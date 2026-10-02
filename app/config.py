"""Runtime limits and flags, overridable through environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import tr


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


# Optional YouTube Data API key, for finding the song's video automatically: the environment
# variable, else the first line of this file next to the start scripts (never committed).
YOUTUBE_KEY_FILE = Path(__file__).resolve().parent.parent / "youtube_api_key.txt"


_KEY_FORMAT = re.compile(r"[A-Za-z0-9_-]{20,80}")


def _read_key_file() -> tuple[str, str]:
    """(key, problem) from the key file; Notepad may save it with a BOM or as UTF-16."""
    try:
        raw = YOUTUBE_KEY_FILE.read_bytes()
    except FileNotFoundError:
        return "", tr(
            f"não existe o ficheiro {YOUTUBE_KEY_FILE.name} na pasta do projeto",
            f"the file {YOUTUBE_KEY_FILE.name} does not exist in the project folder",
        )
    except OSError:
        return "", tr(
            f"não foi possível ler o ficheiro {YOUTUBE_KEY_FILE.name}",
            f"could not read the file {YOUTUBE_KEY_FILE.name}",
        )
    encoding = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        return "", tr(
            f"o ficheiro {YOUTUBE_KEY_FILE.name} não é texto simples",
            f"the file {YOUTUBE_KEY_FILE.name} is not plain text",
        )
    lines = [line.strip().strip("\"'") for line in text.splitlines() if line.strip()]
    if not lines:
        return "", tr(f"o ficheiro {YOUTUBE_KEY_FILE.name} está vazio", f"the file {YOUTUBE_KEY_FILE.name} is empty")
    if not _KEY_FORMAT.fullmatch(lines[0]):
        return "", tr(
            f"a primeira linha de {YOUTUBE_KEY_FILE.name} não parece uma chave (deve ser só a chave, AIza…)",
            f"the first line of {YOUTUBE_KEY_FILE.name} does not look like a key (it must be just the key, AIza…)",
        )
    return lines[0], ""


def save_youtube_key(key: str) -> bool:
    """Write the key to the key file (from the page, on the computer itself); False when it does
    not look like a key."""
    key = key.strip()
    if not _KEY_FORMAT.fullmatch(key):
        return False
    temporary = YOUTUBE_KEY_FILE.with_name(YOUTUBE_KEY_FILE.name + ".tmp")
    temporary.write_text(key + "\n", encoding="utf-8")
    os.replace(temporary, YOUTUBE_KEY_FILE)
    return True


def youtube_key_status() -> tuple[str, str]:
    """(key, problem): the YouTube Data API key, or "" and why automatic video search is off."""
    value = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if value:
        if _KEY_FORMAT.fullmatch(value):
            return value, ""
        return "", tr(
            "a variável YOUTUBE_API_KEY não parece uma chave", "the YOUTUBE_API_KEY variable does not look like a key"
        )
    return _read_key_file()


def _youtube_key() -> str:
    return youtube_key_status()[0]


@dataclass(frozen=True)
class Settings:
    max_upload_bytes: int = _int("MAX_UPLOAD_MB", 10) * 1024 * 1024
    max_total_upload_bytes: int = _int("MAX_TOTAL_UPLOAD_MB", 40) * 1024 * 1024  # all PDFs of one song
    max_pages: int = _int("MAX_PAGES", 40)
    max_image_pages: int = _int("MAX_IMAGE_PAGES", 15)  # pages read by OCR per file, about 1 s each
    max_image_pixels: int = _int("MAX_IMAGE_MEGAPIXELS", 40) * 1_000_000
    max_events: int = _int("MAX_EVENTS", 50_000)
    conversion_timeout_s: int = _int("CONVERSION_TIMEOUT_S", 30)
    worker_memory_mb: int = _int("WORKER_MEMORY_MB", 2048)  # address space; OCR (onnxruntime) needs ~1.5 GB
    max_concurrent: int = _int("MAX_CONCURRENT_CONVERSIONS", 2)
    rate_limit_per_minute: int = _int("RATE_LIMIT_PER_MINUTE", 20)
    inspect_rate_limit_per_minute: int = _int("INSPECT_RATE_LIMIT_PER_MINUTE", 60)
    max_job_timeout_s: int = _int("MAX_JOB_TIMEOUT_S", 90)  # whole request, however many PDFs
    max_measures: int = _int("MAX_MEASURES", 2000)
    # Host names the server answers to (blocks DNS rebinding); comma separated.
    allowed_hosts: tuple[str, ...] = tuple(
        h.strip() for h in os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]").split(",") if h.strip()
    )
    video_search_per_minute: int = _int("VIDEO_SEARCH_PER_MINUTE", 10)
    cover_search_per_minute: int = _int("COVER_SEARCH_PER_MINUTE", 20)
    youtube_api_key: str = field(default_factory=_youtube_key, repr=False)
    # Audio from a URL (yt-dlp + FFmpeg), for content the user may download.
    audio_jobs_per_minute: int = _int("AUDIO_JOBS_PER_MINUTE", 5)
    audio_concurrent_jobs: int = _int("AUDIO_CONCURRENT_JOBS", 1)
    audio_max_bytes: int = _int("AUDIO_MAX_MB", 200) * 1024 * 1024  # downloaded media and the MP3
    audio_max_duration_s: int = _int("AUDIO_MAX_DURATION_S", 20 * 60)
    audio_timeout_s: int = _int("AUDIO_TIMEOUT_S", 300)  # the whole job: download and conversion
    audio_ttl_s: int = _int("AUDIO_TTL_S", 15 * 60)  # finished jobs not downloaded are deleted after this
    # Sites the owner of this installation publishes on and may download from (own server, NAS…);
    # comma separated host names. Not YouTube: a YouTube video's audio is processed for personal
    # use when the app is used on the computer it runs on, otherwise only if Creative Commons.
    audio_download_hosts: tuple[str, ...] = tuple(
        h.strip().lower() for h in os.environ.get("AUDIO_DOWNLOAD_HOSTS", "").split(",") if h.strip()
    )
    # The song library, when the app is used on the computer it runs on; LIBRARY_DIR changes it.
    library_dir: Path = Path(os.environ.get("LIBRARY_DIR") or Path.home() / "PDF-to-GP5" / "Biblioteca")
    library_max_audio_bytes: int = _int("LIBRARY_MAX_AUDIO_MB", 200) * 1024 * 1024
    enable_docs: bool = _bool("ENABLE_DOCS")
    enable_hsts: bool = _bool("ENABLE_HSTS")


settings = Settings()
