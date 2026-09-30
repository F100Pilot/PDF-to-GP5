"""Server messages follow the request's language (header X-App-Lang); Portuguese without it."""

import pytest
from fastapi.testclient import TestClient

from app import main
from tests.pdf_factory import ascii_tab_pdf, blank_pdf

TAB = [
    "e|-0---3---5h7---|",
    "B|---------------|",
    "G|---------------|",
    "D|---------------|",
    "A|---------------|",
    "E|---------------|",
]
BASS = ["G|-------------|", "D|-------------|", "A|-3---5---7---|", "E|-------------|"]
EN = {"X-App-Lang": "en"}


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def test_endpoint_error_follows_the_header(client):
    files = {"file": ("not.pdf", b"plain text", "application/pdf")}
    english = client.post("/api/convert", files=files, headers=EN)
    portuguese = client.post("/api/convert", files=files)
    assert english.status_code == portuguese.status_code == 415
    assert english.json()["detail"] == "The uploaded file is not a PDF: not.pdf."
    assert portuguese.json()["detail"] == "O ficheiro enviado não é um PDF: not.pdf."


def test_conversion_error_from_the_worker_process_follows_the_header(client):
    files = {"file": ("scan.pdf", blank_pdf(), "application/pdf")}
    english = client.post("/api/convert", files=files, headers=EN)
    portuguese = client.post("/api/convert", files=files)
    assert english.status_code == portuguese.status_code == 422
    assert "no extractable text" in english.json()["detail"]
    assert "não contém texto extraível" in portuguese.json()["detail"]


def test_conversion_warning_follows_the_header(client):
    guitar = ascii_tab_pdf([TAB, TAB], extra_lines=["Title: Riff Song", "Tempo: 100"])
    bass = ascii_tab_pdf([[line.replace("|", "|--", 1) for line in BASS]])
    files = [
        ("file", ("Lead.pdf", guitar, "application/pdf")),
        ("file", ("Bass.pdf", bass, "application/pdf")),
    ]
    english = client.post("/api/convert", files=files, headers=EN).json()["report"]["warnings"]
    portuguese = client.post("/api/convert", files=files).json()["report"]["warnings"]
    assert any("Bass: It has 1 bar(s)" in w and "rest bar(s)" in w for w in english)
    assert any("Bass: Tem 1 compassos" in w and "pausa" in w for w in portuguese)


def test_unknown_language_reads_english(client):
    response = client.get("/api/library/x", headers={"X-App-Lang": "xx"})
    assert response.status_code == 404
    assert response.json()["detail"] == "The on-disk library only exists when the app is open on the computer itself."
