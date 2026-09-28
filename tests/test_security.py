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
