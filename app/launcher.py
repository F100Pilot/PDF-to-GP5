"""The start of the Windows program (PDF-to-GP5.exe), doing what start.bat does once the code is up
to date: the server on this computer only, the page opened in Chrome (a profile of its own, where
the graphics acceleration the 3D highway needs is on) or else the default browser, and the server
stops when the page is closed.

Opened twice, the second start only opens the page of the app already running.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import __main__ as server
from .bundled import APP_NAME, user_data_dir

HOST = "127.0.0.1"
PORT = 8021  # as start.bat
SPARE_PORTS = range(8022, 8041)  # when another program holds 8021
READY_TIMEOUT_S = 60


def _health(port: int) -> dict | None:
    """This app's /api/health on ``port``, or None (nothing there, or another program)."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/api/health", timeout=2) as response:
            body = json.loads(response.read(64 * 1024))
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) and body.get("status") == "ok" and "ocr" in body else None


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((HOST, port))
        except OSError:
            return False
    return True


def _chrome() -> str | None:
    """Chrome's program, where its installer puts it (start.bat looks in the same places)."""
    roots = [os.environ.get(name) for name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    for root in filter(None, roots):
        path = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if path.is_file():
            return str(path)
    return None


def open_page(url: str) -> None:
    """Chrome in a window and profile of its own (WebGL always on, as start.bat opens it), else the
    default browser. In Brave the YouTube video does not play inside the page."""
    chrome = _chrome()
    if chrome:
        profile = user_data_dir() / "Chrome"
        flags = [f"--user-data-dir={profile}", "--ignore-gpu-blocklist", "--no-first-run", "--no-default-browser-check"]
        try:
            subprocess.Popen([chrome, *flags, url])
            return
        except OSError:
            pass
    webbrowser.open(url)


def _open_when_ready(port: int) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if _health(port):
            open_page(f"http://{HOST}:{port}")
            return
        time.sleep(0.5)
    print("A página não abriu: o servidor não respondeu. / The page did not open: the server did not answer.")


def main() -> int:
    print(f"{APP_NAME}: a iniciar / starting…", flush=True)
    if _health(PORT):  # already running: show it
        open_page(f"http://{HOST}:{PORT}")
        return 0
    port = next((p for p in (PORT, *SPARE_PORTS) if _port_free(p)), None)
    if port is None:
        print(
            f"ERRO: as portas {PORT}-{SPARE_PORTS[-1]} estão ocupadas. / ERROR: ports {PORT}-{SPARE_PORTS[-1]} are busy."
        )
        return 1
    print(f"Servidor / Server: http://{HOST}:{port}", flush=True)
    print("Para parar: feche a página no browser. / To stop: close the page in the browser.", flush=True)
    if os.environ.get("PDF_TO_GP5_NO_BROWSER") != "1":  # set by the build's smoke test
        threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()
    return server.main(["--host", HOST, "--port", str(port), "--close-with-browser"])
