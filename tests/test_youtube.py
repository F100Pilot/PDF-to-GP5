import io
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import config, main, youtube

KEY = "AIzaTestKey_0123456789abcdefghijklmnop"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _reply(items):
    return FakeResponse(json.dumps({"items": items}).encode())


def test_parse_keeps_valid_videos_and_unescapes_titles():
    items = [
        {
            "id": {"videoId": "dQw4w9WgXcQ"},
            "snippet": {"title": "Artist &amp; Band &#39;Song&#39;", "channelTitle": "Chan"},
        },
        {"id": {"videoId": "bad id!"}, "snippet": {"title": "x"}},
        {"id": {"channelId": "UC123"}, "snippet": {"title": "a channel"}},
        "junk",
    ]
    assert youtube._parse({"items": items}) == [
        {"id": "dQw4w9WgXcQ", "title": "Artist & Band 'Song'", "channel": "Chan"}
    ]
    assert youtube._parse(["not", "a", "dict"]) == []


def test_search_calls_the_api_once_and_caches(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        return _reply([{"id": {"videoId": "dQw4w9WgXcQ"}, "snippet": {"title": "T", "channelTitle": "C"}}])

    monkeypatch.setattr(youtube, "urlopen", fake_urlopen)
    youtube._cache.clear()
    assert youtube.search("Artist Song", KEY)[0]["id"] == "dQw4w9WgXcQ"
    assert youtube.search("artist song ", KEY)[0]["id"] == "dQw4w9WgXcQ"
    assert len(calls) == 1
    assert calls[0].startswith(youtube.API_URL) and "videoEmbeddable=true" in calls[0]


def test_search_errors_do_not_leak_the_key(monkeypatch):
    def fail(request, timeout):
        raise youtube.URLError(f"failed {request.full_url}")

    monkeypatch.setattr(youtube, "urlopen", fail)
    youtube._cache.clear()
    with pytest.raises(youtube.VideoSearchError) as error:
        youtube.search("another song", KEY)
    assert KEY not in str(error.value)


def test_key_from_environment_or_local_file(monkeypatch, tmp_path):
    key_file = tmp_path / "youtube_api_key.txt"
    monkeypatch.setattr(config, "YOUTUBE_KEY_FILE", key_file)
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert config._youtube_key() == ""
    key_file.write_text(f"{KEY}\n# comment\n", encoding="utf-8")
    assert config._youtube_key() == KEY
    monkeypatch.setenv("YOUTUBE_API_KEY", "not a key!")
    assert config._youtube_key() == ""  # malformed values are ignored


@pytest.fixture()
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def test_video_search_endpoint(client, monkeypatch):
    monkeypatch.setattr(main, "settings", replace(main.settings, youtube_api_key=""))
    assert client.get("/api/health").json()["video_search"] is False
    assert client.get("/api/video-search", params={"q": "Artist Song"}).status_code == 404

    monkeypatch.setattr(main, "settings", replace(main.settings, youtube_api_key=KEY))
    monkeypatch.setattr(main, "search_youtube", lambda q, key: [{"id": "dQw4w9WgXcQ", "title": q, "channel": "C"}])
    assert client.get("/api/health").json()["video_search"] is True
    body = client.get("/api/video-search", params={"q": "Artist Song"}).json()
    assert body == {"results": [{"id": "dQw4w9WgXcQ", "title": "Artist Song", "channel": "C"}]}
    assert client.get("/api/video-search", params={"q": "x"}).status_code == 422

    def broken(q, key):
        raise youtube.VideoSearchError("URLError")

    monkeypatch.setattr(main, "search_youtube", broken)
    assert client.get("/api/video-search", params={"q": "Artist Other"}).status_code == 502
