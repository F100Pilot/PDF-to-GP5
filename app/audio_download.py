"""Audio of a web page or media file the user may download, converted to MP3 (yt-dlp + FFmpeg).

Only content offered for download is processed:

* a direct audio/video file (the server hands out the file itself);
* media published under a Creative Commons or public-domain licence (as the site reports it);
* a site the owner of this installation declares as their own (``AUDIO_DOWNLOAD_HOSTS``).

YouTube pages are processed only when licensed Creative Commons (its terms forbid downloading
otherwise). No cookies, logins or account data are ever used, and DRM-protected formats are
never selected, so nothing behind authentication, a paywall or DRM is reachable.

Each job gets its own temporary folder, removed once the MP3 has been downloaded, when the job
fails, or after ``AUDIO_TTL_S``. Downloads and conversions run in a worker thread with a size
limit and a deadline; FFmpeg runs as a separate process with its arguments passed as a list
(never through a shell).
"""

from __future__ import annotations

import ipaddress
import logging
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unicodedata
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .config import settings

logger = logging.getLogger(__name__)

BITRATES = (128, 192, 256, 320)  # kbit/s offered to the user
MAX_URL_LENGTH = 2048
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
TEMP_PREFIX = "pdf-to-gp5-audio-"
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com", "googlevideo.com")
_FREE_LICENCE = re.compile(
    r"creative\s*commons|\bcc[\s-]?(?:by|0|zero)\b|public\s*domain|dom[ií]nio\s+p[uú]blico", re.IGNORECASE
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Pages whose path carries the video id: /shorts/<id>, /embed/<id>, /live/<id>, /v/<id>.
_YOUTUBE_ID_PATHS = ("shorts", "embed", "live", "v")


class AudioDownloadError(Exception):
    """A user-facing error: the message is safe to show."""


# --- Input validation ----------------------------------------------------------------------------


def _resolve(host: str) -> list[str]:
    """IP addresses of ``host`` (monkeypatched in tests)."""
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def _is_youtube(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in _YOUTUBE_HOSTS)


def _declared(host: str) -> bool:
    """A host the owner of this installation publishes on (never YouTube)."""
    return not _is_youtube(host) and any(host == h or host.endswith("." + h) for h in settings.audio_download_hosts)


def validate_url(url: str) -> str:
    """The URL, checked: http(s), no credentials, no control characters or spaces, and a public
    address (so the server cannot be used to reach the local network), unless the host is a
    declared own site."""
    url = (url or "").strip()
    if not url:
        raise AudioDownloadError("Indique o endereço (URL) do áudio ou vídeo.")
    if len(url) > MAX_URL_LENGTH:
        raise AudioDownloadError("O endereço é demasiado longo.")
    if _CONTROL.search(url) or any(ch.isspace() for ch in url):
        raise AudioDownloadError("O endereço tem espaços ou caracteres inválidos.")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise AudioDownloadError("Endereço inválido.") from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AudioDownloadError("O endereço tem de começar por http:// ou https://.")
    if parts.username or parts.password:
        raise AudioDownloadError("O endereço não pode ter nome de utilizador nem palavra-passe.")
    if port is not None and not 1 <= port <= 65535:
        raise AudioDownloadError("Endereço inválido.")
    host = parts.hostname.lower()
    if not _declared(host):
        try:
            addresses = _resolve(host)
        except OSError as exc:
            raise AudioDownloadError(
                "Não foi possível encontrar esse endereço (verifique o URL e a internet)."
            ) from exc
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%")[0])
            if not ip.is_global:
                raise AudioDownloadError(
                    "O endereço aponta para a rede local; só são aceites endereços da internet "
                    "(ou sites declarados em AUDIO_DOWNLOAD_HOSTS)."
                )
    return url


def youtube_id(text: str) -> str | None:
    """The video id of a YouTube link ("…/watch?v=ID", "youtu.be/ID", "…/shorts/ID", "…/embed/ID")
    or of a bare 11-character id; None for anything else."""
    text = (text or "").strip()
    if _YOUTUBE_ID.fullmatch(text):
        return text
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not _is_youtube(host) or host.endswith("googlevideo.com"):
        return None
    segments = [segment for segment in parts.path.split("/") if segment]
    if host == "youtu.be" or host.endswith(".youtu.be"):
        candidate = segments[0] if segments else ""
    elif segments[:1] == ["watch"]:
        candidate = (parse_qs(parts.query).get("v") or [""])[0]
    elif len(segments) >= 2 and segments[0] in _YOUTUBE_ID_PATHS:
        candidate = segments[1]
    else:
        return None
    return candidate if _YOUTUBE_ID.fullmatch(candidate) else None


def youtube_url(video_id: str) -> str:
    """The server-built address of a YouTube video (only the id comes from the user)."""
    if not _YOUTUBE_ID.fullmatch(video_id):
        raise AudioDownloadError("Identificador de vídeo do YouTube inválido.")
    return f"https://www.youtube.com/watch?v={video_id}"


def resolve_source(text: str) -> str:
    """The address to process: for YouTube, rebuilt by the server from the checked video id (no
    host, path or parameters from the user reach yt-dlp); anything else through validate_url()."""
    video = youtube_id(text)
    if video:
        return youtube_url(video)
    try:
        host = (urlsplit((text or "").strip()).hostname or "").lower()
    except ValueError:
        host = ""
    if _is_youtube(host):
        raise AudioDownloadError("Indique um vídeo do YouTube (não uma lista de reprodução nem um canal).")
    return validate_url(text)


# --- Technical limits (whatever the content) -------------------------------------------------------


def check_limits(info: dict) -> None:
    """Refuse playlists, live streams and media longer than the limit (before any download)."""
    if info.get("_type") in ("playlist", "multi_video") or info.get("entries") is not None:
        raise AudioDownloadError("Listas de reprodução não são suportadas: indique um único ficheiro ou vídeo.")
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        raise AudioDownloadError("Emissões em direto não são suportadas.")
    duration = info.get("duration")
    if isinstance(duration, (int, float)) and duration > settings.audio_max_duration_s:
        raise AudioDownloadError(
            f"O áudio tem {round(duration / 60)} min; o máximo é {settings.audio_max_duration_s // 60} min."
        )


# --- May this content be downloaded? ---------------------------------------------------------------


def authorize(info: dict, url: str) -> str:
    """Why the content may be downloaded ("direct", "licence" or "declared"), or raise with the
    reason it may not. ``info`` is yt-dlp's description of the page (no download yet); the
    technical limits are checked separately (check_limits)."""
    page = info.get("webpage_url") or url
    host = (urlsplit(page).hostname or "").lower()
    licence = str(info.get("license") or "").strip()
    if _FREE_LICENCE.search(licence):
        return "licence"
    if info.get("direct") and not _is_youtube(host):
        return "direct"
    if _declared(host):
        return "declared"
    detail = f" (licença indicada: {licence[:80]})" if licence else ""
    raise AudioDownloadError(
        "Este conteúdo não está disponível para download: não é um ficheiro direto nem tem licença "
        f"Creative Commons ou de domínio público{detail}. Só é processado conteúdo que pode ser "
        "descarregado (ficheiros seus, Creative Commons, domínio público)."
    )


# --- Tools ---------------------------------------------------------------------------------------


def ffmpeg_path() -> str | None:
    """The FFmpeg program: the one shipped with imageio-ffmpeg, else one on the PATH."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):  # not installed, or no binary for this platform
        return shutil.which("ffmpeg")


def available() -> tuple[bool, str]:
    """(usable, problem) for the health check and the page."""
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return False, "falta o yt-dlp (pip install -r requirements.txt)"
    if not ffmpeg_path():
        return False, "falta o FFmpeg (pip install -r requirements.txt instala o imageio-ffmpeg)"
    return True, ""


# JavaScript runtimes yt-dlp can use for YouTube, highest priority first, with their program names.
_JS_RUNTIMES = (("deno", ("deno",)), ("node", ("node",)), ("quickjs", ("qjs", "quickjs")), ("bun", ("bun",)))


def js_runtimes() -> dict[str, dict]:
    """The JavaScript runtimes installed on this computer, as yt-dlp's ``js_runtimes`` option."""
    found: dict[str, dict] = {}
    for name, programs in _JS_RUNTIMES:
        path = next((p for p in map(shutil.which, programs) if p), None)
        if path:
            found[name] = {"path": path}
    return found


def youtube_ready() -> tuple[bool, str]:
    """(ready, problem): YouTube needs the yt-dlp-ejs scripts and a JavaScript runtime."""
    try:
        import yt_dlp_ejs  # noqa: F401
    except ImportError:
        return False, "falta o yt-dlp-ejs (pip install -r requirements.txt instala o yt-dlp[default])"
    if not js_runtimes():
        return False, "falta um runtime JavaScript para o YouTube (instale o Deno ou o Node.js)"
    return True, ""


class _Stop(Exception):
    """Raised from yt-dlp's progress hook to stop a download (limit reached or cancelled)."""


class _QuietLogger:
    """yt-dlp messages go to our log (never to the page: they may contain the URL)."""

    def debug(self, message: str) -> None:
        logger.debug("yt-dlp: %s", message)

    def info(self, message: str) -> None:
        logger.debug("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        logger.info("yt-dlp: %s", message)

    def error(self, message: str) -> None:
        logger.info("yt-dlp: %s", message)


def _options(directory: Path, hook: Callable[[dict], None]) -> dict:
    return {
        "format": "bestaudio/best",
        "outtmpl": {"default": str(directory / "source.%(ext)s")},
        "paths": {"home": str(directory), "temp": str(directory)},
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 1,
        "max_filesize": settings.audio_max_bytes,
        "cachedir": False,
        "overwrites": True,
        "progress_hooks": [hook],
        # YouTube's player needs JavaScript: any runtime installed here (yt-dlp picks the best), with
        # the scripts of the installed yt-dlp-ejs package — never code fetched at run time.
        "js_runtimes": js_runtimes() or {"deno": {}},
        "remote_components": [],
        # Never: cookies, credentials, unplayable (DRM) formats — defaults kept on purpose.
    }


def _probe(url: str, directory: Path, hook: Callable[[dict], None]) -> tuple[object, dict]:
    """yt-dlp's description of the page, without downloading (monkeypatched in tests)."""
    import yt_dlp

    ydl = yt_dlp.YoutubeDL(_options(directory, hook))
    try:
        info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        ydl.close()
        raise AudioDownloadError(
            "Não foi possível ler esse endereço (página não suportada, conteúdo protegido ou sem áudio)."
        ) from exc
    return ydl, info or {}


def _download(ydl: object, info: dict, directory: Path) -> Path:
    """Download the chosen audio into ``directory`` (monkeypatched in tests)."""
    import yt_dlp

    try:
        ydl.process_info(info)
    except yt_dlp.utils.DownloadError as exc:
        raise AudioDownloadError("O download falhou.") from exc
    finally:
        ydl.close()
    root = directory.resolve()
    files = [
        p
        for p in directory.glob("source.*")
        if p.is_file() and not p.is_symlink() and not p.name.endswith(".part") and p.resolve().parent == root
    ]
    if not files:
        raise AudioDownloadError("O download não produziu nenhum ficheiro (talvez tenha excedido o tamanho máximo).")
    return files[0]


def convert_to_mp3(
    source: Path,
    target: Path,
    bitrate: int,
    duration: float | None,
    deadline: float,
    progress: Callable[[float], None],
    cancelled: Callable[[], bool] = lambda: False,
    title: str = "",
) -> None:
    """Encode the first audio stream of ``source`` as MP3 (LAME, constant bitrate) with FFmpeg.

    FFmpeg's arguments are a list (no shell); its progress output gives ``progress`` (0…1).
    """
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise AudioDownloadError("O FFmpeg não está disponível.")
    if bitrate not in BITRATES:
        raise AudioDownloadError("Qualidade inválida.")
    args = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(source), "-vn", "-sn", "-dn"]
    args += ["-map", "0:a:0", "-map_metadata", "-1", "-codec:a", "libmp3lame", "-b:a", f"{bitrate}k"]
    if title:
        args += ["-metadata", f"title={title}"]
    args += ["-progress", "pipe:1", "-nostats", str(target)]
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    watchdog = threading.Timer(max(1.0, deadline - time.monotonic()), process.kill)
    watchdog.start()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            if cancelled():
                process.kill()
                break
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and duration and value.isdigit():
                progress(min(1.0, int(value) / 1e6 / duration))
        process.wait()
    finally:
        watchdog.cancel()
    if cancelled():
        raise AudioDownloadError("Cancelado.")
    if time.monotonic() >= deadline:
        raise AudioDownloadError("A conversão demorou demasiado e foi interrompida.")
    if process.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        raise AudioDownloadError("O FFmpeg não conseguiu converter o áudio (o ficheiro não tem áudio legível).")
    if target.stat().st_size > settings.audio_max_bytes:
        raise AudioDownloadError("O MP3 excede o tamanho máximo.")


def download_name(title: str) -> str:
    """ASCII file name for the MP3 (no path separators or special characters)."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    stem = re.sub(r"\.{2,}", "", re.sub(r"[^A-Za-z0-9 ()._-]+", "_", ascii_title)).strip(" ._-")[:80]
    return f"{stem or 'audio'}.mp3"


# --- Jobs ------------------------------------------------------------------------------------------

ACTIVE = ("queued", "checking", "downloading", "converting")


@dataclass
class Job:
    id: str
    url: str
    bitrate: int
    directory: Path
    created: float = field(default_factory=time.monotonic)
    status: str = "queued"  # queued, checking, downloading, converting, done, error, cancelled
    progress: float = 0.0  # 0…1
    error: str = ""
    title: str = ""
    reason: str = ""  # why it may be downloaded: direct / licence / declared
    file: Path | None = None
    cancelled: bool = False

    def public(self) -> dict:
        messages = {
            "queued": "Na fila…",
            "checking": "A verificar o endereço e se o conteúdo pode ser descarregado…",
            "downloading": "A descarregar…",
            "converting": "A converter para MP3…",
            "done": "Pronto.",
            "error": self.error,
            "cancelled": "Cancelado.",
        }
        return {
            "id": self.id,
            "status": self.status,
            "progress": round(self.progress * 100),
            "message": messages.get(self.status, ""),
            "title": self.title,
            "filename": download_name(self.title) if self.status == "done" else "",
            "allowed_because": self.reason,
        }


class JobStore:
    """Jobs in memory; each with its own temporary folder, removed when no longer needed."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None
        self._purge_stale_folders()

    def _purge_stale_folders(self) -> None:
        """Folders left by a previous run that ended abruptly."""
        limit = time.time() - 2 * settings.audio_ttl_s
        for folder in Path(tempfile.gettempdir()).glob(f"{TEMP_PREFIX}*"):
            try:
                if folder.is_dir() and folder.stat().st_mtime < limit:
                    shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                pass

    def active(self) -> int:
        with self._lock:
            return sum(job.status in ACTIVE for job in self._jobs.values())

    def create(self, url: str, bitrate: int) -> Job:
        directory = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
        job = Job(uuid.uuid4().hex, url, bitrate, directory)
        with self._lock:
            self._jobs[job.id] = job
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=settings.audio_concurrent_jobs, thread_name_prefix="audio")
        self._executor.submit(run_job, job)
        return job

    def get(self, job_id: str) -> Job | None:
        if not JOB_ID.match(job_id or ""):
            return None
        with self._lock:
            return self._jobs.get(job_id)

    def remove(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job is not None:
            job.cancelled = True
            shutil.rmtree(job.directory, ignore_errors=True)

    def sweep(self) -> None:
        """Forget finished jobs older than the TTL (and anything far past its deadline)."""
        now = time.monotonic()
        with self._lock:
            stale = [
                job.id
                for job in self._jobs.values()
                if (job.status not in ACTIVE and now - job.created > settings.audio_ttl_s)
                or now - job.created > settings.audio_timeout_s + settings.audio_ttl_s
            ]
        for job_id in stale:
            self.remove(job_id)


def run_job(job: Job) -> None:
    """Check, download and convert; any failure leaves the job in "error" with a clear message."""
    deadline = time.monotonic() + settings.audio_timeout_s

    def hook(status: dict) -> None:
        if job.cancelled:
            raise _Stop("cancelled")
        if time.monotonic() > deadline:
            raise _Stop("timeout")
        done = status.get("downloaded_bytes") or 0
        if done > settings.audio_max_bytes:
            raise _Stop("size")
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        if status.get("status") == "downloading" and total:
            job.progress = 0.05 + 0.6 * min(1.0, done / total)

    try:
        job.status = "checking"
        ydl, info = _probe(job.url, job.directory, hook)
        try:
            check_limits(info)
            job.reason = authorize(info, job.url)
        except AudioDownloadError:
            close = getattr(ydl, "close", None)
            if close:
                close()
            raise
        job.title = _CONTROL.sub("", str(info.get("title") or ""))[:200]
        job.status = "downloading"
        job.progress = 0.05
        source = _download(ydl, info, job.directory)
        if source.stat().st_size > settings.audio_max_bytes:
            raise AudioDownloadError("O ficheiro excede o tamanho máximo.")
        job.status = "converting"
        job.progress = 0.65
        target = job.directory / "audio.mp3"
        duration = info.get("duration") if isinstance(info.get("duration"), (int, float)) else None
        convert_to_mp3(
            source,
            target,
            job.bitrate,
            duration,
            deadline,
            lambda fraction: setattr(job, "progress", 0.65 + 0.35 * fraction),
            lambda: job.cancelled,
            job.title,
        )
        source.unlink(missing_ok=True)  # only the MP3 is kept until it is downloaded
        job.file = target
        job.progress = 1.0
        job.status = "done"
    except AudioDownloadError as exc:
        _fail(job, str(exc))
    except _Stop as exc:
        _fail(job, _STOP_MESSAGES.get(str(exc), "Interrompido."))
    except Exception as exc:  # yt-dlp wraps hook exceptions, and pages can break it in many ways
        stop = next((str(e) for e in _chain(exc) if isinstance(e, _Stop)), None)
        if stop:
            _fail(job, _STOP_MESSAGES.get(stop, "Interrompido."))
        else:
            logger.warning("Audio job failed", exc_info=True)
            _fail(job, "Não foi possível obter o áudio desse endereço.")


_STOP_MESSAGES = {
    "cancelled": "Cancelado.",
    "timeout": "O download demorou demasiado e foi interrompido.",
    "size": "O ficheiro excede o tamanho máximo.",
}


def _chain(exc: BaseException):
    while exc is not None:
        yield exc
        exc = exc.__cause__ or exc.__context__


def _fail(job: Job, message: str) -> None:
    job.status = "cancelled" if job.cancelled else "error"
    job.error = message
    job.file = None
    shutil.rmtree(job.directory, ignore_errors=True)


jobs = JobStore()
