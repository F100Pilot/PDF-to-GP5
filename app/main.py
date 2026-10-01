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
from urllib.parse import unquote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __revision__, __version__, audio_download, i18n, library_transfer
from .changelog import load_releases, version_key
from .config import settings, youtube_key_status
from .converter import INSTRUMENTS, ConversionError, ConversionOptions, ConversionResult, TrackOptions
from .cover import CoverError, find_cover
from .extract.raster_tab import image_kind
from .gp5_writer import MAX_TRACKS, TRACK_COLORS
from .i18n import LanguageMiddleware, tr
from .library_store import LibraryError, LibraryStore
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
library = LibraryStore(settings.library_dir)
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
                await _reject(
                    send,
                    429,
                    tr(
                        "Demasiados pedidos. Tente novamente dentro de um minuto.",
                        "Too many requests. Try again in a minute.",
                    ),
                )
                return
            if _slots.locked():
                await _reject(
                    send,
                    503,
                    tr("Servidor ocupado. Tente novamente em instantes.", "Server busy. Try again in a moment."),
                )
                return
        await self.app(scope, receive, send)


# Order matters: the last middleware added runs first.
# Multipart framing adds a little overhead on top of the files themselves.
app.add_middleware(
    BodySizeLimitMiddleware,
    max_bytes=settings.max_total_upload_bytes + 256 * 1024,
    path_limits=(("/api/library/", settings.library_max_audio_bytes + 64 * 1024),),
)
app.add_middleware(AdmissionMiddleware)
app.add_middleware(SameOriginMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.enable_hsts)
app.add_middleware(LanguageMiddleware)  # outermost: every message below is written in the user's language


@app.get("/api/changelog")
async def changelog() -> dict:
    """Released changes up to the running version, newest first (for the "what's new" banner)."""
    current = version_key(__version__)
    releases = [r for r in load_releases(i18n.current()) if version_key(r["version"]) <= current]
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
            status_code=404,
            detail=tr(
                "Pesquisa de vídeos não configurada (falta a chave da API do YouTube).",
                "Video search is not configured (the YouTube API key is missing).",
            ),
        )
    client = request.client
    if not video_limiter.allow(client_key(client.host if client else None)):
        raise HTTPException(
            status_code=429,
            detail=tr(
                "Demasiadas pesquisas. Tente novamente dentro de um minuto.",
                "Too many searches. Try again in a minute.",
            ),
        )
    try:
        results = await run_in_threadpool(search_youtube, q, settings.youtube_api_key)
    except VideoSearchError as exc:
        logger.warning("YouTube search failed: %s", exc)
        raise HTTPException(
            status_code=502, detail=tr("Não foi possível pesquisar no YouTube.", "Could not search YouTube.")
        ) from None
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
        raise HTTPException(
            status_code=429,
            detail=tr(
                "Demasiadas pesquisas de capas. Tente dentro de um minuto.",
                "Too many cover searches. Try again in a minute.",
            ),
        )
    try:
        found = await run_in_threadpool(find_cover, artist, title)
    except CoverError as exc:
        logger.warning("Cover search failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=tr(
                "Não foi possível procurar a capa (sem ligação à internet?).",
                "Could not look up the cover (no internet connection?).",
            ),
        ) from None
    if found is None:
        raise HTTPException(status_code=404, detail=tr("Capa não encontrada.", "Cover not found."))
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


def _per_track_hint() -> str:
    return tr(
        "Envie um valor por PDF (ou um só valor para todos).", "Send one value per PDF (or a single value for all)."
    )


def _per_track(values: list[str], count: int, default: str, field: str) -> list[str]:
    if not values:
        return [default] * count
    if len(values) == 1:
        return values * count
    if len(values) != count:
        raise HTTPException(
            status_code=422, detail=tr(f"Campo '{field}': {_per_track_hint()}", f"Field '{field}': {_per_track_hint()}")
        )
    return values


def _options(form: ConvertForm, filenames: list[str]) -> ConversionOptions:
    count = len(filenames)
    names = _per_track(form.track_names, count, "", "track_name") if form.track_names else [""] * count
    tunings = _per_track(form.tunings, count, "auto", "tuning")
    instruments = _per_track(form.instruments, count, "auto", "instrument")
    if any(len(name) > 40 for name in names):
        raise HTTPException(
            status_code=422, detail=tr("Nome de track demasiado longo (máx. 40).", "Track name too long (max. 40).")
        )
    if any(t != "auto" and t not in TUNINGS for t in tunings):
        raise HTTPException(status_code=422, detail=tr("Afinação inválida.", "Invalid tuning."))
    if any(i != "auto" and i not in INSTRUMENTS for i in instruments):
        raise HTTPException(status_code=422, detail=tr("Instrumento inválido.", "Invalid instrument."))
    if form.fixed_value not in (4, 8, 16):
        raise HTTPException(status_code=422, detail=tr("Duração fixa inválida.", "Invalid fixed duration."))
    numerator = denominator = None
    if form.time_signature != "auto":
        match = _TIME_SIGNATURE.match(form.time_signature)
        if not match or not 1 <= int(match.group(1)) <= 16:
            raise HTTPException(status_code=422, detail=tr("Compasso inválido.", "Invalid time signature."))
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
        max_image_pages=settings.max_image_pages,
        max_image_pixels=settings.max_image_pixels,
        max_events=settings.max_events,
        max_measures=settings.max_measures,
    )


async def _read_pdfs(files: list[UploadFile]) -> list[bytes]:
    if not files:
        raise HTTPException(status_code=422, detail=tr("Nenhum PDF enviado.", "No PDF uploaded."))
    if len(files) > MAX_TRACKS:
        raise HTTPException(
            status_code=422,
            detail=tr(
                f"Máximo de {MAX_TRACKS} PDFs (tracks) por música.", f"Maximum of {MAX_TRACKS} PDFs (tracks) per song."
            ),
        )
    pdfs: list[bytes] = []
    for upload in files:
        data = await upload.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=tr(f"Ficheiro demasiado grande: {upload.filename}.", f"File too large: {upload.filename}."),
            )
        if not data or not (looks_like_pdf(data) or image_kind(data)):
            raise HTTPException(
                status_code=415,
                detail=tr(
                    f"O ficheiro enviado não é um PDF nem uma imagem PNG, JPEG ou WebP: {upload.filename}.",
                    f"The uploaded file is not a PDF or a PNG, JPEG or WebP image: {upload.filename}.",
                ),
            )
        pdfs.append(data)
    if sum(len(d) for d in pdfs) > settings.max_total_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=tr("Os PDFs excedem o tamanho total permitido.", "The PDFs exceed the total size allowed."),
        )
    return pdfs


async def _run_job(pdfs: list[bytes], options: ConversionOptions, job: str) -> ConversionResult:
    if _slots.locked():
        raise HTTPException(
            status_code=503,
            detail=tr("Servidor ocupado. Tente novamente em instantes.", "Server busy. Try again in a moment."),
        )
    # One budget per request, however many PDFs it carries, so a slow upload
    # cannot hold a worker slot for minutes.
    timeout = min(settings.conversion_timeout_s * len(pdfs), settings.max_job_timeout_s)
    async with _slots:
        try:
            return await run_in_threadpool(run_isolated, pdfs, options, timeout, settings.worker_memory_mb, job)
        except ConversionUnavailable:
            raise HTTPException(
                status_code=503,
                detail=tr("Servidor ocupado. Tente novamente em instantes.", "Server busy. Try again in a moment."),
            ) from None
        except ConversionTimeout:
            raise HTTPException(
                status_code=422,
                detail=tr(
                    "O processamento do PDF excedeu o tempo limite.", "Processing the PDF exceeded the time limit."
                ),
            ) from None
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
        max_image_pages=settings.max_image_pages,
        max_image_pixels=settings.max_image_pixels,
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
        raise HTTPException(
            status_code=503,
            detail=tr(
                f"Obter áudio de um URL não está disponível: {problem}.",
                f"Getting audio from a URL is not available: {problem}.",
            ),
        )
    if not body.authorized:
        raise HTTPException(
            status_code=422,
            detail=tr(
                "Confirme que é para uso pessoal ou que tem autorização para descarregar este conteúdo.",
                "Confirm that it is for personal use or that you are authorized to download this content.",
            ),
        )
    if body.bitrate not in audio_download.BITRATES:
        raise HTTPException(
            status_code=422,
            detail=tr(
                "Qualidade inválida (128, 192, 256 ou 320 kbit/s).", "Invalid quality (128, 192, 256 or 320 kbit/s)."
            ),
        )
    if not audio_limiter.allow(client_key(request.client.host if request.client else None)):
        raise HTTPException(
            status_code=429,
            detail=tr(
                "Demasiados pedidos. Tente novamente dentro de um minuto.", "Too many requests. Try again in a minute."
            ),
        )
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
            raise HTTPException(
                status_code=503,
                detail=tr(f"Vídeos do YouTube indisponíveis: {problem}.", f"YouTube videos unavailable: {problem}."),
            )
    if audio_download.jobs.active() >= settings.audio_concurrent_jobs:
        raise HTTPException(
            status_code=503,
            detail=tr(
                "Já está a ser obtido um áudio. Aguarde que termine.",
                "Audio is already being fetched. Wait for it to finish.",
            ),
        )
    return audio_download.jobs.create(url, body.bitrate, _used_on_this_computer(request)).public()


def _audio_job(job_id: str) -> audio_download.Job:
    job = audio_download.jobs.get(job_id)  # the id is checked (32 hex digits) and only looked up
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=tr("Tarefa não encontrada (terminou ou expirou).", "Task not found (it finished or expired)."),
        )
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
        raise HTTPException(status_code=409, detail=tr("O MP3 ainda não está pronto.", "The MP3 is not ready yet."))
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


# --- Library on disk ------------------------------------------------------------------------
# Only when the app is used on the computer it runs on: a copy published on the internet does not
# keep its visitors' songs (the page then keeps them in the browser, as before).
LibraryFile = Literal["gp5", "audio", "cover"]


def _library(request: Request) -> LibraryStore:
    if not _used_on_this_computer(request):
        raise HTTPException(
            status_code=404,
            detail=tr(
                "A biblioteca no disco só existe com a aplicação aberta no próprio computador.",
                "The on-disk library only exists when the app is open on the computer itself.",
            ),
        )
    return library


def _stored(found: bool) -> None:
    if not found:
        raise HTTPException(
            status_code=404, detail=tr("Música não encontrada na biblioteca.", "Song not found in the library.")
        )


@app.get("/api/library")
async def library_songs(request: Request) -> dict:
    store = _library(request)
    try:
        songs = await run_in_threadpool(store.songs)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=tr(
                f"Não foi possível ler a pasta da biblioteca: {exc.strerror}.",
                f"Could not read the library folder: {exc.strerror}.",
            ),
        ) from exc
    return {"folder": str(store.root), "songs": songs}


@app.post("/api/library")
async def library_save(
    request: Request, meta: Annotated[str, Form(max_length=4 * 1024 * 1024)], gp5: UploadFile
) -> dict:
    """Store a converted song: `meta` (JSON: key, title, artist, report…) and its GP5 file."""
    store = _library(request)
    try:
        data = json.loads(meta)
    except ValueError:
        raise HTTPException(status_code=422, detail=tr("Dados da música inválidos.", "Invalid song data.")) from None
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail=tr("Dados da música inválidos.", "Invalid song data."))
    content = await gp5.read()
    try:
        return await run_in_threadpool(store.save, data, content)
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=tr(
                f"Não foi possível gravar na pasta da biblioteca: {exc.strerror}.",
                f"Could not write to the library folder: {exc.strerror}.",
            ),
        ) from exc


def _write_failed(exc: OSError) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail=tr(
            f"Não foi possível gravar na pasta da biblioteca: {exc.strerror}.",
            f"Could not write to the library folder: {exc.strerror}.",
        ),
    )


class ExportedSong(BaseModel):
    id: str = Field(max_length=300)
    settings: dict = Field(default_factory=dict)


class LibraryExport(BaseModel):
    songs: list[ExportedSong] = Field(min_length=1, max_length=library_transfer.MAX_SONGS)


@app.post("/api/library/export")
async def library_export(request: Request, body: LibraryExport) -> Response:
    """A ZIP of the chosen songs (no audio) with each one's settings from the exporting browser."""
    store = _library(request)
    items = [(song.id, song.settings) for song in body.songs]
    try:
        data = await run_in_threadpool(library_transfer.export_songs, store, items)
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=tr(
                f"Não foi possível ler a pasta da biblioteca: {exc.strerror}.",
                f"Could not read the library folder: {exc.strerror}.",
            ),
        ) from exc
    return Response(
        data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="biblioteca-pdf-to-gp5.zip"'},
    )


@app.post("/api/library/import")
async def library_import(
    request: Request, file: UploadFile, choices: Annotated[str | None, Form(max_length=1024 * 1024)] = None
) -> dict:
    """Without `choices`: the songs in an exported ZIP and which are already in the library. With
    `choices` (JSON {"chosen": [keys], "replace": [keys]}): import them."""
    store = _library(request)
    data = await file.read()
    try:
        songs = await run_in_threadpool(library_transfer.read_export, data)
        if choices is None:
            return {"songs": await run_in_threadpool(library_transfer.preview, store, songs)}
        try:
            picked = json.loads(choices)
            chosen = {str(k) for k in picked.get("chosen", [])}
            replace = {str(k) for k in picked.get("replace", [])}
        except (ValueError, AttributeError, TypeError):
            raise HTTPException(status_code=422, detail=tr("Escolhas inválidas.", "Invalid choices.")) from None
        return await run_in_threadpool(library_transfer.import_songs, store, songs, chosen, replace)
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise _write_failed(exc) from exc


@app.get("/api/library/{song_id}")
async def library_song(request: Request, song_id: str) -> dict:
    song = await run_in_threadpool(_library(request).song, song_id)
    _stored(song is not None)
    return song


@app.get("/api/library/{song_id}/{kind}")
async def library_file(request: Request, song_id: str, kind: LibraryFile) -> FileResponse:
    found = await run_in_threadpool(_library(request).file, song_id, kind)
    _stored(found is not None)
    path, media_type, name = found
    return FileResponse(path, media_type=media_type, filename=name, content_disposition_type="inline")


async def _library_change(request: Request, song_id: str, kind: str, data: bytes | None) -> Response:
    store = _library(request)
    try:
        if kind == "audio":
            name = unquote(request.headers.get("x-filename", "")) or "audio"
            found = await run_in_threadpool(store.set_audio, song_id, name, data)
        elif kind == "cover":
            found = await run_in_threadpool(store.set_cover, song_id, data)
        else:
            raise HTTPException(
                status_code=405,
                detail=tr("Só o áudio e a capa podem ser mudados.", "Only the audio and the cover can be changed."),
            )
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=tr(
                f"Não foi possível gravar na pasta da biblioteca: {exc.strerror}.",
                f"Could not write to the library folder: {exc.strerror}.",
            ),
        ) from exc
    _stored(found)
    return Response(status_code=204)


@app.put("/api/library/{song_id}/{kind}", status_code=204)
async def library_put_file(request: Request, song_id: str, kind: LibraryFile) -> Response:
    """The song's audio or cover: the file itself as the request body (audio: name in X-Filename)."""
    data = await request.body()
    if not data:
        raise HTTPException(status_code=422, detail=tr("Ficheiro vazio.", "Empty file."))
    return await _library_change(request, song_id, kind, data)


@app.delete("/api/library/{song_id}/{kind}", status_code=204)
async def library_delete_file(request: Request, song_id: str, kind: LibraryFile) -> Response:
    return await _library_change(request, song_id, kind, None)


@app.delete("/api/library/{song_id}", status_code=204)
async def library_delete(request: Request, song_id: str) -> Response:
    _stored(await run_in_threadpool(_library(request).delete, song_id))
    return Response(status_code=204)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> RedirectResponse:
    """Browsers ask for /favicon.ico on their own; the page's icon is an SVG."""
    return RedirectResponse("/favicon.svg", status_code=301)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
