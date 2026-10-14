"""Installing what is missing and saving the YouTube key from the page (Definições)."""

import sys
import time

import pytest
from fastapi.testclient import TestClient

from app import config, installer, main


@pytest.fixture
def local():
    return TestClient(main.app, base_url="http://127.0.0.1:8021", client=("127.0.0.1", 50000))


@pytest.fixture
def remote():
    return TestClient(main.app, base_url="http://127.0.0.1:8021", client=("203.0.113.9", 50000))


def test_health_says_whether_this_page_can_install(local, remote):
    health = local.get("/api/health").json()
    assert health["can_install"] is True and health["ocr"] is True and health["ocr_problem"] == ""
    assert remote.get("/api/health").json()["can_install"] is False


def test_install_runs_the_fixed_steps_in_the_background(local, monkeypatch):
    monkeypatch.setattr(installer, "STEPS", ([sys.executable, "-c", "print('instalado')"],))
    monkeypatch.setattr(main, "installation", installer.Installation())
    assert local.post("/api/install").status_code == 202
    for _ in range(100):
        status = local.get("/api/install").json()
        if status["state"] != "running":
            break
        time.sleep(0.05)
    assert status == {"state": "done", "log": ["instalado"]}


def test_failed_step_stops_and_shows_its_output(local, monkeypatch):
    fail = [sys.executable, "-c", "import sys; print('sem rede', file=sys.stderr); sys.exit(1)"]
    never = [sys.executable, "-c", "print('nunca')"]
    monkeypatch.setattr(installer, "STEPS", (fail, never))
    monkeypatch.setattr(main, "installation", installer.Installation())
    local.post("/api/install")
    for _ in range(100):
        status = local.get("/api/install").json()
        if status["state"] != "running":
            break
        time.sleep(0.05)
    assert status == {"state": "failed", "log": ["sem rede"]}


def test_install_and_key_only_on_this_computer(remote):
    assert remote.post("/api/install").status_code == 403
    assert remote.get("/api/install").status_code == 403
    assert remote.post("/api/youtube-key", json={"key": "AIza" + "x" * 35}).status_code == 403


def test_other_sites_cannot_start_an_install(local):
    response = local.post("/api/install", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_youtube_key_is_saved_and_used(local, tmp_path, monkeypatch):
    key_file = tmp_path / "youtube_api_key.txt"
    monkeypatch.setattr(config, "YOUTUBE_KEY_FILE", key_file)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(main, "settings", main.settings)  # restored after the test
    assert local.post("/api/youtube-key", json={"key": "not a key!"}).status_code == 422
    assert not key_file.exists()
    key = "AIza" + "x" * 35
    assert local.post("/api/youtube-key", json={"key": f"  {key} "}).status_code == 204
    assert key_file.read_text(encoding="utf-8") == key + "\n"
    health = local.get("/api/health").json()
    assert health["video_search"] is True and key not in str(health)


@pytest.mark.parametrize("header", ["X-Forwarded-For", "X-Real-IP", "Forwarded", "X-Forwarded-Host"])
def test_a_request_through_a_reverse_proxy_is_not_this_computer(local, header):
    """A proxy on the same machine that rewrites the Host to 127.0.0.1 still adds its own header."""
    headers = {header: "203.0.113.9"}
    assert local.get("/api/health", headers=headers).json()["can_install"] is False
    assert local.post("/api/install", headers=headers).status_code == 403
    assert local.get("/api/library", headers=headers).status_code == 404


def test_local_features_can_be_turned_off_for_a_published_copy(local, monkeypatch):
    import dataclasses

    monkeypatch.setattr(main, "settings", dataclasses.replace(main.settings, local_features=False))
    assert local.get("/api/health").json()["can_install"] is False
    assert local.post("/api/install").status_code == 403
    assert local.post("/api/youtube-key", json={"key": "AIza" + "x" * 35}).status_code == 403
