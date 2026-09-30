import base64
import io
import re

import guitarpro as gp
import pytest
from fastapi.testclient import TestClient

from app import main
from app.converter import ConversionError, ConversionOptions
from app.sandbox import GENERIC_ERROR, ConversionTimeout, _decode_reply, run_isolated
from app.security import RateLimiter
from tests.pdf_factory import blank_pdf, engraved_tab_pdf

# One bar on the high E string: 0 3 5 h 7.
TAB = [[(1, 0), (1, 3), (1, 5), (1, 7, "H")]]


def _tab_pdf(**kwargs) -> bytes:
    return engraved_tab_pdf(TAB, **kwargs)


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
    assert len(set(body["track_colors"])) == body["max_tracks"]
    assert all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in body["track_colors"])
    assert "auto" in body["tunings"] and "drop_d" in body["tunings"]
    assert client.get("/api/options").headers["cache-control"] == "no-store"


def test_score_viewer_files_are_served(client):
    page = client.get("/").text
    assert 'id="score-box"' in page and 'src="score.js"' in page
    assert client.get("/score.js").status_code == 200
    assert client.get("/vendor/alphatab/alphaTab.min.js").status_code == 200
    font = client.get("/vendor/alphatab/font/Bravura.woff2")
    assert font.status_code == 200 and font.headers["content-type"] == "font/woff2"
    assert client.get("/vendor/alphatab/soundfont/sonivox.sf3").status_code == 200


def test_3d_highway_files_are_served(client):
    page = client.get("/").text
    assert 'src="highway3d.js"' in page and 'value="3D"' in page and 'id="highway"' in page
    assert (
        'id="highway-legend"' in page
        and 'id="video-panel"' in page
        and 'src="video.js"' in page
        and 'id="score-3d-tilt"' in page
        and 'id="score-3d-side"' in page
    )
    assert client.get("/highway3d.js").status_code == 200
    # ES modules are refused by browsers unless served with a JavaScript MIME type (nosniff).
    for path in ("/vendor/three/three.module.js", "/vendor/three/three.core.js", "/vendor/three/RoundedBoxGeometry.js"):
        response = client.get(path)
        assert response.status_code == 200 and "javascript" in response.headers["content-type"]


def test_audio_for_gp_download_is_offered_and_can_play_locally(client):
    response = client.get("/")
    assert 'id="audio-file"' in response.text and 'src="audio.js"' in response.text
    assert 'id="audio-tempo"' in response.text and 'data-audio-nudge="-1"' in response.text
    # Start nudges on each side of the value: ±1, ±0,1 and ±0,01 s.
    for step in ("-1", "-0.1", "-0.01", "0.01", "0.1", "1"):
        assert f'data-audio-nudge="{step}"' in response.text
    assert "media-src 'self' blob:" in response.headers["content-security-policy"]
    assert client.get("/audio.js").status_code == 200
    # The .gp's audio is renamed "backing-track.<ext>" (gpzip.js), before score.js exports it.
    assert response.text.index('src="gpzip.js"') < response.text.index('src="score.js"')
    assert client.get("/gpzip.js").status_code == 200


def test_favicon(client):
    assert 'rel="icon" href="favicon.svg"' in client.get("/").text
    redirect = client.get("/favicon.ico", follow_redirects=False)
    assert redirect.status_code == 301 and redirect.headers["location"] == "/favicon.svg"
    icon = client.get("/favicon.svg")
    assert icon.status_code == 200 and icon.headers["content-type"].startswith("image/svg+xml")


def test_pages_navigation_and_fonts(client):
    """One page per subject in index.html (shown by nav.js from the URL hash), fonts served locally."""
    page = client.get("/").text
    for name in ("converter", "resultado", "tocar", "audio", "biblioteca", "definicoes"):
        assert f'data-page="{name}"' in page and f'href="#/{name}"' in page
    # theme.js runs before the stylesheet (no flash of the other theme); the others after parsing.
    assert page.index('<script src="theme.js"></script>') < page.index('href="styles.css"')
    for script in ("nav.js", "library.js", "commands.js"):
        assert f'<script src="{script}" defer></script>' in page
    for script in ("theme.js", "nav.js", "library.js", "commands.js"):
        assert (
            client.get(f"/{script}").headers["content-type"].startswith(("text/javascript", "application/javascript"))
        )
    for font in ("ibm-plex-sans.woff2", "sora.woff2"):
        response = client.get(f"/vendor/fonts/{font}")
        assert response.status_code == 200 and response.headers["content-type"] == "font/woff2"


def test_page_files_are_revalidated(client):
    for path in ("/", "/app.js", "/styles.css"):
        assert client.get(path).headers["cache-control"] == "no-cache"


def test_convert_json(client):
    response = _post(client, _tab_pdf(), title="Riff", tempo="90", tuning="drop_d")
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
    response = _post(client, _tab_pdf(), **form)
    assert response.status_code == 200, response.text
    song = gp.parse(io.BytesIO(base64.b64decode(response.json()["gp5_base64"])))
    assert song.measureHeaders[0].timeSignature.numerator == 3
    assert song.tracks[0].channel.instrument == 30


def test_convert_binary(client):
    response = _post(client, _tab_pdf(), path="/api/convert/gp5")
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
    assert _post(client, _tab_pdf(), **form).status_code == 422


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(main, "rate_limiter", RateLimiter(per_minute=1))
    assert _post(client, _tab_pdf()).status_code == 200
    assert _post(client, _tab_pdf()).status_code == 429


def test_sandbox_timeout_kills_worker():
    with pytest.raises(ConversionTimeout):
        run_isolated(_tab_pdf(), ConversionOptions(), timeout_s=0, memory_mb=1024)


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
    result = run_isolated(_tab_pdf(), ConversionOptions(), timeout_s=30, memory_mb=1024)
    assert result.gp5.startswith(b"\x18FICHIER GUITAR PRO") and result.report["notes"] == 4


def test_empty_staves_do_not_vote_and_become_rests(client):
    pdf = engraved_tab_pdf([[[(1, 0)], [(2, 1)]], [[], []]])
    response = _post(client, pdf)
    assert response.status_code == 200, response.text
    report = response.json()["report"]
    assert report["measures"] == 4 and report["warnings"] == []
    assert [d["measures"] for d in report["tracks"][0]["systems_detail"]] == [2, 2]


def test_metadata_is_detected_when_fields_are_left_empty(client):
    pdf = _tab_pdf(extra_lines=["Title: Riff Song", "Artist: The Band", "Tempo: 96"])
    report = _post(client, pdf).json()["report"]
    assert (report["title"], report["artist"], report["tempo"]) == ("Riff Song", "The Band", 96)
    assert report["auto"] == {"title": True, "artist": True, "tempo": True, "time_signature": False}
    assert report["time_signature"] == "4/4"


def test_user_values_override_detection(client):
    pdf = _tab_pdf(extra_lines=["Title: Riff Song", "Tempo: 96"])
    response = _post(client, pdf, title="Mine", tempo="140", time_signature="3/4")
    report = response.json()["report"]
    assert (report["title"], report["tempo"], report["time_signature"]) == ("Mine", 140, "3/4")
    assert response.json()["filename"] == "Mine.gp5"


def test_inspect_returns_detected_metadata_only(client):
    pdf = _tab_pdf(extra_lines=["Title: Riff Song", "Artist: The Band", "Tempo: 96"])
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


def _post_many(client, pdfs, path="/api/convert", **form):
    files = [("file", (name, data, "application/pdf")) for name, data in pdfs]
    return client.post(path, files=files, data=form)


def test_multi_track_song(client):
    guitar = engraved_tab_pdf([TAB, TAB], extra_lines=["Title: Riff Song", "Tempo: 100"])
    bass = engraved_tab_pdf([[(2, 3), (2, 5), (2, 7)]], strings=4)
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
    pdf = _tab_pdf()
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
    pdf = _tab_pdf()
    response = _post_many(client, [("a.pdf", pdf)] * 3, tuning=["standard", "drop_d"])
    assert response.status_code == 422


def test_too_many_tracks(client):
    pdf = _tab_pdf()
    assert _post_many(client, [("a.pdf", pdf)] * 8).status_code == 422


def test_error_names_the_failing_track(client):
    response = _post_many(client, [("ok.pdf", _tab_pdf()), ("scan.pdf", blank_pdf())])
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Track 2 (scan.pdf):")


def test_parenthesized_repeat_is_written_as_a_tie(client):
    pdf = engraved_tab_pdf([[(1, 0), (1, 0, "("), (1, 0), (1, 3)]])  # four quarters
    data = _post(client, pdf).json()["gp5_base64"]
    notes = [
        n for b in gp.parse(io.BytesIO(base64.b64decode(data))).tracks[0].measures[0].voices[0].beats for n in b.notes
    ]
    assert [n.type for n in notes[:3]] == [gp.NoteType.normal, gp.NoteType.tie, gp.NoteType.normal]
    assert not any(n.effect.ghostNote for n in notes[:3])


def test_tracks_are_aligned_by_printed_bar_numbers(client):
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
    response = _post(client, engraved_tab_pdf(TAB, strings=8))
    assert response.status_code == 422
    assert "7" in response.json()["detail"]


def test_cross_site_post_is_refused(client):
    pdf = _tab_pdf()
    files = {"file": ("a.pdf", pdf, "application/pdf")}
    assert client.post("/api/convert", files=files, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/convert", files=files, headers={"Origin": "null"}).status_code == 403
    assert client.post("/api/convert", files=files, headers={"Origin": "http://testserver"}).status_code == 200


def test_unknown_host_is_refused(client):
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400


def test_inspect_has_its_own_rate_budget(client, monkeypatch):
    monkeypatch.setattr(main, "rate_limiter", RateLimiter(per_minute=1))
    pdf = _tab_pdf()
    for _ in range(3):
        assert client.post("/api/inspect", files={"file": ("x.pdf", pdf, "application/pdf")}).status_code == 200
    assert _post(client, pdf).status_code == 200
    assert _post(client, pdf).status_code == 429


def test_huge_printed_bar_number_does_not_create_rest_bars(client):
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
        run_isolated(_tab_pdf(), ConversionOptions(), timeout_s=5, memory_mb=1024)
