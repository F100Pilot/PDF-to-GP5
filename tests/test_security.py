import pytest

from app.security import RateLimiter, looks_like_pdf, safe_filename


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        (("My Song", "x.pdf"), "My Song.gp5"),
        (("", "../../etc/passwd.pdf"), "passwd.gp5"),
        (("", "C:\\evil\\tab.PDF"), "tab.gp5"),
        (('a"; rm -rf /', ""), "a_ rm -rf.gp5"),
        (("AC/DC - Riff", ""), "AC_DC - Riff.gp5"),
        (("Song (Live)", ""), "Song (Live).gp5"),
        (("\u6f22\u5b57", ""), "tablatura.gp5"),
        (("", ""), "tablatura.gp5"),
    ],
)
def test_safe_filename(candidates, expected):
    assert safe_filename(*candidates) == expected


def test_looks_like_pdf():
    assert looks_like_pdf(b"%PDF-1.7\n...")
    assert looks_like_pdf(b"\x00" * 10 + b"%PDF-1.4")
    assert not looks_like_pdf(b"<html>")
    assert not looks_like_pdf(b"\x00" * 2000 + b"%PDF-1.4")


def test_rate_limiter_blocks_after_limit_and_bounds_memory():
    limiter = RateLimiter(per_minute=2, max_clients=3)
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    for key in "bcdef":
        limiter.allow(key)
    assert len(limiter._hits) == 3


def test_client_key_groups_ipv6_by_64():
    from app.security import client_key

    assert client_key("203.0.113.9") == "203.0.113.9"
    assert client_key("2001:db8:1:2:aaaa::1") == client_key("2001:db8:1:2:bbbb::2") == "2001:db8:1:2::/64"
    assert client_key(None) == "unknown"


# The CSP style hashes in app/security.py were measured for this exact alphaTab build
# (see app/static/vendor/alphatab/README.md): upgrading alphaTab means re-measuring them.
ALPHATAB_SHA256 = "2d0335501b875453d52359de23cd9cebfcf71aed3d5739f1cf95117acfd52bec"


def test_vendored_alphatab_is_the_pinned_build():
    import hashlib
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "app/static/vendor/alphatab/alphaTab.min.js"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ALPHATAB_SHA256


def test_csp_allows_score_viewer_without_unsafe_inline():
    from app.security import ALPHATAB_STYLE_HASHES, CSP

    assert "unsafe-inline" not in CSP and "unsafe-eval" not in CSP
    assert "script-src 'self';" in CSP
    assert "worker-src 'self' blob:;" in CSP
    assert "img-src 'self' data: blob:;" in CSP  # library covers kept in the browser
    assert "frame-src https://www.youtube-nocookie.com https://www.youtube.com;" in CSP
    assert len(ALPHATAB_STYLE_HASHES) == 2
    assert all(f"'{h}'" in CSP for h in ALPHATAB_STYLE_HASHES)


def test_other_sites_cannot_make_the_browser_call_the_api():
    """An <img src="http://127.0.0.1:8021/api/video-search?q=…"> on another site: the answer
    would stay hidden from it, but the request would spend the YouTube key's quota."""
    from fastapi.testclient import TestClient

    from app import main

    client = TestClient(main.app, base_url="http://127.0.0.1:8021")
    for site in ("cross-site", "same-site"):
        response = client.get("/api/health", headers={"Sec-Fetch-Site": site})
        assert response.status_code == 403, site
    for site in ("same-origin", "none"):  # the page itself; the address typed in the browser
        assert client.get("/api/health", headers={"Sec-Fetch-Site": site}).status_code == 200
    assert client.get("/api/health").status_code == 200  # curl, scripts
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200  # a link to the app


def test_a_request_from_elsewhere_to_the_library_is_refused_before_its_body_is_read():
    """The library takes uploads of up to LIBRARY_MAX_AUDIO_MB; only this computer may send them."""
    import asyncio

    from app import main

    async def call(path: str, method: str) -> tuple[int, int]:
        reads, sent = [], []

        async def receive():
            reads.append(1)
            return {"type": "http.request", "body": b"x" * 1024, "more_body": False}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"127.0.0.1:8021"), (b"content-length", b"1024")],
            "client": ("203.0.113.9", 50000),
            "server": ("127.0.0.1", 8021),
        }
        await main.app(scope, receive, send)
        return sent[0]["status"], len(reads)

    assert asyncio.run(call("/api/library/song/audio", "PUT")) == (404, 0)
    assert asyncio.run(call("/api/library", "POST")) == (404, 0)
    assert asyncio.run(call("/api/youtube-key", "POST")) == (403, 0)
