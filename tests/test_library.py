"""The song library in a folder on disk (/api/library), used on the computer the server runs on."""

import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.library_store import LibraryStore, safe_name

GP5 = b"\x18FICHIER GUITAR PRO v5.10" + b"\x00" * 64
MP3 = b"ID3\x04\x00" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
REPORT = {"measures": 3, "tracks": [{"name": "Guitar"}], "warnings": []}


@pytest.fixture
def store(tmp_path, monkeypatch):
    library = LibraryStore(tmp_path / "Biblioteca")
    monkeypatch.setattr(main, "library", library)
    return library


@pytest.fixture
def local():
    return TestClient(main.app, base_url="http://127.0.0.1:8021", client=("127.0.0.1", 50000))


def _meta(**change):
    meta = {
        "key": "eagles - hotel california",
        "title": "Hotel California",
        "artist": "Eagles",
        "tempo": 74,
        "measures": 3,
        "trackNames": ["Guitar"],
        "savedAt": 1000,
        "filename": "Hotel California.gp5",
        "report": REPORT,
    }
    return {**meta, **change}


def _save(client, gp5=GP5, **change):
    return client.post("/api/library", data={"meta": json.dumps(_meta(**change))}, files={"gp5": ("x.gp5", gp5)})


def test_a_song_is_kept_in_its_own_folder(store, local):
    response = _save(local)
    assert response.status_code == 200
    song = response.json()
    assert song["id"] == "Eagles - Hotel California" and song["audioName"] == "" and not song["cover"]
    folder = store.root / "Eagles - Hotel California"
    assert (folder / "Hotel California.gp5").read_bytes() == GP5
    assert json.loads((folder / "musica.json").read_text(encoding="utf-8"))["report"] == REPORT
    listing = local.get("/api/library").json()
    assert listing["folder"] == str(store.root) and [s["id"] for s in listing["songs"]] == [song["id"]]
    full = local.get("/api/library/Eagles - Hotel California").json()
    assert full["report"] == REPORT and full["filename"] == "Hotel California.gp5"
    assert local.get("/api/library/Eagles - Hotel California/gp5").content == GP5


def test_audio_and_cover_stay_when_the_song_is_converted_again(store, local):
    song_id = _save(local).json()["id"]
    put = local.put(f"/api/library/{song_id}/audio", content=MP3, headers={"X-Filename": "Hotel%20California.mp3"})
    assert put.status_code == 204
    assert local.put(f"/api/library/{song_id}/cover", content=JPEG).status_code == 204
    again = _save(local, savedAt=2000, tempo=75).json()
    assert again["id"] == song_id and again["audioName"] == "Hotel California.mp3" and again["cover"]
    audio = local.get(f"/api/library/{song_id}/audio")
    assert audio.content == MP3 and audio.headers["content-type"] == "audio/mpeg"
    # a PNG replaces the JPEG (no stray file), removing the audio deletes its file
    assert local.put(f"/api/library/{song_id}/cover", content=PNG).status_code == 204
    assert local.delete(f"/api/library/{song_id}/audio").status_code == 204
    names = sorted(p.name for p in (store.root / song_id).iterdir())
    assert names == ["Hotel California.gp5", "capa.png", "musica.json"]
    assert local.get(f"/api/library/{song_id}/audio").status_code == 404


def test_what_is_not_a_gp5_audio_or_image_is_refused(store, local):
    assert _save(local, gp5=b"<html>").status_code == 422
    song_id = _save(local).json()["id"]
    assert local.put(f"/api/library/{song_id}/audio", content=b"<script>").status_code == 422
    assert local.put(f"/api/library/{song_id}/cover", content=b"GIF89a").status_code == 422
    assert local.post("/api/library", data={"meta": "[]"}, files={"gp5": ("x", GP5)}).status_code == 422
    assert _save(local, report="x").status_code == 422


def test_ids_are_only_matched_against_existing_folders(store, local, tmp_path):
    (tmp_path / "secret").mkdir()
    (tmp_path / "secret" / "musica.json").write_text(json.dumps({"key": "x", "files": {"gp5": "a.gp5"}}))
    (tmp_path / "secret" / "a.gp5").write_bytes(GP5)
    _save(local)
    for song_id in ("..%2Fsecret", "../secret", "%2E%2E", "secret"):
        assert local.get(f"/api/library/{song_id}/gp5").status_code == 404
        assert local.delete(f"/api/library/{song_id}").status_code in (404, 405, 422)
    assert (tmp_path / "secret" / "a.gp5").exists()


def test_removing_a_song_keeps_the_users_own_files(store, local):
    song_id = _save(local).json()["id"]
    (store.root / song_id / "notes.txt").write_text("mine")
    assert local.delete(f"/api/library/{song_id}").status_code == 204
    assert [p.name for p in (store.root / song_id).iterdir()] == ["notes.txt"]
    assert local.get("/api/library").json()["songs"] == []
    song_id = _save(local, key="other", title="Other", artist="").json()["id"]
    assert local.delete(f"/api/library/{song_id}").status_code == 204
    assert not (store.root / song_id).exists()


def test_same_folder_name_for_another_song_gets_a_number(store, local):
    first = _save(local).json()["id"]
    second = _save(local, key="eagles - hotel california?").json()["id"]
    assert (first, second) == ("Eagles - Hotel California", "Eagles - Hotel California (2)")


def test_only_on_the_computer_the_server_runs_on(store):
    remote = TestClient(main.app, base_url="http://127.0.0.1:8021", client=("203.0.113.9", 50000))
    assert remote.get("/api/library").status_code == 404
    assert _save(remote).status_code == 404
    assert not store.root.exists()


def test_other_sites_cannot_change_the_library(store, local):
    response = local.post(
        "/api/library",
        data={"meta": json.dumps(_meta())},
        files={"gp5": ("x.gp5", GP5)},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_safe_names():
    assert safe_name("AC/DC - Back: In Black?", "x") == "AC_DC - Back_ In Black_"
    assert safe_name("  ..  ", "fallback") == "fallback"
    assert safe_name("CON", "fallback") == "fallback"
    assert len(safe_name("a" * 300, "x")) == 80
