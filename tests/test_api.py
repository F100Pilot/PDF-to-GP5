import base64
import io

import guitarpro as gp
import pytest
from fastapi.testclient import TestClient

from app import main
from app.converter import ConversionError, ConversionOptions
from app.sandbox import GENERIC_ERROR, ConversionTimeout, _decode_reply, run_isolated
from app.security import RateLimiter
from tests.pdf_factory import ascii_tab_pdf, blank_pdf

TAB = [
    "e|-0---3---5h7---|",
    "B|---------------|",
    "G|---------------|",
    "D|---------------|",
    "A|---------------|",
    "E|---------------|",
]


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def _post(client, data: bytes, path="/api/convert", **form):
    return client.post(path, files={"file": ("my tab.pdf", data, "application/pdf")}, data=form)


def test_index_and_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "PDF" in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_docs_disabled_by_default(client):
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


def test_options(client):
    body = client.get("/api/options").json()
    assert "auto" in body["tunings"] and "drop_d" in body["tunings"]
    assert client.get("/api/options").headers["cache-control"] == "no-store"


def test_convert_json(client):
    response = _post(client, ascii_tab_pdf([TAB]), title="Riff", tempo="90", tuning="drop_d")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filename"] == "Riff.gp5"
    assert body["report"]["measures"] == 1 and body["report"]["notes"] == 4
    song = gp.parse(io.BytesIO(base64.b64decode(body["gp5_base64"])))
    assert song.title == "Riff" and song.tempo == 90
    assert song.tracks[0].strings[5].value == 38


def test_convert_with_every_form_field_as_browser_sends_it(client):
    form = {
        "title": "Riff",
        "artist": "",
        "tempo": "120",
        "tuning": "auto",
        "instrument": "distortion",
        "time_signature": "3/4",
        "rhythm_mode": "fixed",
        "fixed_value": "8",
    }
    response = _post(client, ascii_tab_pdf([TAB]), **form)
    assert response.status_code == 200, response.text
    song = gp.parse(io.BytesIO(base64.b64decode(response.json()["gp5_base64"])))
    assert song.measureHeaders[0].timeSignature.numerator == 3
    assert song.tracks[0].channel.instrument == 30


def test_convert_binary(client):
    response = _post(client, ascii_tab_pdf([TAB]), path="/api/convert/gp5")
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="my tab.gp5"'
    assert response.content.startswith(b"\x18FICHIER GUITAR PRO v5.10")


def test_rejects_non_pdf(client):
    assert _post(client, b"<html>not a pdf</html>").status_code == 415


def test_rejects_too_large(client):
    response = _post(client, b"%PDF-" + b"0" * (2 * 1024 * 1024))
    assert response.status_code == 413


def test_scanned_pdf_reports_no_text(client):
    response = _post(client, blank_pdf())
    assert response.status_code == 422
    assert "OCR" in response.json()["detail"]


def test_corrupt_pdf(client):
    response = _post(client, b"%PDF-1.4\n garbage")
    assert response.status_code == 422


@pytest.mark.parametrize(
    "form",
    [
        {"tuning": "nope"},
        {"instrument": "kazoo"},
        {"tempo": "5"},
        {"time_signature": "3/5"},
        {"time_signature": "0/4"},
        {"time_signature": "17/4"},
        {"time_signature": "four"},
        {"fixed_value": "5"},
        {"rhythm_mode": "x"},
        {"title": "x" * 101},
    ],
)
def test_invalid_options(client, form):
    assert _post(client, ascii_tab_pdf([TAB]), **form).status_code == 422


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(main, "rate_limiter", RateLimiter(per_minute=1))
    assert _post(client, ascii_tab_pdf([TAB])).status_code == 200
    assert _post(client, ascii_tab_pdf([TAB])).status_code == 429


def test_sandbox_timeout_kills_worker():
    with pytest.raises(ConversionTimeout):
        run_isolated(ascii_tab_pdf([TAB]), ConversionOptions(), timeout_s=0, memory_mb=1024)


def test_sandbox_propagates_user_errors():
    with pytest.raises(ConversionError, match="OCR"):
        run_isolated(blank_pdf(), ConversionOptions(), timeout_s=30, memory_mb=1024)


def test_rejects_oversized_chunked_body_without_content_length(client):
    def body():
        for _ in range(40):
            yield b"0" * 65536

    response = client.post("/api/convert", content=body(), headers={"content-type": "multipart/form-data; boundary=x"})
    assert response.status_code == 413


@pytest.mark.parametrize("raw", [b"not json", b'{"status": "ok"}', b'{"status": "ok", "gp5": "!!", "report": {}}'])
def test_sandbox_rejects_malformed_replies(raw):
    with pytest.raises(ConversionError, match=GENERIC_ERROR):
        _decode_reply(raw)


def test_sandbox_success_roundtrip():
    result = run_isolated(ascii_tab_pdf([TAB]), ConversionOptions(), timeout_s=30, memory_mb=1024)
    assert result.gp5.startswith(b"\x18FICHIER GUITAR PRO") and result.report["notes"] == 4


def test_empty_staves_do_not_vote_and_become_rests(client):
    from tests.pdf_factory import engraved_tab_pdf

    pdf = engraved_tab_pdf([[[(1, 0)], [(2, 1)]], [[], []]])
    response = _post(client, pdf)
    assert response.status_code == 200, response.text
    report = response.json()["report"]
    assert report["measures"] == 4 and report["warnings"] == []
    assert [d["measures"] for d in report["systems_detail"]] == [2, 2]


def test_metadata_is_detected_when_fields_are_left_empty(client):
    pdf = ascii_tab_pdf([TAB], extra_lines=["Title: Riff Song", "Artist: The Band", "Tempo: 96"])
    report = _post(client, pdf).json()["report"]
    assert (report["title"], report["artist"], report["tempo"]) == ("Riff Song", "The Band", 96)
    assert report["auto"] == {"title": True, "artist": True, "tempo": True, "time_signature": False}
    assert report["time_signature"] == "4/4"


def test_user_values_override_detection(client):
    pdf = ascii_tab_pdf([TAB], extra_lines=["Title: Riff Song", "Tempo: 96"])
    response = _post(client, pdf, title="Mine", tempo="140", time_signature="3/4")
    report = response.json()["report"]
    assert (report["title"], report["tempo"], report["time_signature"]) == ("Mine", 140, "3/4")
    assert response.json()["filename"] == "Mine.gp5"
