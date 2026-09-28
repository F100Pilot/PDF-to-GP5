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
    assert [d["measures"] for d in report["tracks"][0]["systems_detail"]] == [2, 2]


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


def test_inspect_returns_detected_metadata_only(client):
    pdf = ascii_tab_pdf([TAB], extra_lines=["Title: Riff Song", "Artist: The Band", "Tempo: 96"])
    response = client.post("/api/inspect", files={"file": ("x.pdf", pdf, "application/pdf")})
    assert response.status_code == 200
    assert response.json() == {
        "title": "Riff Song",
        "artist": "The Band",
        "tempo": 96,
        "time_signature": None,
        "part_name": None,
        "strings": 6,
        "tuning": "standard",
    }


def test_inspect_validates_upload(client):
    response = client.post("/api/inspect", files={"file": ("x.pdf", b"<html>", "application/pdf")})
    assert response.status_code == 415
    assert client.post("/api/inspect", files={"file": ("x.pdf", blank_pdf(), "application/pdf")}).status_code == 422


def test_changelog_endpoint(client):
    from app import __version__

    body = client.get("/api/changelog").json()
    assert body["version"] == __version__
    assert body["releases"][0]["version"] == __version__
    assert all(r["version"] != "Unreleased" for r in body["releases"])


BASS = ["G|-------------|", "D|-------------|", "A|-3---5---7---|", "E|-------------|"]


def _post_many(client, pdfs, path="/api/convert", **form):
    files = [("file", (name, data, "application/pdf")) for name, data in pdfs]
    return client.post(path, files=files, data=form)


def test_multi_track_song(client):
    guitar = ascii_tab_pdf([TAB, TAB], extra_lines=["Title: Riff Song", "Tempo: 100"])
    bass = ascii_tab_pdf([[line.replace("|", "|--", 1) for line in BASS]])
    response = _post_many(client, [("Riff Song - Lead.pdf", guitar), ("Riff Song - Bass.pdf", bass)])
    assert response.status_code == 200, response.text
    body = response.json()
    report = body["report"]
    assert [t["name"] for t in report["tracks"]] == ["Lead", "Bass"]
    assert [t["strings"] for t in report["tracks"]] == [6, 4]
    assert report["measures"] == 2 and report["tempo"] == 100
    assert any("Bass:" in w and "pausa" in w for w in report["warnings"])  # bass padded to 2 bars
    song = gp.parse(io.BytesIO(base64.b64decode(body["gp5_base64"])))
    assert [t.name for t in song.tracks] == ["Lead", "Bass"]
    assert [len(t.measures) for t in song.tracks] == [2, 2]
    assert song.tracks[1].channel.instrument == 33
    channels = [c for t in song.tracks for c in (t.channel.channel, t.channel.effectChannel)]
    assert len(set(channels)) == 4 and 9 not in channels


def test_per_track_options(client):
    pdf = ascii_tab_pdf([TAB])
    response = _post_many(
        client,
        [("a.pdf", pdf), ("b.pdf", pdf)],
        track_name=["Rhythm", "Lead"],
        tuning=["drop_d", "standard"],
        instrument=["distortion", "clean"],
    )
    assert response.status_code == 200, response.text
    tracks = response.json()["report"]["tracks"]
    assert [(t["name"], t["tuning"], t["instrument"]) for t in tracks] == [
        ("Rhythm", "drop_d", "distortion"),
        ("Lead", "standard", "clean"),
    ]


def test_per_track_option_count_must_match(client):
    pdf = ascii_tab_pdf([TAB])
    response = _post_many(client, [("a.pdf", pdf)] * 3, tuning=["standard", "drop_d"])
    assert response.status_code == 422


def test_too_many_tracks(client):
    pdf = ascii_tab_pdf([TAB])
    assert _post_many(client, [("a.pdf", pdf)] * 8).status_code == 422


def test_error_names_the_failing_track(client):
    response = _post_many(client, [("ok.pdf", ascii_tab_pdf([TAB])), ("scan.pdf", blank_pdf())])
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Track 2 (scan.pdf):")


def test_parenthesized_repeat_is_written_as_a_tie(client):
    pdf = ascii_tab_pdf([["e|-0---(0)---0---|", *TAB[1:]]])
    data = _post(client, pdf).json()["gp5_base64"]
    notes = [
        n for b in gp.parse(io.BytesIO(base64.b64decode(data))).tracks[0].measures[0].voices[0].beats for n in b.notes
    ]
    assert [n.type for n in notes[:3]] == [gp.NoteType.normal, gp.NoteType.tie, gp.NoteType.normal]
    assert not any(n.effect.ghostNote for n in notes[:3])


def test_tracks_are_aligned_by_printed_bar_numbers(client):
    from tests.pdf_factory import engraved_tab_pdf

    full = engraved_tab_pdf(
        [[[(1, 0)], [(1, 1)], [(1, 2)]], [[(1, 3)], [(1, 4)], [(1, 5)]]], bar_numbers=[[1, 2, 3], [4, 5, 6]]
    )
    # Second track: the line with bars 3-4 was not read, so its bars 5-6 must not slide to 3-4.
    gappy = engraved_tab_pdf([[[(2, 7)], [(2, 7)]], [[(2, 9)], [(2, 9)]]], bar_numbers=[[1, 2], [5, 6]])
    response = _post_many(client, [("a.pdf", full), ("b.pdf", gappy)])
    assert response.status_code == 200, response.text
    report = response.json()["report"]
    assert report["measures"] == 6
    assert report["tracks"][1]["missing_bars"] == [3, 4]
    assert any("3–4" in w for w in report["warnings"])
    song = gp.parse(io.BytesIO(base64.b64decode(response.json()["gp5_base64"])))
    frets = [[n.value for b in m.voices[0].beats for n in b.notes] for m in song.tracks[1].measures]
    assert frets == [[7], [7], [], [], [9], [9]]


def test_eight_string_tab_is_rejected_with_clear_message(client):
    eight = [*TAB, "B|---------------|", "F#|--------------|"]
    response = _post(client, ascii_tab_pdf([eight]))
    assert response.status_code == 422
    assert "7" in response.json()["detail"]


def test_cross_site_post_is_refused(client):
    pdf = ascii_tab_pdf([TAB])
    files = {"file": ("a.pdf", pdf, "application/pdf")}
    assert client.post("/api/convert", files=files, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/convert", files=files, headers={"Origin": "null"}).status_code == 403
    assert client.post("/api/convert", files=files, headers={"Origin": "http://testserver"}).status_code == 200


def test_unknown_host_is_refused(client):
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400


def test_inspect_has_its_own_rate_budget(client, monkeypatch):
    monkeypatch.setattr(main, "rate_limiter", RateLimiter(per_minute=1))
    pdf = ascii_tab_pdf([TAB])
    for _ in range(3):
        assert client.post("/api/inspect", files={"file": ("x.pdf", pdf, "application/pdf")}).status_code == 200
    assert _post(client, pdf).status_code == 200
    assert _post(client, pdf).status_code == 429


def test_huge_printed_bar_number_does_not_create_rest_bars(client):
    from tests.pdf_factory import engraved_tab_pdf

    pdf = engraved_tab_pdf([[[(1, 0)], [(1, 2)]]], bar_numbers=[[1, 300000]])
    response = _post(client, pdf)
    assert response.status_code == 200, response.text
    assert response.json()["report"]["measures"] == 2


def test_sandbox_start_failure_is_reported_as_unavailable(monkeypatch):
    from app import sandbox

    class Broken:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise OSError("too many processes")

    monkeypatch.setattr(sandbox._CTX, "Process", Broken)
    with pytest.raises(sandbox.ConversionUnavailable):
        run_isolated(ascii_tab_pdf([TAB]), ConversionOptions(), timeout_s=5, memory_mb=1024)
