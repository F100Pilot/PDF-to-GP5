"""FastAPI application: upload a PDF tab, receive a Guitar Pro 5 file."""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import __version__
from .config import settings
from .converter import INSTRUMENTS, ConversionError, ConversionOptions, ConversionResult
from .rhythm import RhythmOptions
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


async def _run_conversion(
    request: Request,
    file: UploadFile,
    title: str,
    artist: str,
    tempo: int,
    tuning: str,
    instrument: str,
    rhythm_mode: str,
    fixed_value: int,
    numerator: int,
    denominator: int,
) -> ConversionResult:
    client = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client):
        raise HTTPException(status_code=429, detail="Demasiados pedidos. Tente novamente dentro de um minuto.")
    if tuning != "auto" and tuning not in TUNINGS:
        raise HTTPException(status_code=422, detail="Afinação inválida.")
    if instrument != "auto" and instrument not in INSTRUMENTS:
        raise HTTPException(status_code=422, detail="Instrumento inválido.")
    if fixed_value not in (4, 8, 16):
        raise HTTPException(status_code=422, detail="Duração fixa inválida.")
    if denominator not in (2, 4, 8, 16):
        raise HTTPException(status_code=422, detail="Denominador do compasso inválido.")

    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Ficheiro demasiado grande.")
    if not data or not looks_like_pdf(data):
        raise HTTPException(status_code=415, detail="O ficheiro enviado não é um PDF.")

    options = ConversionOptions(
        title=title,
        artist=artist,
        tempo=tempo,
        tuning=tuning,
        instrument=instrument,
        rhythm=RhythmOptions(mode=rhythm_mode, fixed_value=fixed_value, numerator=numerator, denominator=denominator),
        max_pages=settings.max_pages,
        max_events=settings.max_events,
    )
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


# Shared form parameters (validated by FastAPI before any processing).
FileField = Annotated[UploadFile, File(description="PDF com tablatura")]
Title = Annotated[str, Form(max_length=100)]
Artist = Annotated[str, Form(max_length=100)]
Tempo = Annotated[int, Form(ge=20, le=400)]
Tuning = Annotated[str, Form(max_length=20)]
Instrument = Annotated[str, Form(max_length=20)]
Mode = Annotated[Literal["auto", "spacing", "fixed"], Form()]
FixedValue = Annotated[int, Form()]
Numerator = Annotated[int, Form(ge=1, le=16)]
Denominator = Annotated[int, Form()]


@app.post("/api/convert")
async def convert_json(
    request: Request,
    file: FileField,
    title: Title = "",
    artist: Artist = "",
    tempo: Tempo = 120,
    tuning: Tuning = "auto",
    instrument: Instrument = "auto",
    rhythm_mode: Mode = "auto",
    fixed_value: FixedValue = 8,
    numerator: Numerator = 4,
    denominator: Denominator = 4,
) -> JSONResponse:
    """Convert and return JSON with the report and the GP5 file (base64)."""
    result = await _run_conversion(
        request, file, title, artist, tempo, tuning, instrument, rhythm_mode, fixed_value, numerator, denominator
    )
    return JSONResponse(
        {
            "filename": safe_filename(title, file.filename or ""),
            "gp5_base64": base64.b64encode(result.gp5).decode("ascii"),
            "report": result.report,
        }
    )


@app.post("/api/convert/gp5")
async def convert_binary(
    request: Request,
    file: FileField,
    title: Title = "",
    artist: Artist = "",
    tempo: Tempo = 120,
    tuning: Tuning = "auto",
    instrument: Instrument = "auto",
    rhythm_mode: Mode = "auto",
    fixed_value: FixedValue = 8,
    numerator: Numerator = 4,
    denominator: Denominator = 4,
) -> Response:
    """Convert and return the .gp5 file directly (for scripts / curl)."""
    result = await _run_conversion(
        request, file, title, artist, tempo, tuning, instrument, rhythm_mode, fixed_value, numerator, denominator
    )
    filename = safe_filename(title, file.filename or "")
    return Response(
        content=result.gp5,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Conversion-Warnings": str(len(result.report["warnings"])),
        },
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
