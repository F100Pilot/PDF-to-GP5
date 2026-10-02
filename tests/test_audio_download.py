"""Audio from a URL: validation, the "may be downloaded" check, FFmpeg conversion and the job API.

No network: yt-dlp is replaced by fakes; FFmpeg (from imageio-ffmpeg) really converts."""

import dataclasses
import math
import shutil
import struct
import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import audio_download as ad
from app.main import app


def _wav(path: Path, seconds: float = 1.0) -> Path:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        frames = (int(8000 * math.sin(2 * math.pi * 440 * i / 8000)) for i in range(int(8000 * seconds)))
        out.writeframes(b"".join(struct.pack("<h", f) for f in frames))
    return path


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(ad, "_resolve", lambda host: ["127.0.0.1"] if host == "localhost" else ["93.184.216.34"])


# --- URL validation ---


@pytest.mark.parametrize(
    "url",
    ["https://example.com/song.mp3", "http://example.com:8080/a?x=1", "https://nas.example.lan/music/a.ogg"],
)
def test_valid_urls(public_dns, url):
    assert ad.validate_url(f"  {url} ") == url


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("", "Indique"),
        ("ftp://example.com/a.mp3", "http"),
        ("javascript:alert(1)", "http"),
        ("file:///etc/passwd", "http"),
        ("https://user:pw@example.com/a.mp3", "palavra-passe"),
        ("https://example.com/a b.mp3", "espaços"),
        ("https://example.com/a.mp3;rm -rf /", "espaços"),
        ("https://example.com/\x00a.mp3", "caracteres"),
        ("http://localhost/a.mp3", "rede local"),
        ("http://127.0.0.1/a.mp3", "rede local"),
        ("https://example.com/" + "a" * 3000, "longo"),
    ],
)
def test_invalid_urls(public_dns, monkeypatch, url, reason):
    if "127.0.0.1" in url:
        monkeypatch.setattr(ad, "_resolve", lambda host: [host])
    with pytest.raises(ad.AudioDownloadError, match=reason):
        ad.validate_url(url)


def test_private_address_is_refused_unless_declared(monkeypatch):
    monkeypatch.setattr(ad, "_resolve", lambda host: ["192.168.1.20"])
    with pytest.raises(ad.AudioDownloadError, match="rede local"):
        ad.validate_url("http://my-nas/a.mp3")
    assert ad.validate_url("http://nas.example.lan/a.mp3")  # declared in AUDIO_DOWNLOAD_HOSTS


# --- May it be downloaded? ---


@pytest.mark.parametrize(
    ("info", "url", "because"),
    [
        ({"direct": True}, "https://example.com/a.mp3", "direct"),
        (
            {"license": "Creative Commons Attribution license (reuse allowed)"},
            "https://www.youtube.com/watch?v=x",
            "licence",
        ),
        ({"license": "CC0"}, "https://archive.org/details/x", "licence"),
        ({"license": "Public Domain Mark 1.0"}, "https://example.org/x", "licence"),
        ({}, "https://nas.example.lan/page", "declared"),
    ],
)
def test_content_that_may_be_downloaded(info, url, because):
    assert ad.authorize(info, url) == because


@pytest.mark.parametrize(
    ("info", "url", "reason"),
    [
        ({"title": "A song"}, "https://www.youtube.com/watch?v=x", "não está disponível"),
        ({"license": "Standard YouTube License"}, "https://youtu.be/x", "Standard YouTube License"),
        ({"direct": True}, "https://rr1.googlevideo.com/videoplayback", "não está disponível"),
        ({}, "https://example.com/page", "não está disponível"),
    ],
)
def test_content_that_may_not_be_downloaded(info, url, reason):
    with pytest.raises(ad.AudioDownloadError, match=reason):
        ad.authorize(info, url)


@pytest.mark.parametrize(
    ("info", "reason"),
    [
        ({"direct": True, "is_live": True}, "direto"),
        ({"live_status": "is_upcoming"}, "direto"),
        ({"_type": "playlist", "entries": []}, "Listas"),
        ({"direct": True, "duration": 99_999}, "máximo"),
        # Technical limits apply whatever the licence.
        ({"license": "Creative Commons Attribution license (reuse allowed)", "is_live": True}, "direto"),
    ],
)
def test_technical_limits_are_checked_separately(info, reason):
    with pytest.raises(ad.AudioDownloadError, match=reason):
        ad.check_limits(info)


def test_technical_limits_accept_a_single_short_video():
    ad.check_limits({"duration": 180, "license": ""})  # no error; the licence is authorize()'s business


# --- YouTube: only the video id is taken from the user ---


@pytest.mark.parametrize(
    ("text", "video"),
    [
        ("https://www.youtube.com/watch?v=abcDEF12345", "abcDEF12345"),
        ("https://www.youtube.com/watch?v=abcDEF12345&list=PL123&t=42s", "abcDEF12345"),
        ("https://youtu.be/abcDEF12345?si=xyz", "abcDEF12345"),
        ("https://m.youtube.com/shorts/abcDEF12345", "abcDEF12345"),
        ("https://www.youtube-nocookie.com/embed/abcDEF12345", "abcDEF12345"),
        ("https://music.youtube.com/watch?v=abc_EF-2345", "abc_EF-2345"),
        (" abcDEF12345 ", "abcDEF12345"),
        ("https://www.youtube.com/playlist?list=PL123", None),
        ("https://www.youtube.com/@channel", None),
        ("https://www.youtube.com/watch?v=short", None),
        ("https://www.youtube.com/watch?v=abcDEF12345;rm", None),
        ("https://rr1.googlevideo.com/videoplayback?v=abcDEF12345", None),
        ("https://example.com/watch?v=abcDEF12345", None),
        ("javascript:abcDEF12345", None),
    ],
)
def test_youtube_id(text, video):
    assert ad.youtube_id(text) == video


def test_resolve_source_rebuilds_youtube_addresses(public_dns):
    built = "https://www.youtube.com/watch?v=abcDEF12345"
    assert ad.resolve_source("https://youtu.be/abcDEF12345?list=PL1&t=9") == built
    assert ad.resolve_source("abcDEF12345") == built
    with pytest.raises(ad.AudioDownloadError, match="lista de reprodução"):
        ad.resolve_source("https://www.youtube.com/playlist?list=PL123")
    assert ad.resolve_source("https://example.com/a.mp3") == "https://example.com/a.mp3"  # validate_url
    with pytest.raises(ad.AudioDownloadError, match="http"):
        ad.resolve_source("ftp://example.com/a.mp3")
    with pytest.raises(ad.AudioDownloadError):
        ad.youtube_url("../../etc")


def test_js_runtimes_found_on_this_computer(monkeypatch):
    paths = {"node": "/usr/bin/node", "qjs": "/usr/bin/qjs"}
    monkeypatch.setattr(ad.shutil, "which", lambda name: paths.get(name))
    monkeypatch.setattr(ad, "_packaged_deno", lambda: None)
    assert ad.js_runtimes() == {"node": {"path": "/usr/bin/node"}, "quickjs": {"path": "/usr/bin/qjs"}}
    options = ad._options(Path("/tmp"), lambda _: None)
    assert options["js_runtimes"] == ad.js_runtimes() and options["remote_components"] == []
    assert "cookiefile" not in options and "cookiesfrombrowser" not in options and "username" not in options
    monkeypatch.setattr(ad.shutil, "which", lambda name: None)
    assert ad.youtube_ready() == (False, "falta um runtime JavaScript para o YouTube (instale o Deno ou o Node.js)")
    monkeypatch.setattr(ad, "_packaged_deno", lambda: "/venv/bin/deno")  # the "deno" package
    assert ad.js_runtimes() == {"deno": {"path": "/venv/bin/deno"}}


@pytest.mark.parametrize(
    ("info", "url"),
    [
        ({"title": "A song", "license": "Standard YouTube License"}, "https://www.youtube.com/watch?v=x"),
        ({"webpage_url": "https://music.youtube.com/watch?v=x"}, "https://www.youtube.com/watch?v=x"),
    ],
)
def test_a_youtube_video_is_for_personal_use_on_this_computer(info, url):
    assert ad.authorize(info, url, personal=True) == "personal"
    with pytest.raises(ad.AudioDownloadError, match="uso pessoal"):
        ad.authorize(info, url)  # the same video, asked from elsewhere


@pytest.mark.parametrize(
    ("info", "url"),
    [
        ({}, "https://example.com/page"),  # personal use opens YouTube videos, not any site
        ({"direct": True}, "https://rr1.googlevideo.com/videoplayback"),
    ],
)
def test_personal_use_does_not_open_other_content(info, url):
    with pytest.raises(ad.AudioDownloadError, match="não está disponível"):
        ad.authorize(info, url, personal=True)


@pytest.mark.parametrize(
    ("messages", "cause"),
    [
        (
            [
                "[youtube] x: No supported JavaScript runtime could be found.",
                "ERROR: [youtube] x: Sign in to confirm you're not a bot",
            ],
            "runtime",  # the runtime is named first: signing in would not help
        ),
        (["ERROR: [youtube] x: Sign in to confirm you’re not a bot."], "robô"),
        (["ERROR: [youtube] x: Sign in to confirm your age."], "idade"),
        (["ERROR: [youtube] x: Private video. Sign in if you've been granted access"], "privado"),
        (["ERROR: [youtube] x: Video unavailable. This video has been removed"], "não está disponível"),
        (["ERROR: [youtube] x: Requested format is not available."], "Atualize o yt-dlp"),
        (
            [
                (
                    "ERROR: [youtube] x: Unable to download API page: [SSL: CERTIFICATE_VERIFY_FAILED] "
                    "certificate verify failed: self-signed certificate in certificate chain"
                )
            ],
            "certificado",
        ),
        (
            [
                (
                    "ERROR: [youtube] x: Unable to download API page: ('Unable to connect to proxy', "
                    "OSError('Tunnel connection failed: 403 Forbidden'))"
                )
            ],
            "ligação à internet",
        ),
        (
            ["ERROR: [youtube] x: Unable to download API page: <urlopen error [Errno 11001] getaddrinfo failed>"],
            "internet",
        ),
    ],
)
def test_a_failure_says_its_cause(messages, cause):
    assert cause in ad.explain_failure(messages)


def test_an_unrecognised_failure_has_no_invented_cause():
    assert ad.explain_failure(["ERROR: something new"]) is None


def test_the_cause_reaches_the_user_instead_of_a_generic_message(monkeypatch, tmp_path):
    """yt-dlp's warning about the missing runtime used to be switched off (no_warnings) and every
    failure became "Não foi possível ler esse endereço"."""
    import yt_dlp

    class FakeYoutubeDL:
        def __init__(self, params):
            self.params = params
            assert params["no_warnings"] is False

        def extract_info(self, url, download):
            self.params["logger"].warning("[youtube] x: No supported JavaScript runtime could be found.")
            raise yt_dlp.utils.DownloadError("ERROR: [youtube] x: Sign in to confirm you're not a bot")

        def close(self):
            pass

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    with pytest.raises(ad.AudioDownloadError, match="Deno"):
        ad._probe("https://www.youtube.com/watch?v=abcDEF12345", tmp_path, lambda _: None)


def test_youtube_cannot_be_declared_as_own_site(monkeypatch):
    monkeypatch.setattr(ad, "settings", dataclasses.replace(ad.settings, audio_download_hosts=("youtube.com",)))
    with pytest.raises(ad.AudioDownloadError):
        ad.authorize({}, "https://www.youtube.com/watch?v=x")


# --- FFmpeg ---


def test_ffmpeg_converts_to_mp3_with_progress(tmp_path):
    source = _wav(tmp_path / "in.wav", 2.0)
    target = tmp_path / "out.mp3"
    seen = []
    ad.convert_to_mp3(source, target, 128, 2.0, time.monotonic() + 60, seen.append, title='x"; rm -rf / #')
    data = target.read_bytes()
    assert data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)
    assert seen and 0 < max(seen) <= 1


def test_ffmpeg_reports_unreadable_input(tmp_path):
    source = tmp_path / "in.mp3"
    source.write_bytes(b"not audio at all" * 100)
    with pytest.raises(ad.AudioDownloadError, match="FFmpeg"):
        ad.convert_to_mp3(source, tmp_path / "out.mp3", 192, None, time.monotonic() + 60, lambda _: None)


def test_download_name_is_safe():
    assert ad.download_name("../../etc/passwd") == "etc_passwd.mp3"
    assert ad.download_name("Canção: Ação?") == "Cancao_ Acao.mp3"
    assert ad.download_name("") == "audio.mp3"


# --- Job API (yt-dlp faked) ---


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_ytdlp(monkeypatch, public_dns):
    """A direct file whose "download" writes a small WAV into the job's folder."""
    state = {"info": {"direct": True, "title": "Test ../tone", "duration": 1.0}}

    def probe(url, directory, hook):
        return object(), dict(state["info"])

    def download(ydl, info, directory):
        hook_path = _wav(directory / "source.wav", 1.0)
        return hook_path

    monkeypatch.setattr(ad, "_probe", probe)
    monkeypatch.setattr(ad, "_download", download)
    monkeypatch.setattr(ad, "youtube_ready", lambda: (True, ""))
    return state


def _wait(client, job_id, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        body = client.get(f"/api/audio/jobs/{job_id}").json()
        if body["status"] not in ad.ACTIVE:
            return body
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_job_downloads_converts_and_cleans_up(client, fake_ytdlp):
    started = client.post(
        "/api/audio/jobs", json={"url": "https://example.com/tone.wav", "bitrate": 192, "authorized": True}
    )
    assert started.status_code == 202
    job_id = started.json()["id"]
    folder = ad.jobs.get(job_id).directory
    done = _wait(client, job_id)
    assert done["status"] == "done" and done["progress"] == 100 and done["allowed_because"] == "direct"
    assert done["filename"] == "Test _tone.mp3"
    response = client.get(f"/api/audio/jobs/{job_id}/file")
    assert response.status_code == 200 and response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "no-store"
    assert response.content[:3] == b"ID3" or response.content[0] == 0xFF
    assert not folder.exists()  # removed once sent
    assert client.get(f"/api/audio/jobs/{job_id}/file").status_code == 404


def test_job_refused_when_not_downloadable_leaves_nothing(client, fake_ytdlp):
    fake_ytdlp["info"] = {"title": "Song", "license": "Standard YouTube License"}
    job_id = client.post(
        "/api/audio/jobs",
        json={"url": "https://youtu.be/abcDEF12345?list=PL1", "bitrate": 192, "authorized": True},
    ).json()["id"]
    job = ad.jobs.get(job_id)
    folder = job.directory
    assert job.url == "https://www.youtube.com/watch?v=abcDEF12345"  # rebuilt from the id alone
    done = _wait(client, job_id)
    assert done["status"] == "error" and "não está disponível" in done["message"]
    assert not folder.exists()
    assert client.get(f"/api/audio/jobs/{job_id}/file").status_code == 409


def test_a_youtube_videos_audio_on_this_computer_becomes_an_mp3(fake_ytdlp):
    """The page opened at http://127.0.0.1 on the computer the server runs on (start.bat)."""
    local = TestClient(app, base_url="http://127.0.0.1:8020", client=("127.0.0.1", 50000))
    fake_ytdlp["info"] = {"title": "Song", "license": "Standard YouTube License", "duration": 1.0}
    job_id = local.post("/api/audio/jobs", json={"url": "abcDEF12345", "bitrate": 192, "authorized": True}).json()["id"]
    done = _wait(local, job_id)
    assert done["status"] == "done" and done["allowed_because"] == "personal"
    assert local.get(f"/api/audio/jobs/{job_id}/file").status_code == 200


@pytest.mark.parametrize(
    ("base_url", "client_address"),
    [
        ("http://testserver", ("127.0.0.1", 50000)),  # a proxy on this machine, public name
        ("http://127.0.0.1:8020", ("203.0.113.9", 50000)),  # another computer
    ],
)
def test_youtube_from_anywhere_else_stays_creative_commons_only(fake_ytdlp, base_url, client_address):
    other = TestClient(app, base_url=base_url, client=client_address)
    fake_ytdlp["info"] = {"title": "Song", "license": "Standard YouTube License", "duration": 1.0}
    job_id = other.post("/api/audio/jobs", json={"url": "abcDEF12345", "authorized": True}).json()["id"]
    done = _wait(other, job_id)
    assert done["status"] == "error" and "uso pessoal" in done["message"]


def test_youtube_without_its_runtime_is_refused_up_front(client, fake_ytdlp, monkeypatch):
    monkeypatch.setattr(ad, "youtube_ready", lambda: (False, "falta um runtime JavaScript"))
    refused = client.post("/api/audio/jobs", json={"url": "abcDEF12345", "authorized": True})
    assert refused.status_code == 503 and "runtime JavaScript" in refused.json()["detail"]
    ok = client.post("/api/audio/jobs", json={"url": "https://example.com/a.wav", "authorized": True})
    assert ok.status_code == 202  # other addresses do not need it
    _wait(client, ok.json()["id"])


def test_request_validation(client, fake_ytdlp):
    ok = {"url": "https://example.com/a.mp3", "bitrate": 192, "authorized": True}
    assert client.post("/api/audio/jobs", json={**ok, "authorized": False}).status_code == 422
    assert client.post("/api/audio/jobs", json={**ok, "bitrate": 999}).status_code == 422
    bad = client.post("/api/audio/jobs", json={**ok, "url": "file:///etc/passwd"})
    assert bad.status_code == 422 and "http" in bad.json()["detail"]
    assert client.get("/api/audio/jobs/not-a-job").status_code == 404
    assert client.get("/api/audio/jobs/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/audio/jobs/" + "0" * 32 + "/file").status_code == 404


def test_cancel_removes_the_job(client, fake_ytdlp):
    job_id = client.post("/api/audio/jobs", json={"url": "https://example.com/a.wav", "authorized": True}).json()["id"]
    _wait(client, job_id)
    folder = ad.jobs.get(job_id).directory
    assert client.delete(f"/api/audio/jobs/{job_id}").status_code == 204
    assert not folder.exists() and client.get(f"/api/audio/jobs/{job_id}").status_code == 404


def test_health_reports_audio_download(client):
    body = client.get("/api/health").json()
    assert body["audio_download"] is True and body["audio_download_problem"] == ""


def test_real_ytdlp_and_ffmpeg_on_a_direct_file(tmp_path):
    """yt-dlp (not faked) fetches a WAV from a local web server; FFmpeg makes the MP3."""
    import functools
    import http.server
    import tempfile
    import threading

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    _wav(tmp_path / "tone.wav", 1.0)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        job = ad.Job("f" * 32, f"http://127.0.0.1:{server.server_port}/tone.wav", 128, Path(tempfile.mkdtemp()))
        ad.run_job(job)
        assert (job.status, job.reason) == ("done", "direct")
        assert [p.name for p in job.directory.iterdir()] == ["audio.mp3"]  # the download itself is gone
        page = ad.Job("e" * 32, f"http://127.0.0.1:{server.server_port}/", 128, Path(tempfile.mkdtemp()))
        ad.run_job(page)  # a web page without audio
        assert page.status == "error" and not page.directory.exists()
    finally:
        server.shutdown()
        shutil.rmtree(job.directory, ignore_errors=True)
