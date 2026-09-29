import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from app import main
from app.presence import GRACE_S, STALE_S, Presence


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _presence():
    clock = Clock()
    return Presence(clock), clock


def test_never_stops_before_a_page_opens():
    presence, clock = _presence()
    clock.now += 10 * STALE_S
    assert not presence.should_stop()


def test_stops_after_last_page_closes_and_grace_period():
    presence, clock = _presence()
    presence.update("page-aaaa", alive=True)
    presence.update("page-bbbb", alive=True)
    presence.update("page-aaaa", alive=False)
    clock.now += GRACE_S + 1
    assert not presence.should_stop()  # another page is still open
    presence.update("page-bbbb", alive=False)
    clock.now += GRACE_S - 1
    assert not presence.should_stop()
    clock.now += 1
    assert presence.should_stop()


def test_reload_within_grace_keeps_running():
    presence, clock = _presence()
    presence.update("page-aaaa", alive=True)
    presence.update("page-aaaa", alive=False)
    clock.now += 2
    presence.update("page-cccc", alive=True)  # the reloaded page
    clock.now += GRACE_S * 3
    assert not presence.should_stop()


def test_silent_page_counts_as_closed():
    presence, clock = _presence()
    presence.update("page-aaaa", alive=True)
    clock.now += STALE_S + GRACE_S + 1
    assert not presence.should_stop()  # grace starts when the page is found stale
    clock.now += GRACE_S
    assert presence.should_stop()


@pytest.fixture()
def client():
    with TestClient(main.app) as test_client:
        yield test_client
    main.presence.enabled = False


def test_presence_endpoint_disabled_by_default(client):
    assert client.get("/api/health").json()["close_with_browser"] is False
    assert client.post("/api/presence", json={"id": "page-aaaa", "state": "alive"}).status_code == 404


def test_presence_endpoint_when_enabled(client):
    main.presence.enabled = True
    assert client.get("/api/health").json()["close_with_browser"] is True
    assert client.post("/api/presence", json={"id": "page-aaaa", "state": "alive"}).status_code == 204
    assert client.post("/api/presence", json={"id": "page-aaaa", "state": "gone"}).status_code == 204
    assert client.post("/api/presence", json={"id": "bad id!", "state": "alive"}).status_code == 422
    assert client.post("/api/presence", json={"id": "page-aaaa", "state": "x"}).status_code == 422
    foreign = client.post(
        "/api/presence", json={"id": "page-aaaa", "state": "gone"}, headers={"Origin": "http://evil.example"}
    )
    assert foreign.status_code == 403


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_launcher_stops_after_page_closes():
    port = _free_port()
    root = Path(__file__).resolve().parent.parent
    code = f"import app.presence as p; p.GRACE_S = 0; from app.__main__ import main; raise SystemExit(main(['--port', '{port}', '--close-with-browser']))"
    process = subprocess.Popen([sys.executable, "-c", code], cwd=root)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                if httpx2.get(f"{base}/api/health").json()["close_with_browser"]:
                    break
            except httpx2.HTTPError:
                time.sleep(0.1)
        httpx2.post(f"{base}/api/presence", json={"id": "page-aaaa", "state": "alive"})
        httpx2.post(f"{base}/api/presence", json={"id": "page-aaaa", "state": "gone"})
        assert process.wait(timeout=15) == 0
    finally:
        if process.poll() is None:
            process.kill()


def test_launcher_stops_even_with_a_stuck_request():
    """A request whose body never arrives must not keep the server alive after the page closed."""
    port = _free_port()
    root = Path(__file__).resolve().parent.parent
    code = f"import app.presence as p; p.GRACE_S = 0; from app.__main__ import main; raise SystemExit(main(['--port', '{port}', '--close-with-browser']))"
    process = subprocess.Popen(
        [sys.executable, "-c", code], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                if httpx2.get(f"{base}/api/health").json()["close_with_browser"]:
                    break
            except httpx2.HTTPError:
                time.sleep(0.1)
        stuck = socket.create_connection(("127.0.0.1", port))
        stuck.sendall(b"POST /api/presence HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 500\r\n\r\n{")
        time.sleep(0.3)
        httpx2.post(f"{base}/api/presence", json={"id": "page-aaaa", "state": "alive"})
        httpx2.post(f"{base}/api/presence", json={"id": "page-aaaa", "state": "gone"})
        assert process.wait(timeout=20) == 0
        stuck.close()
    finally:
        if process.poll() is None:
            process.kill()
