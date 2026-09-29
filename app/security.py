"""HTTP hardening: security headers, request size cap, rate limiting, input checks."""

from __future__ import annotations

import ipaddress
import re
import threading
import time
from collections import OrderedDict, deque

from fastapi import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The score viewer (vendored alphaTab) injects two fixed <style> blocks (its shared rules and
# the @font-face for its music font); they are allowed by hash, not with 'unsafe-inline'.
# Its audio synthesizer runs in a worker started from a blob: URL that imports alphaTab from 'self'.
ALPHATAB_STYLE_HASHES = (
    "sha256-EIR5s3Qp1PxPxW4Koopu9nVN+I2chNMT0ImH3VG/s+c=",  # shared rules (alphaTabStyleShared)
    "sha256-t9NAmAR13X3WICTwMsEJq4wX4AYLiH6LxxmzV9VkUJ8=",  # @font-face for /vendor/alphatab/font/
)
_STYLE_SOURCES = " ".join(["'self'", *(f"'{h}'" for h in ALPHATAB_STYLE_HASHES)])
CSP = (
    "default-src 'self'; script-src 'self'; "
    f"style-src {_STYLE_SOURCES}; "
    "img-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; "
    # Optional YouTube video beside the score: only the privacy-enhanced embed player may be framed.
    "frame-src https://www.youtube-nocookie.com; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
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
                # API answers are never stored; page files are revalidated on every load
                # (cheap ETag check) so an update shows up without a forced reload.
                headers.append((b"cache-control", b"no-store" if is_api else b"no-cache"))
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


class SameOriginMiddleware:
    """Refuse state-changing requests sent by other web sites.

    A page on any site can make the browser POST a form to http://127.0.0.1:8020;
    browsers then send an Origin header naming that site. Requests without an
    Origin (curl, scripts) are allowed.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in ("GET", "HEAD", "OPTIONS"):
            headers = dict(scope.get("headers", []))
            origin = headers.get(b"origin", b"").decode("latin-1")
            host = headers.get(b"host", b"").decode("latin-1")
            if origin and (origin == "null" or origin.split("://", 1)[-1].rstrip("/") != host):
                body = b'{"detail":"Pedido de outra origem recusado."}'
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def client_key(host: str | None) -> str:
    """Rate-limit key: the IPv4 address, or the /64 network for IPv6 (one home or host)."""
    if not host:
        return "unknown"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


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


_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ ()-]+")


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
