"""Runtime limits and flags, overridable through environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


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


@dataclass(frozen=True)
class Settings:
    max_upload_bytes: int = _int("MAX_UPLOAD_MB", 10) * 1024 * 1024
    max_total_upload_bytes: int = _int("MAX_TOTAL_UPLOAD_MB", 40) * 1024 * 1024  # all PDFs of one song
    max_pages: int = _int("MAX_PAGES", 40)
    max_events: int = _int("MAX_EVENTS", 50_000)
    conversion_timeout_s: int = _int("CONVERSION_TIMEOUT_S", 30)
    worker_memory_mb: int = _int("WORKER_MEMORY_MB", 1024)
    max_concurrent: int = _int("MAX_CONCURRENT_CONVERSIONS", 2)
    rate_limit_per_minute: int = _int("RATE_LIMIT_PER_MINUTE", 20)
    inspect_rate_limit_per_minute: int = _int("INSPECT_RATE_LIMIT_PER_MINUTE", 60)
    max_job_timeout_s: int = _int("MAX_JOB_TIMEOUT_S", 90)  # whole request, however many PDFs
    max_measures: int = _int("MAX_MEASURES", 2000)
    # Host names the server answers to (blocks DNS rebinding); comma separated.
    allowed_hosts: tuple[str, ...] = tuple(
        h.strip() for h in os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]").split(",") if h.strip()
    )
    enable_docs: bool = _bool("ENABLE_DOCS")
    enable_hsts: bool = _bool("ENABLE_HSTS")


settings = Settings()
