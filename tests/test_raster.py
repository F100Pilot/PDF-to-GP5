"""Tablature read from pictures (OCR): PNG/JPEG/WebP uploads and PDFs that are only images."""

import io

import pytest
from PIL import Image

from app.converter import ConversionError, ConversionOptions, convert, inspect
from app.extract.raster_tab import _TEMPO_MARK, _join_lines, image_kind
from tests.pdf_factory import engraved_tab_pdf, image_pdf, tab_png

STAVES = [
    [[(1, 0), (2, 12)], [(3, 5), (6, 3)]],
    [[(4, 7), (5, 10)], [(1, 2), (2, 9)]],
]


def _picture(width: int = 1300, image_format: str = "PNG", staves=STAVES, heading=None) -> bytes:
    # editors blank the staff line behind each number; the reader relies on that gap
    pdf = engraved_tab_pdf(staves, knockout=True, heading=heading)
    return tab_png(pdf, width=width, image_format=image_format)


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


HEADING = ("Riff Song", "The Band", 96)


@pytest.mark.parametrize("width", [1000, 1300, 2000])
def test_title_artist_and_tempo_are_read_from_the_picture(width):
    report = convert(_picture(width, heading=HEADING), ConversionOptions()).report
    assert (report["title"], report["artist"], report["tempo"]) == HEADING
    assert report["auto"]["title"] and report["auto"]["artist"] and report["auto"]["tempo"]


def test_title_artist_and_tempo_of_a_pdf_of_pictures():
    report = convert(image_pdf([_picture(heading=HEADING)]), ConversionOptions()).report
    assert (report["title"], report["artist"], report["tempo"]) == HEADING


def test_inspect_reads_the_heading_of_a_picture():
    detected = inspect(_picture(heading=HEADING), ConversionOptions())
    assert (detected["title"], detected["artist"], detected["tempo"]) == HEADING


def test_tempo_mark_as_the_recogniser_reads_it():
    for read in ("：97", "J=97", "= 97", "♩ = 97", "」：97"):
        assert _TEMPO_MARK.sub("= ", read) == "= 97", read
    assert _TEMPO_MARK.sub("= ", "Tuning: E A D G B E").startswith("Tuning")
    assert _TEMPO_MARK.sub("= ", "Verse 1") == "Verse 1"


def test_boxes_cut_on_one_line_are_joined():
    note, number, far = (100, 50, 118, 70), (122, 51, 150, 69), (400, 50, 450, 70)
    assert sorted(_join_lines([number, far, note])) == [(100, 50, 150, 70), far]
    assert _join_lines([(100, 50, 150, 70), (100, 90, 150, 110)]) == [(100, 50, 150, 70), (100, 90, 150, 110)]


def _signatures(gp5: bytes) -> list[tuple[int, int]]:
    import guitarpro as gp

    song = gp.parse(io.BytesIO(gp5))
    return [(h.timeSignature.numerator, h.timeSignature.denominator.value) for h in song.measureHeaders]


def _signature_picture(signatures, width: int = 1300) -> bytes:
    staves = [[[(1, 0), (2, 3)], [(3, 5), (1, 2)], [(2, 1), (3, 2)]]]
    return tab_png(engraved_tab_pdf(staves, knockout=True, signatures=signatures), width=width)


@pytest.mark.parametrize(("numerator", "denominator"), [(3, 4), (6, 8), (12, 8), (4, 4)])
def test_time_signature_is_read_from_the_picture(numerator, denominator):
    result = convert(_signature_picture([(0, 0, numerator, denominator)]), ConversionOptions())
    assert result.report["time_signature"] == f"{numerator}/{denominator}"
    assert _signatures(result.gp5)[0] == (numerator, denominator)


@pytest.mark.parametrize("width", [1000, 2600])
def test_time_signature_change_on_the_staff(width):
    result = convert(_signature_picture([(0, 0, 4, 4), (0, 1, 3, 4)], width), ConversionOptions())
    assert _signatures(result.gp5)[:3] == [(4, 4), (3, 4), (3, 4)]


def test_no_time_signature_is_made_up():
    result = convert(_picture(), ConversionOptions())
    assert not result.report["auto"]["time_signature"]


def test_pdf_text_with_tempo_and_time_signature_from_its_picture():
    # a printed web page: title and artist as text, the tab (tempo mark, time signature) a picture
    staves = [[[(1, 0), (2, 3)], [(3, 5), (1, 2)]]]
    tab = engraved_tab_pdf(staves, knockout=True, heading=("", "", 96), signatures=[(0, 0, 3, 4)])
    report = convert(image_pdf([tab_png(tab)], text=("Riff Song", "The Band")), ConversionOptions()).report
    assert (report["title"], report["artist"], report["tempo"], report["time_signature"]) == (
        "Riff Song",
        "The Band",
        96,
        "3/4",
    )
