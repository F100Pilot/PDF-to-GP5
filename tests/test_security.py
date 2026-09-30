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
