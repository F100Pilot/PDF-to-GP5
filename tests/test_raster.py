"""Tablature read from pictures (OCR): PNG/JPEG/WebP uploads and PDFs that are only images."""

import io

import pytest
from PIL import Image

from app.converter import ConversionError, ConversionOptions, convert, inspect
from app.extract.raster_tab import image_kind
from tests.pdf_factory import engraved_tab_pdf, image_pdf, tab_png

STAVES = [
    [[(1, 0), (2, 12)], [(3, 5), (6, 3)]],
    [[(4, 7), (5, 10)], [(1, 2), (2, 9)]],
]


def _picture(width: int = 1300, image_format: str = "PNG", staves=STAVES) -> bytes:
    # editors blank the staff line behind each number; the reader relies on that gap
    return tab_png(engraved_tab_pdf(staves, knockout=True), width=width, image_format=image_format)


def _frets(gp5: bytes) -> list[tuple[int, int]]:
    import guitarpro as gp

    song = gp.parse(io.BytesIO(gp5))
    return [
        (note.string, note.value)
        for measure in song.tracks[0].measures
        for beat in measure.voices[0].beats
        for note in sorted(beat.notes, key=lambda n: n.string)
    ]


def _expected(staves=STAVES) -> list[tuple[int, int]]:
    """What the same tab gives when read from the vector PDF."""
    return _frets(convert(engraved_tab_pdf(staves, knockout=True), ConversionOptions()).gp5)


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_picture_of_a_tab_is_read(image_format):
    result = convert(_picture(image_format=image_format), ConversionOptions())
    assert _frets(result.gp5) == _expected()
    assert result.report["tracks"][0]["sources"] == ["image"]
    assert any("OCR" in w for w in result.report["warnings"])


@pytest.mark.parametrize("width", [850, 2600, 5000])
def test_picture_size_does_not_matter(width):
    assert _frets(convert(_picture(width), ConversionOptions()).gp5) == _expected()


def test_crop_of_one_staff_is_read():
    image = Image.open(io.BytesIO(_picture()))
    buffer = io.BytesIO()
    image.crop((60, 140, image.width - 60, 370)).save(buffer, format="PNG")  # the first staff only
    assert _frets(convert(buffer.getvalue(), ConversionOptions()).gp5) == _expected(STAVES[:1])


def test_pdf_of_pictures_is_read_page_by_page():
    result = convert(image_pdf([_picture(staves=STAVES[:1]), _picture(staves=STAVES[1:])]), ConversionOptions())
    assert _frets(result.gp5) == _expected()
    assert result.report["tracks"][0]["pages"] == [1, 2]


def test_engraved_pdf_is_not_read_by_ocr():
    result = convert(engraved_tab_pdf(STAVES), ConversionOptions())
    assert result.report["tracks"][0]["sources"] == ["engraved"]
    assert not any("OCR" in w for w in result.report["warnings"])


def test_inspect_reads_the_strings_of_a_picture():
    detected = inspect(_picture(), ConversionOptions())
    assert detected["strings"] == 6 and detected["title"] is None


def test_too_many_picture_pages():
    page = _picture(staves=STAVES[:1])
    with pytest.raises(ConversionError, match="OCR"):
        convert(image_pdf([page, page]), ConversionOptions(max_image_pages=1))


def test_too_many_pixels():
    picture = _picture()
    with pytest.raises(ConversionError, match="megap"):
        convert(picture, ConversionOptions(max_image_pixels=100_000))


def test_corrupt_picture():
    with pytest.raises(ConversionError, match="imagem não é válida"):
        convert(b"\x89PNG\r\n\x1a\n" + b"\0" * 64, ConversionOptions())


def test_picture_without_a_tab():
    buffer = io.BytesIO()
    Image.new("L", (400, 300), 255).save(buffer, format="PNG")
    with pytest.raises(ConversionError, match="tablatura"):
        convert(buffer.getvalue(), ConversionOptions())


def test_image_kind():
    assert image_kind(b"\x89PNG\r\n\x1a\n....") == "png"
    assert image_kind(b"\xff\xd8\xff\xe0") == "jpeg"
    assert image_kind(b"RIFF\0\0\0\0WEBPVP8 ") == "webp"
    assert image_kind(b"%PDF-1.7") is None
    assert image_kind(b"GIF89a") is None


def test_onnx_runtime_telemetry_is_off():
    import os

    from app.extract.raster_tab import _recognizer

    _recognizer()
    assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"
