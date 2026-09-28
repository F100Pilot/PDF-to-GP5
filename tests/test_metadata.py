import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.extract.metadata import (
    _detect_tempo,
    _detect_time_signature,
    detect_metadata,
    detect_part_name,
    track_name_from_filename,
)
from app.extract.pdf_reader import Char, Page, read_document


def _pdf(lines: list[tuple[str, int, str]], title: str | None = None, author: str | None = None) -> bytes:
    """lines: (text, font size, alignment 'c' or 'l'), drawn top-down."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    if title:
        pdf.setTitle(title)
    if author:
        pdf.setAuthor(author)
    y = A4[1] - 60
    for text, size, align in lines:
        pdf.setFont("Helvetica", size)
        if align == "c":
            pdf.drawCentredString(A4[0] / 2, y, text)
        else:
            pdf.drawString(40, y, text)
        y -= size * 1.8
    for i in range(20):  # body text so the title stands out
        pdf.setFont("Helvetica", 9)
        pdf.drawString(40, 300 - i * 12, f"body line {i}")
    pdf.save()
    return buffer.getvalue()


def _detect(data: bytes):
    pages, info = read_document(data, 5)
    return detect_metadata(pages, info)


def test_visual_title_and_artist():
    meta = _detect(_pdf([("Happen To Me", 24, "c"), ("Russell Dickerson", 14, "c"), ("Tuning: E A D G B E", 9, "l")]))
    assert (meta.title, meta.artist) == ("Happen To Me", "Russell Dickerson")


def test_credit_line_is_preferred_for_artist():
    meta = _detect(_pdf([("Song Name", 24, "c"), ("Arranged for guitar", 12, "c"), ("Music by Jane Doe", 10, "c")]))
    assert (meta.title, meta.artist) == ("Song Name", "Jane Doe")


def test_labelled_fields_win_and_uniform_text_has_no_visual_title():
    meta = _detect(_pdf([("Song: Blue Sky", 10, "l"), ("Band: The Clouds", 10, "l")]))
    assert (meta.title, meta.artist) == ("Blue Sky", "The Clouds")


def test_document_info_fallback_ignores_placeholders():
    assert _detect(_pdf([("tab", 10, "l")], title="Real Title", author="Real Author")).title == "Real Title"
    assert _detect(_pdf([("tab", 10, "l")], title="untitled", author="anonymous")).title is None
    assert _detect(_pdf([("tab", 10, "l")], title="Microsoft Word - My Song.docx")).title == "My Song.docx"


def test_tempo_patterns():
    assert _detect_tempo(["=118"]) == 118
    assert _detect_tempo([" = 60"]) == 90  # dotted quarter
    assert _detect_tempo([" = 200"]) == 100  # eighth note
    assert _detect_tempo(["= 132"]) == 132
    assert _detect_tempo(["Tempo: 96"]) == 96
    assert _detect_tempo(["Played at 140 BPM"]) == 140
    assert _detect_tempo(["Page 12 of 30", "= 999"]) is None


def _glyph(text: str, x: float, top: float) -> Char:
    return Char(text, x, x + 12, top, top + 25)


def test_time_signature_glyphs():
    page = Page(1, 600, 800, [_glyph("", 50, 100), _glyph("", 50, 112)], [])
    assert _detect_time_signature(page) == (6, 8)
    page = Page(1, 600, 800, [_glyph("", 44, 100), _glyph("", 56, 100), _glyph("", 50, 112)], [])
    assert _detect_time_signature(page) == (12, 8)
    assert _detect_time_signature(Page(1, 600, 800, [_glyph("", 50, 100)], [])) == (4, 4)
    assert _detect_time_signature(Page(1, 600, 800, [_glyph("", 50, 100)], [])) is None  # lone digit


def test_part_name_from_page_text():
    data = _pdf([("Happen To Me", 24, "c"), ("Russell Dickerson", 14, "c"), ("Electric Guitar 2", 10, "l")])
    pages, info = read_document(data, 5)
    assert detect_part_name(pages, detect_metadata(pages, info)) == "Electric Guitar 2"


def test_track_name_from_filename():
    assert (
        track_name_from_filename("Russell_Dickerson_-_Happen_To_Me_-_Bass.pdf", "Happen To Me", "Russell Dickerson")
        == "Bass"
    )
    assert track_name_from_filename("Happen To Me.pdf", "Happen To Me", None) is None
    assert track_name_from_filename("C:\\tabs\\Song - Lead Guitar.PDF", "Song", None) == "Lead Guitar"
