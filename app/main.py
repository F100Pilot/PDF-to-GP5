"""FastAPI application: upload PDF tabs (one per track), receive a Guitar Pro 5 file."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __revision__, __version__, audio_download
from .changelog import load_releases, version_key
from .config import settings, youtube_key_status
from .converter import INSTRUMENTS, ConversionError, ConversionOptions, ConversionResult, TrackOptions
from .cover import CoverError, find_cover
from .gp5_writer import MAX_TRACKS, TRACK_COLORS
from .presence import PAGE_ID, Presence
from .sandbox import ConversionTimeout, ConversionUnavailable, run_isolated
from .security import (
    BodySizeLimitMiddleware,
    RateLimiter,
    SameOriginMiddleware,
    SecurityHeadersMiddleware,
    client_key,
    looks_like_pdf,
    safe_filename,
)
from .tunings import TUNINGS
from .youtube import VideoSearchError
from .youtube import search as search_youtube

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
# Not in every platform's mimetypes table (score viewer font and sounds).
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("application/octet-stream", ".sf3")

app = FastAPI(
    title="PDF to GP5",
    version=__version__,
    docs_url="/api/docs" if settings.enable_docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.enable_docs else None,
)
rate_limiter = RateLimiter(settings.rate_limit_per_minute)
inspect_limiter = RateLimiter(settings.inspect_rate_limit_per_minute)
video_limiter = RateLimiter(settings.video_search_per_minute)
cover_limiter = RateLimiter(settings.cover_search_per_minute)
audio_limiter = RateLimiter(settings.audio_jobs_per_minute)
_slots = asyncio.Semaphore(settings.max_concurrent)
presence = Presence()  # enabled by the local launcher (python -m app)
_JOB_PATHS = {"/api/convert", "/api/convert/gp5", "/api/inspect"}


async def _reject(send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


class AdmissionMiddleware:
    """Rate limit and busy check before the upload is received and parsed (pure ASGI)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] in _JOB_PATHS:
            limiter = inspect_limiter if scope["path"] == "/api/inspect" else rate_limiter
            client = scope.get("client")
            if not limiter.allow(client_key(client[0] if client else None)):
                await _reject(send, 429, "Demasiados pedidos. Tente novamente dentro de um minuto.")
                return
            if _slots.locked():
                await _reject(send, 503, "Servidor ocupado. Tente novamente em instantes.")
                return
        await self.app(scope, receive, send)


# Order matters: the last middleware added runs first.
# Multipart framing adds a little overhead on top of the files themselves.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_total_upload_bytes + 256 * 1024)
app.add_middleware(AdmissionMiddleware)
app.add_middleware(SameOriginMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.enable_hsts)


@app.get("/api/changelog")
async def changelog() -> dict:
    """Released changes up to the running version, newest first (for the "what's new" banner)."""
    current = version_key(__version__)
    releases = [r for r in load_releases() if version_key(r["version"]) <= current]
    return {"version": __version__, "releases": releases}


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "revision": __revision__,
        "close_with_browser": presence.enabled,
        "video_search": bool(settings.youtube_api_key),
        # Why automatic video search is off (shown in the video panel); never the key itself.
        "video_search_problem": "" if settings.youtube_api_key else youtube_key_status()[1],
        # Audio from a URL (yt-dlp + FFmpeg), or why it is unavailable.
        "audio_download": audio_download.available()[0],
        "audio_download_problem": audio_download.available()[1],
        "audio_youtube": audio_download.youtube_ready()[0],
        "audio_youtube_problem": audio_download.youtube_ready()[1],
    }


@app.get("/api/video-search")
async def video_search(request: Request, q: Annotated[str, Query(min_length=2, max_length=200)]) -> dict:
    """The song's video on YouTube ("artist title"), when a YouTube Data API key is configured."""
    if not settings.youtube_api_key:
        raise HTTPException(
            status_code=404, detail="Pesquisa de vídeos não configurada (falta a chave da API do YouTube)."
        )
    client = request.client
    if not video_limiter.allow(client_key(client.host if client else None)):
        raise HTTPException(status_code=429, detail="Demasiadas pesquisas. Tente novamente dentro de um minuto.")
    try:
        results = await run_in_threadpool(search_youtube, q, settings.youtube_api_key)
    except VideoSearchError as exc:
        logger.warning("YouTube search failed: %s", exc)
        raise HTTPException(status_code=502, detail="Não foi possível pesquisar no YouTube.") from None
    return {"results": results}


@app.get("/api/cover")
async def song_cover(
    request: Request,
    artist: Annotated[str, Query(min_length=1, max_length=200)],
    title: Annotated[str, Query(min_length=1, max_length=200)],
) -> Response:
    """The song's album cover (iTunes Search API), for the library; 404 when there is none."""
    client = request.client
    if not cover_limiter.allow(client_key(client.host if client else None)):
        raise HTTPException(status_code=429, detail="Demasiadas pesquisas de capas. Tente dentro de um minuto.")
    try:
        found = await run_in_threadpool(find_cover, artist, title)
    except CoverError as exc:
        logger.warning("Cover search failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Não foi possível procurar a capa (sem ligação à internet?)."
        ) from None
    if found is None:
        raise HTTPException(status_code=404, detail="Capa não encontrada.")
    image, media_type = found
    return Response(content=image, media_type=media_type)


class PresenceReport(BaseModel):
    id: str = Field(pattern=PAGE_ID.pattern)
    state: Literal["alive", "gone"]


@app.post("/api/presence", status_code=204)
async def page_presence(report: PresenceReport) -> Response:
    """A page of the app is open ("alive", repeated) or was closed ("gone")."""
    if not presence.enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    presence.update(report.id, report.state == "alive")
    return Response(status_code=204)


@app.get("/api/options")
async def options() -> dict:
    return {
        "tunings": ["auto", *TUNINGS],
        "instruments": ["auto", *INSTRUMENTS],
        "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
        "max_total_upload_mb": settings.max_total_upload_bytes // (1024 * 1024),
        "max_tracks": MAX_TRACKS,
        "track_colors": ["#{:02x}{:02x}{:02x}".format(*rgb) for rgb in TRACK_COLORS],
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
    expand_repeats: bool
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
    expand_repeats: Annotated[bool, Form()] = False,
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
        expand_repeats,
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
        expand_repeats=form.expand_repeats,
        max_pages=settings.max_pages,
        max_events=settings.max_events,
        max_measures=settings.max_measures,
    )


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
    # One budget per request, however many PDFs it carries, so a slow upload
    # cannot hold a worker slot for minutes.
    timeout = min(settings.conversion_timeout_s * len(pdfs), settings.max_job_timeout_s)
    async with _slots:
        try:
            return await run_in_threadpool(run_isolated, pdfs, options, timeout, settings.worker_memory_mb, job)
        except ConversionUnavailable:
            raise HTTPException(status_code=503, detail="Servidor ocupado. Tente novamente em instantes.") from None
        except ConversionTimeout:
            raise HTTPException(status_code=422, detail="O processamento do PDF excedeu o tempo limite.") from None
        except ConversionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None


async def _run_conversion(request: Request, files: list[UploadFile], form: ConvertForm) -> ConversionResult:
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
    options = ConversionOptions(
        tracks=(TrackOptions(filename=file.filename or ""),),
        max_pages=settings.max_pages,
        max_events=settings.max_events,
        max_measures=settings.max_measures,
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


class AudioJobRequest(BaseModel):
    url: str = Field(min_length=1, max_length=audio_download.MAX_URL_LENGTH)
    bitrate: int = 192
    authorized: bool = False  # the user confirms they may download this content


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return host == "localhost"


def _used_on_this_computer(request: Request) -> bool:
    """The page was opened on the computer the server runs on (http://127.0.0.1…/localhost):
    the request comes from this machine AND is addressed to a local name. Both, so a reverse
    proxy on the same machine publishing the app under a public name does not count."""
    client = request.client.host if request.client else ""
    return _loopback(client) and _loopback(request.url.hostname or "")


@app.post("/api/audio/jobs", status_code=202)
async def start_audio_job(request: Request, body: AudioJobRequest) -> dict:
    """Start getting the audio of `url` as an MP3; poll GET /api/audio/jobs/{id} for progress."""
    audio_download.jobs.sweep()
    usable, problem = audio_download.available()
    if not usable:
        raise HTTPException(status_code=503, detail=f"Obter áudio de um URL não está disponível: {problem}.")
    if not body.authorized:
        raise HTTPException(
            status_code=422,
            detail="Confirme que é para uso pessoal ou que tem autorização para descarregar este conteúdo.",
        )
    if body.bitrate not in audio_download.BITRATES:
        raise HTTPException(status_code=422, detail="Qualidade inválida (128, 192, 256 ou 320 kbit/s).")
    if not audio_limiter.allow(client_key(request.client.host if request.client else None)):
        raise HTTPException(status_code=429, detail="Demasiados pedidos. Tente novamente dentro de um minuto.")
    try:
        # YouTube: only the checked video id is kept (the server builds the address); anything else
        # is validated as a URL (resolves the host name).
        url = await run_in_threadpool(audio_download.resolve_source, body.url)
    except audio_download.AudioDownloadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if audio_download.youtube_id(url):
        # Say what is missing now, not after a download that YouTube would refuse.
        ready, problem = audio_download.youtube_ready()
        if not ready:
            raise HTTPException(status_code=503, detail=f"Vídeos do YouTube indisponíveis: {problem}.")
    if audio_download.jobs.active() >= settings.audio_concurrent_jobs:
        raise HTTPException(status_code=503, detail="Já está a ser obtido um áudio. Aguarde que termine.")
    return audio_download.jobs.create(url, body.bitrate, _used_on_this_computer(request)).public()


def _audio_job(job_id: str) -> audio_download.Job:
    job = audio_download.jobs.get(job_id)  # the id is checked (32 hex digits) and only looked up
    if job is None:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada (terminou ou expirou).")
    return job


@app.get("/api/audio/jobs/{job_id}")
async def audio_job_status(job_id: str) -> dict:
    audio_download.jobs.sweep()
    return _audio_job(job_id).public()


@app.get("/api/audio/jobs/{job_id}/file")
async def audio_job_file(job_id: str) -> FileResponse:
    """The MP3, once; its temporary folder is removed after it is sent."""
    job = _audio_job(job_id)
    if job.status != "done" or job.file is None or not job.file.is_file():
        raise HTTPException(status_code=409, detail="O MP3 ainda não está pronto.")
    return FileResponse(
        job.file,
        media_type="audio/mpeg",
        filename=audio_download.download_name(job.title),
        background=BackgroundTask(audio_download.jobs.remove, job.id),
    )


@app.delete("/api/audio/jobs/{job_id}", status_code=204)
async def cancel_audio_job(job_id: str) -> Response:
    audio_download.jobs.remove(_audio_job(job_id).id)
    return Response(status_code=204)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> RedirectResponse:
    """Browsers ask for /favicon.ico on their own; the page's icon is an SVG."""
    return RedirectResponse("/favicon.svg", status_code=301)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
