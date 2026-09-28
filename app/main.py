"""FastAPI application: upload PDF tabs (one per track), receive a Guitar Pro 5 file."""

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

from . import __revision__, __version__
from .changelog import load_releases, version_key
from .config import settings
from .converter import INSTRUMENTS, ConversionError, ConversionOptions, ConversionResult, TrackOptions
from .gp5_writer import MAX_TRACKS
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
# Multipart framing adds a little overhead on top of the files themselves.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_total_upload_bytes + 256 * 1024)
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.enable_hsts)

rate_limiter = RateLimiter(settings.rate_limit_per_minute)
_slots = asyncio.Semaphore(settings.max_concurrent)


@app.get("/api/changelog")
async def changelog() -> dict:
    """Released changes up to the running version, newest first (for the "what's new" banner)."""
    current = version_key(__version__)
    releases = [r for r in load_releases() if version_key(r["version"]) <= current]
    return {"version": __version__, "releases": releases}


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__, "revision": __revision__}


@app.get("/api/options")
async def options() -> dict:
    return {
        "tunings": ["auto", *TUNINGS],
        "instruments": ["auto", *INSTRUMENTS],
        "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
        "max_total_upload_mb": settings.max_total_upload_bytes // (1024 * 1024),
        "max_tracks": MAX_TRACKS,
        "max_pages": settings.max_pages,
    }


_TIME_SIGNATURE = re.compile(r"^(\d{1,2})/(2|4|8|16)$")
_PER_TRACK_HINT = "Envie um valor por PDF (ou um só valor para todos)."


@dataclass(frozen=True)
class ConvertForm:
    """Form fields shared by both conversion endpoints; empty values mean "detect".

    ``track_name``, ``tuning`` and ``instrument`` are per PDF, in upload order; a
    single value applies to every PDF.
    """

    title: str
    artist: str
    tempo: int | None
    time_signature: str
    rhythm_mode: str
    fixed_value: int
    parentheses: str
    track_names: list[str]
    tunings: list[str]
    instruments: list[str]


def convert_form(
    title: Annotated[str, Form(max_length=100)] = "",
    artist: Annotated[str, Form(max_length=100)] = "",
    tempo: Annotated[int | None, Form(ge=20, le=400)] = None,
    time_signature: Annotated[str, Form(max_length=5)] = "auto",
    rhythm_mode: Annotated[Literal["auto", "spacing", "fixed"], Form()] = "auto",
    fixed_value: Annotated[int, Form()] = 8,
    parentheses: Annotated[Literal["tie", "note"], Form()] = "tie",
    track_name: Annotated[list[str] | None, Form()] = None,
    tuning: Annotated[list[str] | None, Form()] = None,
    instrument: Annotated[list[str] | None, Form()] = None,
) -> ConvertForm:
    return ConvertForm(
        title,
        artist,
        tempo,
        time_signature,
        rhythm_mode,
        fixed_value,
        parentheses,
        track_name or [],
        tuning or [],
        instrument or [],
    )


def _per_track(values: list[str], count: int, default: str, field: str) -> list[str]:
    if not values:
        return [default] * count
    if len(values) == 1:
        return values * count
    if len(values) != count:
        raise HTTPException(status_code=422, detail=f"Campo '{field}': {_PER_TRACK_HINT}")
    return values


def _options(form: ConvertForm, filenames: list[str]) -> ConversionOptions:
    count = len(filenames)
    names = _per_track(form.track_names, count, "", "track_name") if form.track_names else [""] * count
    tunings = _per_track(form.tunings, count, "auto", "tuning")
    instruments = _per_track(form.instruments, count, "auto", "instrument")
    if any(len(name) > 40 for name in names):
        raise HTTPException(status_code=422, detail="Nome de track demasiado longo (máx. 40).")
    if any(t != "auto" and t not in TUNINGS for t in tunings):
        raise HTTPException(status_code=422, detail="Afinação inválida.")
    if any(i != "auto" and i not in INSTRUMENTS for i in instruments):
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
        tracks=tuple(
            TrackOptions(name=n, filename=f, tuning=t, instrument=i)
            for n, f, t, i in zip(names, filenames, tunings, instruments, strict=True)
        ),
        rhythm_mode=form.rhythm_mode,
        fixed_value=form.fixed_value,
        parentheses=form.parentheses,
        max_pages=settings.max_pages,
        max_events=settings.max_events,
    )


def _check_client(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client):
        raise HTTPException(status_code=429, detail="Demasiados pedidos. Tente novamente dentro de um minuto.")


async def _read_pdfs(files: list[UploadFile]) -> list[bytes]:
    if not files:
        raise HTTPException(status_code=422, detail="Nenhum PDF enviado.")
    if len(files) > MAX_TRACKS:
        raise HTTPException(status_code=422, detail=f"Máximo de {MAX_TRACKS} PDFs (tracks) por música.")
    pdfs: list[bytes] = []
    for upload in files:
        data = await upload.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"Ficheiro demasiado grande: {upload.filename}.")
        if not data or not looks_like_pdf(data):
            raise HTTPException(status_code=415, detail=f"O ficheiro enviado não é um PDF: {upload.filename}.")
        pdfs.append(data)
    if sum(len(d) for d in pdfs) > settings.max_total_upload_bytes:
        raise HTTPException(status_code=413, detail="Os PDFs excedem o tamanho total permitido.")
    return pdfs


async def _run_job(pdfs: list[bytes], options: ConversionOptions, job: str) -> ConversionResult:
    if _slots.locked():
        raise HTTPException(status_code=503, detail="Servidor ocupado. Tente novamente em instantes.")
    timeout = settings.conversion_timeout_s * len(pdfs)
    async with _slots:
        try:
            return await run_in_threadpool(run_isolated, pdfs, options, timeout, settings.worker_memory_mb, job)
        except ConversionTimeout:
            raise HTTPException(status_code=422, detail="O processamento do PDF excedeu o tempo limite.") from None
        except ConversionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None


async def _run_conversion(request: Request, files: list[UploadFile], form: ConvertForm) -> ConversionResult:
    _check_client(request)
    options = _options(form, [f.filename or "" for f in files])
    return await _run_job(await _read_pdfs(files), options, "convert")


def _download_name(result: ConversionResult, files: list[UploadFile]) -> str:
    return safe_filename(result.report["title"], files[0].filename or "" if files else "")


FileField = Annotated[UploadFile, File(description="PDF com tablatura")]
FilesField = Annotated[list[UploadFile], File(description="Um PDF por track (máx. 7)")]
FormFields = Annotated[ConvertForm, Depends(convert_form)]


@app.post("/api/inspect")
async def inspect_pdf(request: Request, file: FileField) -> JSONResponse:
    """Detect song metadata and the track's part so the form can be pre-filled."""
    _check_client(request)
    options = ConversionOptions(
        tracks=(TrackOptions(filename=file.filename or ""),),
        max_pages=settings.max_pages,
        max_events=settings.max_events,
    )
    result = await _run_job(await _read_pdfs([file]), options, "inspect")
    return JSONResponse(result.report)


@app.post("/api/convert")
async def convert_json(request: Request, file: FilesField, form: FormFields) -> JSONResponse:
    """Convert one PDF per track and return JSON with the report and the GP5 file (base64)."""
    result = await _run_conversion(request, file, form)
    return JSONResponse(
        {
            "filename": _download_name(result, file),
            "gp5_base64": base64.b64encode(result.gp5).decode("ascii"),
            "report": result.report,
        }
    )


@app.post("/api/convert/gp5")
async def convert_binary(request: Request, file: FilesField, form: FormFields) -> Response:
    """Convert and return the .gp5 file directly (for scripts / curl)."""
    result = await _run_conversion(request, file, form)
    return Response(
        content=result.gp5,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{_download_name(result, file)}"',
            "X-Conversion-Warnings": str(len(result.report["warnings"])),
        },
    )


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
