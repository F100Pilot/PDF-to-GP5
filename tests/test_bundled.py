"""The Windows program (PyInstaller): the programs in the bundle, the user's data outside the
program folder, nothing to install, and the launcher."""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import audio_download, bundled, installer, launcher


@pytest.fixture
def frozen(monkeypatch, tmp_path):
    """A bundle in tmp_path with ffmpeg and deno, as PyInstaller lays it out."""
    suffix = ".exe" if sys.platform == "win32" else ""
    for name in ("ffmpeg", "deno"):
        (tmp_path / name).mkdir()
        (tmp_path / name / f"{name}{suffix}").write_bytes(b"")
    monkeypatch.setattr(bundled, "FROZEN", True)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    return tmp_path


def test_the_bundled_programs_come_first(frozen):
    assert audio_download.ffmpeg_path() == str(next((frozen / "ffmpeg").iterdir()))
    assert audio_download._packaged_deno() == str(next((frozen / "deno").iterdir()))


def test_outside_the_bundle_nothing_is_found_there(monkeypatch):
    monkeypatch.setattr(bundled, "FROZEN", False)
    assert bundled.program("ffmpeg") is None


def test_the_user_data_is_in_local_app_data_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(bundled.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert bundled.user_data_dir() == tmp_path / "PDF-to-GP5"


def test_the_installed_program_installs_nothing(monkeypatch):
    monkeypatch.setattr(installer, "FROZEN", True)
    ran = []
    monkeypatch.setattr(installer.subprocess, "run", lambda *a, **k: ran.append(a))
    job = installer.Installation()
    job._run()
    assert job.state == "failed" and not ran
    assert "inclui tudo" in " ".join(job.log)


class _Health(BaseHTTPRequestHandler):
    body = b""

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


@pytest.mark.parametrize(
    ("body", "ours"),
    [
        (json.dumps({"status": "ok", "ocr": True}).encode(), True),
        (json.dumps({"status": "ok"}).encode(), False),  # another program's health check
        (b"<html>", False),
    ],
)
def test_the_launcher_knows_its_own_server(body, ours):
    """Opened twice, the second start only opens the page: it must tell this app from another
    program on the port."""
    _Health.body = body
    server = HTTPServer(("127.0.0.1", 0), _Health)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert (launcher._health(server.server_port) is not None) is ours
        assert not launcher._port_free(server.server_port)
    finally:
        server.shutdown()
        server.server_close()


def test_an_already_running_app_is_only_shown(monkeypatch):
    opened = []
    monkeypatch.setattr(launcher, "_health", lambda port: {"status": "ok", "ocr": True})
    monkeypatch.setattr(launcher, "open_page", opened.append)
    monkeypatch.setattr(launcher.server, "main", lambda argv: pytest.fail("a second server"))
    assert launcher.main() == 0
    assert opened == ["http://127.0.0.1:8021"]


def test_a_busy_port_moves_to_the_next_free_one(monkeypatch):
    started = []
    monkeypatch.setenv("PDF_TO_GP5_NO_BROWSER", "1")
    monkeypatch.setattr(launcher, "_health", lambda port: None)
    monkeypatch.setattr(launcher, "_port_free", lambda port: port == 8023)
    monkeypatch.setattr(launcher.server, "main", lambda argv: started.append(argv) or 0)
    assert launcher.main() == 0
    assert started == [["--host", "127.0.0.1", "--port", "8023", "--close-with-browser"]]
