"""Song covers from the iTunes Search API (network replaced by fixed replies)."""

import json

import pytest
from fastapi.testclient import TestClient

from app import cover, main

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
ART = "https://is1-ssl.mzstatic.com/image/thumb/Music/v4/ab/cd/source/100x100bb.jpg"


def _result(artist, track, url=ART):
    return {"artistName": artist, "trackName": track, "artworkUrl100": url}


@pytest.fixture(autouse=True)
def _empty_cache():
    cover._cache.clear()
    yield
    cover._cache.clear()


def test_artwork_of_the_same_artist_and_title_in_large_size():
    data = {
        "results": [
            _result("Eagles Tribute Band", "Hotel California", ART.replace("ab/cd", "xx/yy")),
            _result("Eagles", "Take It Easy", ART.replace("ab/cd", "ee/ff")),
            _result("Eagles", "Hotel California (Remastered)"),
        ]
    }
    url = cover.artwork_url(data, "Eagles", "Hotel California")
    assert url == "https://is1-ssl.mzstatic.com/image/thumb/Music/v4/ab/cd/source/600x600bb.jpg"


def test_no_cover_from_another_artist_or_another_host():
    assert (
        cover.artwork_url({"results": [_result("Someone Else", "Hotel California")]}, "Eagles", "Hotel California")
        is None
    )
    evil = _result("Eagles", "Hotel California", "https://example.com/100x100bb.jpg")
    plain_http = _result("Eagles", "Hotel California", ART.replace("https://", "http://"))
    assert cover.artwork_url({"results": [evil, plain_http]}, "Eagles", "Hotel California") is None
    assert cover.artwork_url("junk", "Eagles", "x") is None


def test_accents_and_punctuation_do_not_matter():
    data = {"results": [_result("Beyoncé", "Halo!")]}
    assert cover.artwork_url(data, "beyonce", "halo") is not None


def _network(monkeypatch, search, image=JPEG):
    calls = []

    def fake_read(url, limit):
        calls.append(url)
        if url.startswith(cover.SEARCH_URL):
            return json.dumps(search).encode()
        return image

    monkeypatch.setattr(cover, "_read", fake_read)
    return calls


def test_find_cover_downloads_the_image_once_a_day(monkeypatch):
    calls = _network(monkeypatch, {"results": [_result("Eagles", "Hotel California")]})
    assert cover.find_cover("Eagles", "Hotel California") == (JPEG, "image/jpeg")
    assert cover.find_cover("eagles", "hotel california") == (JPEG, "image/jpeg")  # cached
    assert len(calls) == 2 and "600x600bb.jpg" in calls[1]


def test_find_cover_rejects_what_is_not_an_image(monkeypatch):
    _network(monkeypatch, {"results": [_result("Eagles", "Hotel California")]}, image=b"<html>")
    with pytest.raises(cover.CoverError):
        cover.find_cover("Eagles", "Hotel California")


def test_cover_endpoint(monkeypatch):
    client = TestClient(main.app)
    _network(monkeypatch, {"results": [_result("Eagles", "Hotel California")]})
    response = client.get("/api/cover", params={"artist": "Eagles", "title": "Hotel California"})
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert response.content == JPEG
    _network(monkeypatch, {"results": []})
    assert client.get("/api/cover", params={"artist": "Nobody", "title": "Nothing"}).status_code == 404
    assert client.get("/api/cover", params={"artist": "", "title": "x"}).status_code == 422

    def offline(url, limit):
        raise cover.CoverError("offline")

    monkeypatch.setattr(cover, "_read", offline)
    assert client.get("/api/cover", params={"artist": "A", "title": "B"}).status_code == 502
