"""FastAPI application: upload a PDF tab, receive a Guitar Pro 5 file."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import __version__
from .config import settings
from .converter import INSTRUMENTS, ConversionError, ConversionOptions, ConversionResult
from .sandbox import ConversionTimeout, run_isolated
from .security import BodySizeLimitMiddleware, RateLimiter, SecurityHeadersMiddleware, looks_like_pdf, safe_filename
from .tunings import TUNINGS

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="PDF to GP5",
    version=__version__,
    docs_url="/api/docs" if settings.enable_docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.enable_docs else None,
)
# Multipart framing adds a little overhead on top of the file itself.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes + 64 * 1024)
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.enable_hsts)

rate_limiter = RateLimiter(settings.rate_limit_per_minute)
_slots = asyncio.Semaphore(settings.max_concurrent)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/options")
async def options() -> dict:
    return {
        "tunings": ["auto", *TUNINGS],
        "instruments": ["auto", *INSTRUMENTS],
        "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
        "max_pages": settings.max_pages,
    }


_TIME_SIGNATURE = re.compile(r"^(\d{1,2})/(2|4|8|16)$")


@dataclass(frozen=True)
class ConvertForm:
    """Form fields shared by both conversion endpoints; empty values mean "detect"."""

    title: str
    artist: str
    tempo: int | None
    time_signature: str
    tuning: str
    instrument: str
    rhythm_mode: str
    fixed_value: int


def convert_form(
    title: Annotated[str, Form(max_length=100)] = "",
    artist: Annotated[str, Form(max_length=100)] = "",
    tempo: Annotated[int | None, Form(ge=20, le=400)] = None,
    time_signature: Annotated[str, Form(max_length=5)] = "auto",
    tuning: Annotated[str, Form(max_length=20)] = "auto",
    instrument: Annotated[str, Form(max_length=20)] = "auto",
    rhythm_mode: Annotated[Literal["auto", "spacing", "fixed"], Form()] = "auto",
    fixed_value: Annotated[int, Form()] = 8,
) -> ConvertForm:
    return ConvertForm(title, artist, tempo, time_signature, tuning, instrument, rhythm_mode, fixed_value)


def _options(form: ConvertForm) -> ConversionOptions:
    if form.tuning != "auto" and form.tuning not in TUNINGS:
        raise HTTPException(status_code=422, detail="Afinação inválida.")
    if form.instrument != "auto" and form.instrument not in INSTRUMENTS:
        raise HTTPException(status_code=422, detail="Instrumento inválido.")
    if form.fixed_value not in (4, 8, 16):
        raise HTTPException(status_code=422, detail="Duração fixa inválida.")
    numerator = denominator = None
    if form.time_signature != "auto":
        match = _TIME_SIGNATURE.match(form.time_signature)
        if not match or not 1 <= int(match.group(1)) <= 16:
            raise HTTPException(status_code=422, detail="Compasso inválido.")
        numerator, denominator = int(match.group(1)), int(match.group(2))
    return ConversionOptions(
        title=form.title,
        artist=form.artist,
        tempo=form.tempo,
        numerator=numerator,
        denominator=denominator,
        tuning=form.tuning,
        instrument=form.instrument,
        rhythm_mode=form.rhythm_mode,
        fixed_value=form.fixed_value,
        max_pages=settings.max_pages,
        max_events=settings.max_events,
    )


async def _run_conversion(request: Request, file: UploadFile, form: ConvertForm) -> ConversionResult:
    client = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client):
        raise HTTPException(status_code=429, detail="Demasiados pedidos. Tente novamente dentro de um minuto.")
    options = _options(form)

    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Ficheiro demasiado grande.")
    if not data or not looks_like_pdf(data):
        raise HTTPException(status_code=415, detail="O ficheiro enviado não é um PDF.")

    if _slots.locked():
        raise HTTPException(status_code=503, detail="Servidor ocupado. Tente novamente em instantes.")
    async with _slots:
        try:
            return await run_in_threadpool(
                run_isolated, data, options, settings.conversion_timeout_s, settings.worker_memory_mb
            )
        except ConversionTimeout:
            raise HTTPException(status_code=422, detail="O processamento do PDF excedeu o tempo limite.") from None
        except ConversionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None


FileField = Annotated[UploadFile, File(description="PDF com tablatura")]
FormFields = Annotated[ConvertForm, Depends(convert_form)]


@app.post("/api/convert")
async def convert_json(request: Request, file: FileField, form: FormFields) -> JSONResponse:
    """Convert and return JSON with the report and the GP5 file (base64)."""
    result = await _run_conversion(request, file, form)
    return JSONResponse(
        {
            "filename": safe_filename(result.report["title"], file.filename or ""),
            "gp5_base64": base64.b64encode(result.gp5).decode("ascii"),
            "report": result.report,
        }
    )


@app.post("/api/convert/gp5")
async def convert_binary(request: Request, file: FileField, form: FormFields) -> Response:
    """Convert and return the .gp5 file directly (for scripts / curl)."""
    result = await _run_conversion(request, file, form)
    filename = safe_filename(result.report["title"], file.filename or "")
    return Response(
        content=result.gp5,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Conversion-Warnings": str(len(result.report["warnings"])),
        },
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
