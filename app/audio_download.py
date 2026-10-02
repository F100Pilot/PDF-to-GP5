"""Audio of a web page or media file the user may download, converted to MP3 (yt-dlp + FFmpeg).

Only content offered for download is processed:

* a direct audio/video file (the server hands out the file itself);
* media published under a Creative Commons or public-domain licence (as the site reports it);
* a site the owner of this installation declares as their own (``AUDIO_DOWNLOAD_HOSTS``);
* the audio of ONE YouTube video for personal use, when the app is used on the computer it runs
  on (``personal``: the request comes from this computer, to a local address — see main.py).

YouTube's terms forbid downloading outside its own features, so on any other request a YouTube
page is processed only when licensed Creative Commons: a copy of this app published on the
internet does not become a YouTube converter for its visitors. No cookies, logins or account
data are ever used, and DRM-protected formats are never selected, so nothing behind
authentication, a paywall or DRM is reachable.

Each job gets its own temporary folder, removed once the MP3 has been downloaded, when the job
fails, or after ``AUDIO_TTL_S``. Downloads and conversions run in a worker thread with a size
limit and a deadline; FFmpeg runs as a separate process with its arguments passed as a list
(never through a shell).
"""

from __future__ import annotations

import contextvars
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
from .i18n import tr

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
        raise AudioDownloadError(
            tr("Indique o endereço (URL) do áudio ou vídeo.", "Enter the address (URL) of the audio or video.")
        )
    if len(url) > MAX_URL_LENGTH:
        raise AudioDownloadError(tr("O endereço é demasiado longo.", "The address is too long."))
    if _CONTROL.search(url) or any(ch.isspace() for ch in url):
        raise AudioDownloadError(
            tr("O endereço tem espaços ou caracteres inválidos.", "The address has spaces or invalid characters.")
        )
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise AudioDownloadError(tr("Endereço inválido.", "Invalid address.")) from exc
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AudioDownloadError(
            tr("O endereço tem de começar por http:// ou https://.", "The address must start with http:// or https://.")
        )
    if parts.username or parts.password:
        raise AudioDownloadError(
            tr(
                "O endereço não pode ter nome de utilizador nem palavra-passe.",
                "The address cannot contain a username or password.",
            )
        )
    if port is not None and not 1 <= port <= 65535:
        raise AudioDownloadError(tr("Endereço inválido.", "Invalid address."))
    host = parts.hostname.lower()
    if not _declared(host):
        try:
            addresses = _resolve(host)
        except OSError as exc:
            raise AudioDownloadError(
                tr(
                    "Não foi possível encontrar esse endereço (verifique o URL e a internet).",
                    "Could not find that address (check the URL and the internet connection).",
                )
            ) from exc
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%")[0])
            if not ip.is_global:
                raise AudioDownloadError(
                    tr(
                        "O endereço aponta para a rede local; só são aceites endereços da internet "
                        "(ou sites declarados em AUDIO_DOWNLOAD_HOSTS).",
                        "The address points to the local network; only internet addresses are accepted "
                        "(or sites declared in AUDIO_DOWNLOAD_HOSTS).",
                    )
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
        raise AudioDownloadError(tr("Identificador de vídeo do YouTube inválido.", "Invalid YouTube video ID."))
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
        raise AudioDownloadError(
            tr(
                "Indique um vídeo do YouTube (não uma lista de reprodução nem um canal).",
                "Enter a YouTube video (not a playlist or a channel).",
            )
        )
    return validate_url(text)


# --- Technical limits (whatever the content) -------------------------------------------------------


def check_limits(info: dict) -> None:
    """Refuse playlists, live streams and media longer than the limit (before any download)."""
    if info.get("_type") in ("playlist", "multi_video") or info.get("entries") is not None:
        raise AudioDownloadError(
            tr(
                "Listas de reprodução não são suportadas: indique um único ficheiro ou vídeo.",
                "Playlists are not supported: enter a single file or video.",
            )
        )
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        raise AudioDownloadError(tr("Emissões em direto não são suportadas.", "Live streams are not supported."))
    duration = info.get("duration")
    if isinstance(duration, (int, float)) and duration > settings.audio_max_duration_s:
        raise AudioDownloadError(
            tr(
                f"O áudio tem {round(duration / 60)} min; o máximo é {settings.audio_max_duration_s // 60} min.",
                f"The audio is {round(duration / 60)} min long; the maximum is {settings.audio_max_duration_s // 60} min.",
            )
        )


# --- May this content be downloaded? ---------------------------------------------------------------


def authorize(info: dict, url: str, personal: bool = False) -> str:
    """Why the content may be downloaded ("direct", "licence", "declared" or "personal"), or
    raise with the reason it may not. ``info`` is yt-dlp's description of the page (no download
    yet); the technical limits are checked separately (check_limits). ``personal``: the app is
    used on the computer it runs on, where a YouTube video's audio is for personal use."""
    page = info.get("webpage_url") or url
    host = (urlsplit(page).hostname or "").lower()
    licence = str(info.get("license") or "").strip()
    if _FREE_LICENCE.search(licence):
        return "licence"
    if personal and _is_youtube(host) and not host.endswith("googlevideo.com"):
        return "personal"
    if info.get("direct") and not _is_youtube(host):
        return "direct"
    if _declared(host):
        return "declared"
    detail = tr(f" (licença indicada: {licence[:80]})", f" (license given: {licence[:80]})") if licence else ""
    youtube = (
        tr(
            " Vídeos do YouTube só são processados para uso pessoal, com a aplicação aberta no próprio "
            "computador onde corre.",
            " YouTube videos are only processed for personal use, with the app open on the computer it runs on.",
        )
        if _is_youtube(host)
        else ""
    )
    raise AudioDownloadError(
        tr(
            "Este conteúdo não está disponível para download: não é um ficheiro direto nem tem licença "
            f"Creative Commons ou de domínio público{detail}. Só é processado conteúdo que pode ser "
            f"descarregado (ficheiros seus, Creative Commons, domínio público).{youtube}",
            "This content is not available for download: it is not a direct file and has no "
            f"Creative Commons or public-domain license{detail}. Only content that may be downloaded "
            f"is processed (your own files, Creative Commons, public domain).{youtube}",
        )
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
        return False, tr(
            "falta o yt-dlp (pip install -r requirements.txt)", "yt-dlp is missing (pip install -r requirements.txt)"
        )
    if not ffmpeg_path():
        return False, tr(
            "falta o FFmpeg (pip install -r requirements.txt instala o imageio-ffmpeg)",
            "FFmpeg is missing (pip install -r requirements.txt installs imageio-ffmpeg)",
        )
    return True, ""


# JavaScript runtimes yt-dlp can use for YouTube, highest priority first, with their program names.
_JS_RUNTIMES = (("deno", ("deno",)), ("node", ("node",)), ("quickjs", ("qjs", "quickjs")), ("bun", ("bun",)))


def _packaged_deno() -> str | None:
    """Deno installed in the app's own Python environment (requirements.txt: the "deno" package),
    which is not on the PATH when the app runs from its virtual environment."""
    try:
        from deno import find_deno_bin

        return find_deno_bin()
    except (ImportError, OSError):
        return None


def js_runtimes() -> dict[str, dict]:
    """The JavaScript runtimes installed on this computer, as yt-dlp's ``js_runtimes`` option."""
    found: dict[str, dict] = {}
    for name, programs in _JS_RUNTIMES:
        path = next((p for p in map(shutil.which, programs) if p), None)
        if name == "deno" and not path:
            path = _packaged_deno()
        if path:
            found[name] = {"path": path}
    return found


def youtube_ready() -> tuple[bool, str]:
    """(ready, problem): YouTube needs the yt-dlp-ejs scripts and a JavaScript runtime."""
    try:
        import yt_dlp_ejs  # noqa: F401
    except ImportError:
        return False, tr(
            "falta o yt-dlp-ejs (pip install -r requirements.txt instala o yt-dlp[default])",
            "yt-dlp-ejs is missing (pip install -r requirements.txt installs yt-dlp[default])",
        )
    if not js_runtimes():
        return False, tr(
            "falta um runtime JavaScript para o YouTube (instale o Deno ou o Node.js)",
            "a JavaScript runtime for YouTube is missing (install Deno or Node.js)",
        )
    return True, ""


class _Stop(Exception):
    """Raised from yt-dlp's progress hook to stop a download (limit reached or cancelled)."""


class _QuietLogger:
    """yt-dlp messages go to our log (never to the page: they may contain the URL). Warnings and
    errors are also kept, so a failure can say its cause (explain_failure) instead of a generic
    message."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def debug(self, message: str) -> None:
        logger.debug("yt-dlp: %s", message)

    def info(self, message: str) -> None:
        logger.debug("yt-dlp: %s", message)

    def warning(self, message: str) -> None:
        logger.info("yt-dlp: %s", message)
        self.messages.append(message)

    def error(self, message: str) -> None:
        logger.info("yt-dlp: %s", message)
        self.messages.append(message)


def _failure_causes() -> tuple[tuple[tuple[str, ...], str], ...]:
    """What yt-dlp says, lower case → the cause shown to the user, first match wins. A missing
    JavaScript runtime comes first: without one YouTube refuses in a way that also reads like
    "sign in", and signing in would not help. A function, so the texts follow the request's language."""
    return (
        (
            ("no supported javascript runtime", "challenge solving failed", "signature solving failed"),
            tr(
                "O YouTube exige resolver um desafio em JavaScript e falta o runtime: instale o Deno "
                "(winget install DenoLand.Deno) ou o Node.js, confirme que o yt-dlp[default] está "
                "instalado (pip install -r requirements.txt) e reinicie a aplicação.",
                "YouTube requires solving a JavaScript challenge and the runtime is missing: install Deno "
                "(winget install DenoLand.Deno) or Node.js, make sure yt-dlp[default] is installed "
                "(pip install -r requirements.txt) and restart the app.",
            ),
        ),
        (
            ("confirm your age", "age-restricted", "inappropriate for some users"),
            tr(
                "O vídeo tem restrição de idade: o YouTube só o mostra com sessão iniciada.",
                "The video is age-restricted: YouTube only shows it to signed-in users.",
            ),
        ),
        (
            ("not a bot",),
            tr(
                "O YouTube pediu para confirmar que não é um robô (acontece a pedidos sem sessão "
                "iniciada, que esta aplicação não usa). Tente mais tarde ou noutra rede.",
                "YouTube asked to confirm you are not a robot (it happens to requests without a "
                "signed-in session, which this app does not use). Try later or on another network.",
            ),
        ),
        (("private video",), tr("O vídeo é privado.", "The video is private.")),
        (
            ("requested format is not available", "only images are available"),
            tr(
                "O YouTube não entregou nenhum formato de áudio. Atualize o yt-dlp (pip install -U "
                '"yt-dlp[default]") e confirme que tem o Deno ou o Node.js instalado.',
                "YouTube did not deliver any audio format. Update yt-dlp (pip install -U "
                '"yt-dlp[default]") and make sure Deno or Node.js is installed.',
            ),
        ),
        (
            ("video unavailable", "not available in your country", "has been removed"),
            tr(
                "O vídeo não está disponível (removido, privado ou bloqueado neste país).",
                "The video is not available (removed, private or blocked in this country).",
            ),
        ),
        (
            ("certificate verify failed",),
            tr(
                "A ligação segura ao site foi recusada (certificado inválido): confirme a data e a hora "
                "do computador e se um antivírus ou proxy está a inspecionar as ligações HTTPS.",
                "The secure connection to the site was refused (invalid certificate): check the "
                "computer's date and time and whether an antivirus or proxy is inspecting HTTPS connections.",
            ),
        ),
        (
            (
                "unable to connect to proxy",
                "getaddrinfo failed",
                "name or service not known",
                "temporary failure in name resolution",
                "failed to resolve",
                "connection refused",
                "network is unreachable",
                "timed out",
            ),
            tr(
                "Não foi possível ligar ao site: confirme a ligação à internet (ou a firewall/proxy).",
                "Could not connect to the site: check the internet connection (or the firewall/proxy).",
            ),
        ),
    )


def explain_failure(messages: list[str]) -> str | None:
    """The cause of a failed yt-dlp run, from what it printed; None when it is not recognised."""
    text = " ".join(messages).lower()
    for hints, cause in _failure_causes():
        if any(hint in text for hint in hints):
            return cause
    return None


def _messages(ydl: object, exc: BaseException) -> list[str]:
    log = getattr(ydl, "params", {}).get("logger")
    return [*getattr(log, "messages", []), str(exc)]


def _options(directory: Path, hook: Callable[[dict], None]) -> dict:
    return {
        "format": "bestaudio/best",
        "outtmpl": {"default": str(directory / "source.%(ext)s")},
        "paths": {"home": str(directory), "temp": str(directory)},
        "noplaylist": True,
        "quiet": True,
        # Warnings reach our logger only (never the page); they carry the cause of a YouTube refusal.
        "no_warnings": False,
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
            explain_failure(_messages(ydl, exc))
            or tr(
                "Não foi possível ler esse endereço (página não suportada, conteúdo protegido ou sem áudio).",
                "Could not read that address (unsupported page, protected content or no audio).",
            )
        ) from exc
    return ydl, info or {}


def _download(ydl: object, info: dict, directory: Path) -> Path:
    """Download the chosen audio into ``directory`` (monkeypatched in tests)."""
    import yt_dlp

    try:
        ydl.process_info(info)
    except yt_dlp.utils.DownloadError as exc:
        raise AudioDownloadError(
            explain_failure(_messages(ydl, exc)) or tr("O download falhou.", "The download failed.")
        ) from exc
    finally:
        ydl.close()
    root = directory.resolve()
    files = [
        p
        for p in directory.glob("source.*")
        if p.is_file() and not p.is_symlink() and not p.name.endswith(".part") and p.resolve().parent == root
    ]
    if not files:
        raise AudioDownloadError(
            tr(
                "O download não produziu nenhum ficheiro (talvez tenha excedido o tamanho máximo).",
                "The download produced no file (it may have exceeded the maximum size).",
            )
        )
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
        raise AudioDownloadError(tr("O FFmpeg não está disponível.", "FFmpeg is not available."))
    if bitrate not in BITRATES:
        raise AudioDownloadError(tr("Qualidade inválida.", "Invalid quality."))
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
        raise AudioDownloadError(tr("Cancelado.", "Cancelled."))
    if time.monotonic() >= deadline:
        raise AudioDownloadError(
            tr("A conversão demorou demasiado e foi interrompida.", "The conversion took too long and was stopped.")
        )
    if process.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        raise AudioDownloadError(
            tr(
                "O FFmpeg não conseguiu converter o áudio (o ficheiro não tem áudio legível).",
                "FFmpeg could not convert the audio (the file has no readable audio).",
            )
        )
    if target.stat().st_size > settings.audio_max_bytes:
        raise AudioDownloadError(tr("O MP3 excede o tamanho máximo.", "The MP3 exceeds the maximum size."))


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
    reason: str = ""  # why it may be downloaded: direct / licence / declared / personal
    personal: bool = False  # used on the computer the app runs on (see authorize)
    file: Path | None = None
    cancelled: bool = False

    def public(self) -> dict:
        messages = {
            "queued": tr("Na fila…", "Queued…"),
            "checking": tr(
                "A verificar o endereço e se o conteúdo pode ser descarregado…",
                "Checking the address and whether the content may be downloaded…",
            ),
            "downloading": tr("A descarregar…", "Downloading…"),
            "converting": tr("A converter para MP3…", "Converting to MP3…"),
            "done": tr("Pronto.", "Done."),
            "error": self.error,
            "cancelled": tr("Cancelado.", "Cancelled."),
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

    def create(self, url: str, bitrate: int, personal: bool = False) -> Job:
        directory = Path(tempfile.mkdtemp(prefix=TEMP_PREFIX))
        job = Job(uuid.uuid4().hex, url, bitrate, directory, personal=personal)
        with self._lock:
            self._jobs[job.id] = job
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=settings.audio_concurrent_jobs, thread_name_prefix="audio")
        # In a copy of this request's context, so the job's errors are written in the user's language.
        self._executor.submit(contextvars.copy_context().run, run_job, job)
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
            job.reason = authorize(info, job.url, job.personal)
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
            raise AudioDownloadError(tr("O ficheiro excede o tamanho máximo.", "The file exceeds the maximum size."))
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
        _fail(job, _stop_message(str(exc)))
    except Exception as exc:  # yt-dlp wraps hook exceptions, and pages can break it in many ways
        stop = next((str(e) for e in _chain(exc) if isinstance(e, _Stop)), None)
        if stop:
            _fail(job, _stop_message(stop))
        else:
            logger.warning("Audio job failed", exc_info=True)
            _fail(
                job, tr("Não foi possível obter o áudio desse endereço.", "Could not get the audio from that address.")
            )


def _stop_message(reason: str) -> str:
    """The message for a download stopped from the progress hook (see _Stop)."""
    messages = {
        "cancelled": tr("Cancelado.", "Cancelled."),
        "timeout": tr(
            "O download demorou demasiado e foi interrompido.", "The download took too long and was stopped."
        ),
        "size": tr("O ficheiro excede o tamanho máximo.", "The file exceeds the maximum size."),
    }
    return messages.get(reason) or tr("Interrompido.", "Interrupted.")


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
