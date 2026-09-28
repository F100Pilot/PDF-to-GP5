"""HTTP hardening: security headers, request size cap, rate limiting, input checks."""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict, deque

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app = app
        self.headers = [
            (b"content-security-policy", CSP.encode()),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
            (b"cross-origin-opener-policy", b"same-origin"),
            (b"cross-origin-resource-policy", b"same-origin"),
        ]
        if hsts:
            self.headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith("/api/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(self.headers)
                if is_api:
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Reject request bodies above ``max_bytes`` without buffering them first."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = self.max_bytes + 1
                if declared > self.max_bytes:
                    await _send_413(send)
                    return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status_code=413, detail="Pedido demasiado grande.")
            return message

        await self.app(scope, limited_receive, send)


async def _send_413(send: Send) -> None:
    body = b'{"detail":"Pedido demasiado grande."}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RateLimiter:
    """Sliding-window limiter keyed by client address, bounded in memory."""

    def __init__(self, per_minute: int, max_clients: int = 10_000) -> None:
        self.per_minute = per_minute
        self.max_clients = max_clients
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.pop(key, None) or deque()
            while hits and now - hits[0] > 60:
                hits.popleft()
            allowed = len(hits) < self.per_minute
            if allowed:
                hits.append(now)
            self._hits[key] = hits
            while len(self._hits) > self.max_clients:
                self._hits.popitem(last=False)
            return allowed


PDF_MAGIC = b"%PDF-"


def looks_like_pdf(head: bytes) -> bool:
    """The PDF header must appear within the first 1024 bytes (ISO 32000-1, 7.5.2)."""
    return PDF_MAGIC in head[:1024]


_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_filename(title: str, upload_name: str, default: str = "tablatura", max_length: int = 80) -> str:
    """Build an ASCII-only download name ending in .gp5 (title first, then upload name)."""
    upload_stem = upload_name.replace("\\", "/").rsplit("/", 1)[-1]
    if upload_stem.lower().endswith(".pdf"):
        upload_stem = upload_stem[:-4]
    for candidate in (title, upload_stem):
        stem = _UNSAFE_FILENAME.sub("_", candidate).strip(" ._-")[:max_length]
        if stem:
            return f"{stem}.gp5"
    return f"{default}.gp5"
