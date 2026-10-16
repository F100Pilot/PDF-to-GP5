"""Tablature read from pictures (OCR): PNG/JPEG/WebP uploads and PDFs that are only images."""

import io
import itertools

import pytest
from PIL import Image

from app.converter import ConversionError, ConversionOptions, convert, inspect
from app.extract.raster_tab import _TEMPO_MARK, _join_lines, image_kind
from tests.pdf_factory import engraved_tab_pdf, image_pdf, rhythm_tab_pdf, tab_png

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
    assert [s["page"] for s in result.report["tracks"][0]["systems_detail"]] == [1, 2]


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


def _notes(gp5: bytes) -> list[tuple[int, int, int, str, bool]]:
    import guitarpro as gp

    song = gp.parse(io.BytesIO(gp5))
    return [
        (number, note.string, note.value, note.type.name, note.effect.ghostNote)
        for number, measure in enumerate(song.tracks[0].measures, start=1)
        for beat in measure.voices[0].beats
        for note in beat.notes
    ]


def test_parenthesized_notes_in_a_picture_are_ghost_notes_or_ties_as_in_the_pdf():
    staves = [[[(1, 3), (2, 5, "(")], [(1, 3, "("), (3, 7)]]]
    pdf = engraved_tab_pdf(staves, knockout=True)
    assert _notes(convert(tab_png(pdf), ConversionOptions()).gp5) == _notes(convert(pdf, ConversionOptions()).gp5)


def test_bar_numbers_count_a_multi_bar_rest_in_a_picture():
    # bar 2 is a rest standing for bars 2-4: the numbers jump from 2 to 5
    staves = [[[(1, 0)], [], [(2, 3)]]]
    pdf = engraved_tab_pdf(staves, knockout=True, bar_numbers=[[1, 2, 5]])
    assert convert(pdf, ConversionOptions()).report["measures"] == 5
    assert convert(tab_png(pdf), ConversionOptions()).report["measures"] == 5


def test_misread_bar_numbers_are_dropped():
    from app.extract.raster_tab import _increasing

    read = [(0, 50), (1, 52), (2, 63), (3, 54), (4, 6), (5, 56)]  # 63 and 6 misread
    assert _increasing(read) == [0, 1, 3, 5]


def test_chord_digits_touching_are_cut_apart():
    from app.extract.raster_tab import _split_chords

    lines = [100.0, 116.0, 132.0]
    touching = (10, 109, 10, 30, 200)  # a "2" on the line at 116 touching a "0" on the line at 132
    single = (40, 109, 10, 14, 90)
    pieces = list(_split_chords([touching, single], lines, 16.0))
    assert [(y, h) for _, y, _, h, _ in pieces] == [(109, 15), (124, 15), (109, 14)]


@pytest.mark.parametrize("width", [1190, 1300])
def test_digits_close_to_the_line_in_a_small_print(width):
    # a web print scaled down: the gap behind each number is a fraction of a pixel, so the line
    # touches the bar of a 4 and the top of a 6's loop
    staves = [[[(1, 4), (2, 6), (3, 4), (4, 6)], [(5, 6), (6, 4), (3, 14), (2, 16)]]]
    picture = tab_png(engraved_tab_pdf(staves, knockout=True, gap=0.15), width=width)
    assert _frets(convert(picture, ConversionOptions()).gp5) == _expected(staves)


def test_digit_read_as_a_letter_is_read_again():
    from app.extract.raster_tab import _misread_digit

    assert all(_misread_digit(text) for text in ["d", "a", "D", "的", "自", "·", "K"])
    # the TAB clef, an accent, a rest, a slide's stroke: not digits
    assert not any(_misread_digit(text) for text in ["T", "A", "B", "y", "Y", "!", "-", "/", ""])


RHYTHM = [
    [("4", 1, 0), ("8", 2, 1), ("8", 2, 3), ("8.", 3, 2), ("16", 3, 4), ("4", 4, 5)],
    [("r2",), ("4", 1, 3), ("4", 2, 3)],
    [("16", 1, 1), ("16", 1, 2), ("16", 1, 3), ("16", 1, 4), ("8", 2, 1), ("8", 2, 2), ("4", 3, 0), ("4", 3, 2)],
]


@pytest.mark.parametrize("width", [1300, 2000])
def test_rhythm_drawn_under_the_tab_is_read_from_the_picture(width):
    # stems, beams, a partial beam, a dot and a half rest, as in a print of "tab with stems"
    import guitarpro as gp

    result = convert(tab_png(rhythm_tab_pdf(RHYTHM), width=width), ConversionOptions())
    song = gp.parse(io.BytesIO(result.gp5))
    beats = [
        [(b.duration.value, b.duration.isDotted, b.status.name == "rest") for b in m.voices[0].beats]
        for m in song.tracks[0].measures
    ]
    assert beats == [
        [
            (4, False, False),
            (8, False, False),
            (8, False, False),
            (8, True, False),
            (16, False, False),
            (4, False, False),
        ],
        [(2, False, True), (4, False, False), (4, False, False)],
        [(16, False, False)] * 4 + [(8, False, False)] * 2 + [(4, False, False)] * 2,
    ]
    assert result.report["tracks"][0]["rhythm_from_notation"] == 3


def test_page_with_text_as_outlines_is_read_by_ocr(monkeypatch):
    # "Microsoft Print to PDF" of a web page (Songsterr) draws the numbers and words as outlines:
    # staff lines found, but no text. Such a page is read as a picture.
    import dataclasses

    from app import converter

    real = converter.read_document

    def without_text(data, max_pages):
        pages, info = real(data, max_pages)
        return [dataclasses.replace(page, chars=[]) for page in pages], info

    monkeypatch.setattr(converter, "read_document", without_text)
    result = convert(engraved_tab_pdf(STAVES, knockout=True), ConversionOptions())
    assert _frets(result.gp5) == _expected()
    assert result.report["tracks"][0]["sources"] == ["image"]


def test_tuning_letters_left_of_the_staff_are_read():
    from app.extract.engraved_tab import extract_engraved_systems
    from app.extract.raster_tab import read_image
    from tests.pdf_factory import labelled_tab_pdf

    page, _ = read_image(tab_png(labelled_tab_pdf(["C", "G", "D#", "A#", "F", "A#"])), 40_000_000)
    systems = extract_engraved_systems(page)
    assert systems[0].labels == ["C", "G", "D#", "A#", "F", "A#"]
    assert all(event.x > systems[0].start_x for event in systems[0].events)  # the F is no fret


TECHNIQUE_STAVES = [
    [[(2, 5), (2, 7, "H"), (3, 4), (1, 8), (1, 5, "P")], [(4, 2), (5, 2), (6, 0), (3, 2), (3, 4, "H")]],
    [[(4, 7), (5, 10), (6, 2), (6, 5, "H")], [(2, 8), (1, 7), (5, 5), (5, 2, "P")]],
]
TECHNIQUE_RANGES = [(0, "P.M.", 60, 300), (0, "PH", 420, 540), (1, "let ring", 60, 260), (1, "N.H.", 300, 420)]


def _techniques(gp5: bytes) -> list[tuple]:
    import guitarpro as gp

    song = gp.parse(io.BytesIO(gp5))
    return [
        (note.string, note.value, note.effect.hammer, note.effect.palmMute, note.effect.letRing, note.effect.harmonic)
        for measure in song.tracks[0].measures
        for beat in measure.voices[0].beats
        for note in sorted(beat.notes, key=lambda n: n.string)
    ]


@pytest.mark.parametrize("width", [1000, 1600])
def test_technique_marks_in_a_picture_are_read_as_in_the_pdf(width):
    """ "H"/"P" over the staff, "P.M." and "let ring" with their dashed lines under it, and harmonics
    ("PH", "N.H.") over it: read from the picture, applied to the same notes as in the PDF."""
    pdf = engraved_tab_pdf(TECHNIQUE_STAVES, knockout=True, ranges=TECHNIQUE_RANGES)
    expected = _techniques(convert(pdf, ConversionOptions()).gp5)
    assert sum(1 for t in expected if t[2]) >= 3 and sum(1 for t in expected if t[3]) >= 3
    assert any(t[4] for t in expected) and any(t[5] for t in expected)
    assert _techniques(convert(tab_png(pdf, width), ConversionOptions()).gp5) == expected


def test_only_technique_words_are_kept():
    from app.extract.raster_tab import _mark_text

    assert [_mark_text(w) for w in ("H", "P", "P.M.", "PM", "P. M", "let ring", "Let Ring", "P.H.", "AH", "N.H.")] == [
        "H",
        "P",
        "P.M.",
        "P.M.",
        "P.M.",
        "letring",
        "letring",
        "PH",
        "AH",
        "N.H.",
    ]
    # a dynamic, a bar number, a section label, a chord name: not technique marks
    assert [_mark_text(w) for w in ("p", "h", "12", "Verse", "A", "full", "")] == [None] * 7


def test_the_dashes_of_a_range_end_where_they_are_drawn():
    """A dash in the picture is longer than drawn (its soft edges): read as is, a note just past
    the end of a "P.M. - - -" line was palm-muted. The factory draws dashes 3 long every 5."""
    from app.extract.raster_tab import read_image

    pdf = engraved_tab_pdf(TECHNIQUE_STAVES, knockout=True, ranges=[(0, "P.M.", 60, 250), (1, "let ring", 100, 400)])
    for width in (1000, 1600):
        page, _ = read_image(tab_png(pdf, width), 10**8)
        dashes = sorted((s for s in page.segments if s.top == s.bottom and s.x1 - s.x0 < 8), key=lambda s: s.x0)
        assert len(dashes) > 40
        lengths = sorted(s.x1 - s.x0 for s in dashes)
        periods = sorted(b.x0 - a.x0 for a, b in itertools.pairwise(dashes) if b.x0 - a.x0 < 8)
        assert 0.5 <= lengths[len(lengths) // 2] / periods[len(periods) // 2] <= 0.62


SLIDE_STAVES = [
    [[(3, 5), (3, 9, "/"), (2, 8, "<"), (2, 6, ">")], [(1, 12), (1, 9, "/"), (4, 4, "<"), (5, 2)]],
    [[(4, 7, ">"), (3, 2), (3, 7, "/"), (3, 5, "/")], [(6, 3, "<"), (5, 9, "<"), (2, 10), (2, 12, "/")]],
    [
        [(6, 14), (4, 8, "<"), (3, 14, "<"), (6, 14, "<"), (3, 5, ">")],
        [(4, 9), (6, 13), (4, 11), (1, 10)],
        [(2, 3), (1, 8, ">"), (2, 3, ">")],
        [(3, 7), (1, 13), (1, 11)],
    ],
]


def _slides(gp5: bytes) -> list[tuple]:
    import guitarpro as gp

    song = gp.parse(io.BytesIO(gp5))
    return [
        (note.string, note.value, sorted(s.name for s in note.effect.slides))
        for measure in song.tracks[0].measures
        for beat in measure.voices[0].beats
        for note in sorted(beat.notes, key=lambda n: n.string)
    ]


@pytest.mark.parametrize("width", [1300, 1600])
def test_slides_in_a_picture_are_read_as_in_the_pdf(width):
    """Slides drawn as straight strokes on the staff — between two notes on a string (cut in two
    by the string's line when drawn low over it), into a note from below, out of it downwards —
    read from the picture as from the PDF; two slides into notes on neighbouring strings, nearly
    in line, stay two."""
    pdf = engraved_tab_pdf(SLIDE_STAVES, knockout=True)
    expected = _slides(convert(pdf, ConversionOptions()).gp5)
    kinds = [kind for *_, found in expected for kind in found]
    assert kinds.count("shiftSlideTo") == 5 and kinds.count("intoFromBelow") == 7 and kinds.count("outDownwards") == 5
    assert _slides(convert(tab_png(pdf, width), ConversionOptions()).gp5) == expected


def test_bends_and_parentheses_are_not_taken_for_slides():
    """A bend's curve, a parenthesis and the slanted stroke of a big time-signature "4", cut by the
    staff lines, leave slanted pieces of ink: they are not straight, so not slides."""
    staves = [
        [
            [(2, 9), (6, 12, "("), (2, 2), (1, 12, "b")],
            [(3, 1), (5, 11, "("), (2, 3, "("), (2, 0, "b")],
            [(3, 8), (2, 9, "("), (6, 11), (5, 10, "b")],
            [(4, 7), (2, 15, "("), (1, 9), (3, 9, "b")],
        ]
    ]
    pdf = engraved_tab_pdf(staves, knockout=True, ranges=[(0, "P.M.", 60, 250)], signatures=[(0, 0, 4, 4)])
    for width in (1000, 1300, 1600):
        assert all(not found for *_, found in _slides(convert(tab_png(pdf, width), ConversionOptions()).gp5))


VIBRATO_STAVES = [
    [[(3, 5, "~"), (2, 8), (4, 7, "~H"), (6, 3)], [(1, 12, "~"), (2, 9, "("), (5, 4), (5, 2, "~")]],
    [[(4, 9), (4, 7, "~"), (2, 10, "~"), (3, 2)], [(6, 0, "~"), (1, 3), (1, 5, "H"), (2, 1, "~")]],
]


def _vibratos(gp5: bytes) -> list[bool]:
    import guitarpro as gp

    song = gp.parse(io.BytesIO(gp5))
    return [
        note.effect.vibrato
        for measure in song.tracks[0].measures
        for beat in measure.voices[0].beats
        for note in beat.notes
        if note.type.name != "tie"
    ]


@pytest.mark.parametrize("width", [1000, 1300, 1600])
def test_vibrato_in_a_picture_is_read(width):
    """A wavy line over the staff gives vibrato to the note under it. The factory draws it as a
    path, which the vector reader does not see (it reads wiggle glyphs), so the expected notes
    are the ones marked."""
    pdf = engraved_tab_pdf(VIBRATO_STAVES, knockout=True)
    marked = [len(note) > 2 and "~" in note[2] for staff in VIBRATO_STAVES for measure in staff for note in measure]
    assert _vibratos(convert(tab_png(pdf, width), ConversionOptions()).gp5) == marked


def test_words_over_the_staff_are_not_vibrato():
    """Words printed over the staff are not wavy lines, even those whose letters rise and fall
    as evenly as a wave ("minimum", "mum": stems and arches; bold letters run together)."""
    words = [
        (0, 62, "minimum", "Helvetica-Bold", 8),
        (0, 140, "mum", "Helvetica", 9),
        (0, 190, "una corda", "Times-Italic", 7),
        (0, 290, "Chorus", "Helvetica-Bold", 7),
        (0, 360, "acc.", "Helvetica-BoldOblique", 9),
        (0, 420, "rit.", "Times-Italic", 9),
        (1, 62, "nun rumor", "Helvetica-Bold", 9),
        (1, 200, "wow", "Helvetica-BoldOblique", 8),
        (1, 300, "Verse 2", "Times-Roman", 8),
        (1, 400, "uuu", "Helvetica-Bold", 8),
    ]
    staves = [[[(3, 5), (2, 8), (4, 7), (6, 3)], [(1, 12), (2, 9), (5, 4), (5, 2)]]] * 2
    pdf = engraved_tab_pdf(staves, knockout=True, words=words)
    for width in (1000, 1300, 1600):
        assert not any(_vibratos(convert(tab_png(pdf, width), ConversionOptions()).gp5))


def test_a_wave_is_one_stroke_rising_and_falling_evenly():
    import numpy as np

    from app.extract.raster_tab import _is_wave

    def art(text):
        return np.array([[ch == "#" for ch in row] for row in text.split()])

    wave = art(
        """
        .###...####...####..####...####
        #####..#####.#####..#####.#####
        .#.######.##.##.######.##.##.##
        ...#####..#####..####..#####...
        ....###....###...####...###....
        """
    )
    bold_m = art(
        """
        ###############.
        ####.###.###..##
        ##...##..###..##
        ##...##..##...##
        ##...##..##...##
        ##...##..##...##
        ##...##..##...##
        ##...##..##...##
        """
    )
    two_heights = art(  # a "u" and an "o": ink at two heights in some columns
        """
        ##..##.#####.##..##.#####.
        ##..##.##.##.##..##.##.##.
        ##..##.##.##.##..##.##.##.
        ######.#####.######.#####.
        """
    )
    run_together = art(  # bold italic letters touching ("acc."): one blob, ink at two heights
        """
        #..##..#.####.##.##..#
        ################.#####
        ##########..##########
        .#########..#########.
        .######.###.#########.
        .######..#####.######.
        ..........##..........
        """
    )
    one_zigzag = art(  # a "w": rises and falls, but once
        """
        ##........##
        .##......##.
        ..##....##..
        ...##..##...
        ....####....
        """
    )
    one_hump = art(  # a slur
        """
        ......##########......
        ...####........####...
        .###..............###.
        ##..................##
        """
    )

    def polyline(points):
        import cv2

        canvas = np.zeros((40, 60), np.uint8)
        cv2.polylines(canvas, [np.array(points, np.int32)], False, 1, 1)
        ys, xs = np.nonzero(canvas)
        return canvas[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1].astype(bool)

    stems_and_arches = np.zeros((8, 30), bool)  # a wide bold "mmm": rises and falls evenly
    stems_and_arches[:2] = True
    for x in range(0, 30, 4):
        stems_and_arches[:, x : x + 2] = True
    short_zigzag = polyline([(0, 0), (3, 5), (6, 0), (9, 5), (12, 0)])  # "vv": not long enough
    uneven = polyline([(0, 0), (2, 4), (4, 0), (6, 4), (20, 0), (22, 4)])  # not at an even pace
    assert _is_wave(wave, 16, np)
    for shape in (bold_m, two_heights, run_together, one_zigzag, one_hump, stems_and_arches, short_zigzag, uneven):
        assert not _is_wave(shape, 16, np)


def test_the_vibrato_glyph_is_placed_as_a_music_font_places_it():
    """The tab reader takes a wiggle glyph's line as about one em above its box (music fonts draw
    there); the glyph handed on must put that line on the wave."""
    from app.extract.raster_tab import read_image
    from app.extract.rhythm_marks import glyph_ys

    page, _ = read_image(tab_png(engraved_tab_pdf(VIBRATO_STAVES, knockout=True), 1300), 10**8)
    tops = sorted({s.top for s in page.segments if s.top == s.bottom and s.x1 - s.x0 > 200})
    staff_tops = [tops[0]] + [b for a, b in itertools.pairwise(tops) if b - a > 20]
    waves = [c for c in page.chars if c.text == "\ueab0"]
    assert len(waves) == 8
    for wave in waves:
        top = min((t for t in staff_tops if t > glyph_ys(wave)[1]), key=lambda t: t - glyph_ys(wave)[1])
        assert abs(top - glyph_ys(wave)[1] - 14) < 1.2  # the factory draws it 14 points over the top line


TIE_STAVES = [
    [
        [(3, 5), (3, 5, "t"), (2, 8), (2, 8, "(")],
        [(4, 7), (4, 9, "/s"), (4, 7, "/s"), (5, 6, "T")],
        [],
        [(2, 3), (2, 3, "t"), (2, 3, "t"), (6, 3)],
    ],
    [
        [(6, 2), (6, 2, "t"), (3, 7), (3, 9, "/s")],
        [(5, 0), (2, 13), (2, 13, "tT")],
        [],
        [(4, 6), (4, 6, "("), (1, 8), (1, 8, "t")],
    ],
]


def _tie_notes(gp5: bytes) -> list[tuple]:
    import guitarpro as gp

    song = gp.parse(io.BytesIO(gp5))
    return [
        (
            index,
            note.string,
            note.value,
            note.type.name,
            note.effect.ghostNote,
            sorted(s.name for s in note.effect.slides),
        )
        for index, measure in enumerate(song.tracks[0].measures)
        for beat in measure.voices[0].beats
        for note in beat.notes
    ]


# Ties ending right at the tied number's parenthesis, close enough to touch it in a picture.
TOUCHING_TIES = [
    [
        [(1, 1), (3, 7), (3, 7, "t"), (3, 7, "tT")],
        [],
        [(3, 10), (3, 12, "s/"), (6, 13)],
        [(3, 6), (3, 4), (3, 4, "t")],
    ],
    [
        [(2, 12), (1, 3), (1, 3, "t"), (2, 1, "T")],
        [],
        [(1, 7), (1, 7, "("), (1, 7, "t"), (6, 1)],
        [(1, 7), (1, 7, "t"), (1, 7, "t"), (5, 9)],
    ],
]


@pytest.mark.parametrize("width", [1000, 1300, 1600])
@pytest.mark.parametrize("staves", [TIE_STAVES, TOUCHING_TIES], ids=["ties", "touching"])
def test_ties_and_slurs_in_a_picture_are_read_as_in_the_pdf(staves, width):
    """Arcs over the strings, read from the picture as from the PDF: a tie into a parenthesised
    note (a parenthesised note no arc reaches is a ghost note), a slur over a slide (legato),
    ties one after another, a tie over the bar line into an empty bar (cut in two by the bar
    line when the lines are removed), and ties touching the parenthesis they end at."""
    pdf = engraved_tab_pdf(staves, knockout=True)
    expected = _tie_notes(convert(pdf, ConversionOptions()).gp5)
    assert sum(1 for n in expected if n[3] == "tie") >= 8
    assert _tie_notes(convert(tab_png(pdf, width), ConversionOptions()).gp5) == expected


def test_the_tie_page_has_every_kind_of_arc():
    expected = _tie_notes(convert(engraved_tab_pdf(TIE_STAVES, knockout=True), ConversionOptions()).gp5)
    assert any(n[4] for n in expected) and any("legatoSlideTo" in n[5] for n in expected)


def test_no_arc_is_made_up_on_a_page_without_any():
    """A made-up arc beside a parenthesised note would tell the reader the page draws its ties as
    arcs, and every other parenthesised note would turn into a ghost note: none must be found on
    a page with parentheses, bends, slides, vibrato and words over the staff but no arcs."""
    from app.extract import raster_tab

    staves = [
        [[(3, 5), (3, 5, "("), (4, 7, "b"), (6, 3)], [(1, 12, "~"), (2, 9, "("), (5, 4, "<"), (5, 2, ">")]],
        [[(4, 9), (4, 7, "/"), (2, 10, "("), (3, 2, "b")], [(6, 0, "~"), (1, 3), (1, 3, "("), (2, 1)]],
    ]
    words = [
        (0, 62, "una corda", "Times-Italic", 7),
        (0, 300, "minimum", "Helvetica-Bold", 8),
        (1, 200, "nun", "Helvetica", 9),
    ]
    pdf = engraved_tab_pdf(staves, knockout=True, words=words, signatures=[(0, 0, 4, 4)])
    found: list = []
    original = raster_tab._arcs
    raster_tab._arcs = lambda *args: found.extend(original(*args)) or []
    try:
        for width in (1000, 1300, 1600):
            raster_tab.read_image(tab_png(pdf, width), 10**8)
    finally:
        raster_tab._arcs = original
    assert found == []


def test_an_arc_is_one_thin_stroke_curving_one_way():
    import cv2
    import numpy as np

    from app.extract.raster_tab import _arc_chain, _is_arc

    def drawn(points, thickness=1):
        canvas = np.zeros((60, 200), np.uint8)
        cv2.polylines(canvas, [np.array(points, np.int32)], False, 1, thickness)
        ys, xs = np.nonzero(canvas)
        return xs, ys

    def arc(x0, x1, y, rise):
        t = np.linspace(0, 1, 40)
        return [(x0 + (x1 - x0) * s, y - 4 * rise * s * (1 - s)) for s in t]

    def art(text):
        ys, xs = np.nonzero(np.array([[ch == "#" for ch in row] for row in text.split()]))
        return xs, ys

    letters = art(  # letters run together over the staff, where an arc was once seen
        """
        ###...........###....###
        ###........#..###....###
        ###.......#######....##.
        ####......#######...###.
        .####...####.###....###.
        .##########..###....###.
        ..########...###....###.
        ......#.................
        """
    )
    assert _is_arc(*drawn(arc(10, 60, 30, 6)), 16, np)
    assert _is_arc(*drawn([(x, 2 * y - 20) for x, y in arc(10, 60, 30, -3)]), 16, np)  # drawn under
    assert not _is_arc(*drawn([(10, 30), (60, 24)]), 16, np)  # a straight slide
    assert not _is_arc(*drawn([(10, 40), (14, 30), (30, 30), (60, 34)]), 16, np)  # bend: rises at one end
    wave = [(10 + i * 4, 30 + (4 if i % 2 else 0)) for i in range(13)]
    assert not _is_arc(*drawn(wave), 16, np)  # a vibrato
    assert not _is_arc(*letters, 16, np)
    xs, ys = drawn(arc(10, 60, 30, 6))
    broken = (xs < 32) | (xs > 38)
    assert not _is_arc(xs[broken], ys[broken], 16, np)  # not drawn across: a gap in the middle
    canvas_xs, canvas_ys = drawn(arc(10, 60, 30, 6) + [(60, 30)])
    mark_xs, mark_ys = drawn([(33, 27), (36, 27)])  # a second stroke under it: a letter's bowl
    assert not _is_arc(np.concatenate([canvas_xs, mark_xs]), np.concatenate([canvas_ys, mark_ys]), 16, np)
    assert not _is_arc(*drawn([(10 + i, 22 + 0.006 * (i - 10) ** 2) for i in range(51)]), 16, np)  # ends apart
    xs, ys = drawn(arc(10, 60, 30, 6) + arc(60, 110, 30, 6))  # two slurs meeting on one note
    parts = _arc_chain(xs, ys, 16, np)
    assert len(parts) == 2 and all(_is_arc(px, py, 16, np) for px, py in parts)


BEND_STAVES = [
    [[(3, 5, "b"), (2, 8), (4, 7)], [(4, 7, "B"), (6, 3), (2, 8)], [(2, 9, "bR"), (5, 9), (3, 7)]],
    [[(5, 6, "BR"), (1, 3), (2, 3)], [(3, 7, "^"), (5, 2), (1, 5)], [(6, 5, "b"), (4, 2), (2, 3)]],
]


def _bends(gp5: bytes) -> list[tuple]:
    import guitarpro as gp

    song = gp.parse(io.BytesIO(gp5))
    return [
        (
            note.string,
            note.value,
            note.type.name,
            (note.effect.bend.type.name, note.effect.bend.value) if note.effect.bend else None,
        )
        for measure in song.tracks[0].measures
        for beat in measure.voices[0].beats
        for note in beat.notes
    ]


@pytest.mark.parametrize("width", [1300, 1600])
def test_bends_in_a_picture_are_read_as_in_the_pdf(width):
    """A bend's arrowhead over the staff with the curve rising to it from the note, its amount
    over it ("full", "1/2"), a release (an arrowhead pointing down at the end of a curve back)
    and a pre-bend (a straight arrow up from the number): read from the picture as from the PDF,
    from the top string to the bottom one."""
    pdf = engraved_tab_pdf(BEND_STAVES, knockout=True)
    expected = _bends(convert(pdf, ConversionOptions()).gp5)
    kinds = {b for *_, b in expected if b}
    assert {("bend", 100), ("bend", 50), ("bendRelease", 100), ("bendRelease", 50), ("prebend", 100)} <= kinds
    assert _bends(convert(tab_png(pdf, width), ConversionOptions()).gp5) == expected


def test_no_bend_is_made_up_from_words_or_a_tempo_mark():
    """Bold letters over the staff and the tempo mark's filled note head with its stem look like
    arrowheads with a stroke: none of them becomes a bend."""
    from app.extract import raster_tab

    words = [
        (0, 62, "AVA", "Helvetica-Bold", 9),
        (0, 200, "VAMP", "Times-Bold", 8),
        (0, 330, "full", "Helvetica-Bold", 7),
        (1, 62, "T Y", "Helvetica-Bold", 9),
        (1, 200, "1/2", "Helvetica-Bold", 8),
    ]
    staves = [[[(3, 5), (2, 8), (4, 7)], [(4, 7), (6, 3, "("), (2, 8)]]] * 2
    pdf = engraved_tab_pdf(staves, knockout=True, words=words, heading=("Invented Song", "Nobody", 120))
    found: list = []
    original = raster_tab._bends

    def spy(*args):
        out = original(*args)
        found.extend(out[0])
        return out

    raster_tab._bends = spy
    try:
        for width in (1000, 1300, 1600):
            assert not any(b for *_, b in _bends(convert(tab_png(pdf, width), ConversionOptions()).gp5))
    finally:
        raster_tab._bends = original
    assert found == []


def test_an_arrowhead_is_a_triangle_narrowing_to_a_point():
    import numpy as np

    from app.extract.raster_tab import _arrowhead

    def art(text):
        return np.array([[ch == "#" for ch in row] for row in text.split()])

    up_with_stroke = art(  # an arrowhead with the bend's stroke hanging from its base
        """
        ......#......
        .....###.....
        .....###.....
        ....#####....
        ....#####....
        ...#######...
        ...#######...
        ...#######...
        .....###.....
        .....###.....
        .....###.....
        .....###.....
        .....###.....
        """
    )
    down_with_stroke = art(  # a release's arrowhead, the curve coming in from above on a slant
        """
        ....###........
        .....##........
        .....###.......
        ...#######.....
        ...#######.....
        ...#######.....
        ...#######.....
        ....####.......
        .....###.......
        .....##........
        ......#........
        """
    )
    blob = art(  # a solid square (a filled letter, a blot): no tip on either side
        """
        .#######.
        .#######.
        .#######.
        .#######.
        .#######.
        """
    )
    assert _arrowhead(up_with_stroke, 6, (3, 8), 16, np)[0] == "up"
    assert _arrowhead(down_with_stroke, 6, (3, 8), 16, np)[0] == "down"
    assert _arrowhead(blob, 4, (0, 5), 16, np) is None
    small = art(  # a narrow triangle, a quarter of a space wide: part of a digit, not an arrow
        """
        .#..
        .#..
        .##.
        .##.
        ####
        ####
        """
    )
    assert _arrowhead(small, 1, (4, 6), 16, np) is None


@pytest.mark.parametrize("width", [900, 1300])
def test_chords_whose_digits_touch(width):
    """A songbook print: the digits of each chord as tall as the space between the strings, so in a
    small picture they touch one above the other. The column they make is not a bar line, and each
    digit is read on its own string."""
    from app.extract.engraved_tab import extract_engraved_systems
    from app.extract.raster_tab import read_image
    from tests.pdf_factory import chord_tab_pdf

    a = [(2, 2), (3, 2), (4, 2), (5, 0)]
    d = [(1, 2), (2, 3), (3, 2), (4, 0)]
    e = [(1, 0), (2, 0), (3, 1), (4, 2), (5, 2), (6, 0)]
    measures = [[a, a, d, d], [e, e, e, e], [a, d, e, a]]
    picture = tab_png(chord_tab_pdf(measures), width=width)
    page, _ = read_image(picture, 40_000_000)
    systems = extract_engraved_systems(page)
    events = sorted((ev.x, ev.string, ev.fret) for s in systems for ev in s.events if ev.fret is not None)
    chords: list[list[tuple[int, int]]] = []  # the digits of a chord are within a few units of each other
    for i, (x, string, fret) in enumerate(events):
        if not i or x - events[i - 1][0] > 3:
            chords.append([])
        chords[-1].append((string, fret))
    assert [sorted(chord) for chord in chords] == [sorted(chord) for bar in measures for chord in bar]
    assert convert(picture, ConversionOptions()).report["measures"] == 3


def test_rhythm_printed_as_in_a_tab_book():
    """A tab book's rhythm: each stem hangs from the chord's lowest digit (so the stems end at
    different heights, and a short one is still a quarter), a lone 8th's flag rises from the stem's
    end, 8ths are beamed, an 8th rest sits between the middle lines. Every bar keeps the printed
    rhythm, not one estimated from the spacing."""
    import guitarpro

    from tests.pdf_factory import songbook_tab_pdf

    a = [(2, 2), (3, 2), (4, 2), (5, 0)]
    d = [(1, 2), (2, 3), (3, 2), (4, 0)]
    e = [(1, 0), (2, 0), (3, 1), (4, 2), (5, 2), (6, 0)]
    measures = [
        [("4", a), ("4", a), ("r8",), ("8f", d), ("4", d)],
        [("8", e)] * 4 + [("4", e), ("4", e)],
        [("4", a), ("4", d), ("r8",), ("8f", e), ("4", e)],
    ]
    result = convert(tab_png(songbook_tab_pdf(measures), 1300), ConversionOptions())
    assert result.report["tracks"][0]["rhythm_from_notation"] == 3
    song = guitarpro.parse(io.BytesIO(result.gp5))
    durations = [
        [(beat.duration.value, beat.status.name == "rest") for beat in measure.voices[0].beats]
        for measure in song.tracks[0].measures
    ]
    q, e8, r8 = (4, False), (8, False), (8, True)
    assert durations == [[q, q, r8, e8, q], [e8, e8, e8, e8, q, q], [q, q, r8, e8, q]]


def test_half_notes_ringed_as_in_a_tab_book():
    """A tab book rings the numbers of a half note (an empty ring with a stem: a half note tied
    over from the chord before), and hangs each stem from the chord's lowest number, so a chord's stem crosses the strings
    under it; the flag of a lone 8th rises from its short stem back to the staff. Every bar keeps
    the printed rhythm, every number is read and no stem or flag becomes a number."""
    import guitarpro

    from tests.pdf_factory import songbook_tab_pdf

    a = [(2, 2), (3, 2), (4, 2), (5, 0)]
    g = [(2, 0), (3, 0), (4, 0)]
    d = [(1, 2), (2, 3), (3, 2), (4, 0)]
    measures = [
        [("2", a), ("8", g), ("8", d), ("4", g)],
        [("2t",), ("8f", g), ("r8",), ("4", d)],
        [("4", a), ("4", g), ("2", d)],
    ]
    result = convert(tab_png(songbook_tab_pdf(measures), 1300), ConversionOptions())
    assert result.report["tracks"][0]["rhythm_from_notation"] == 3
    song = guitarpro.parse(io.BytesIO(result.gp5))
    read = [
        [
            (beat.duration.value, beat.status.name == "rest", sorted((n.string, n.value) for n in beat.notes))
            for beat in m.voices[0].beats
        ]
        for m in song.tracks[0].measures
    ]
    assert read == [
        [(2, False, a), (8, False, g), (8, False, d), (4, False, g)],
        [(2, False, g), (8, False, g), (8, True, []), (4, False, d)],  # the ring tied over: the G goes on
        [(4, False, a), (4, False, g), (2, False, d)],
    ]


def test_a_tall_lone_seven_in_the_staff_is_an_8th_rest():
    """An 8th rest read whole as a "7", its shape joined to something else so of no rest's size:
    taller than a digit and alone in its column, it is an 8th rest. A "7" stacked in a chord is not."""
    import numpy as np

    from app.extract.pdf_reader import Char
    from app.extract.raster_tab import _rests

    spacing, k = 16.0, 7 / 16
    ys = [100 + i * spacing for i in range(6)]
    groups = [[(y, round(y), round(y), 50, 950) for y in ys]]
    empty = np.zeros((300, 1000), bool)

    def seven(x, top, height):
        return Char("7", x * k, (x + 13) * k, top * k, (top + height) * k)

    lone = seven(300, ys[2] - 2, 18)  # between the middle lines, 1.1 spaces tall
    stacked = seven(600, ys[2] - 2, 18)
    neighbour = Char("2", 601 * k, 613 * k, (ys[3] + 1) * k, (ys[3] + 15) * k)
    short = seven(800, ys[2] - 6, 13)  # a digit's height: a fret
    rests, _, misread = _rests(empty, empty, groups, spacing, k, [lone, stacked, neighbour, short])
    assert [c.text for c in rests] == [""] and misread == [lone]


def test_a_bold_blurred_zero_is_read_again_from_its_darkest_pixels():
    """A bold 0 in a JPEG of a tab book: the grey around its strokes closes the hole, the box is
    nearly filled in and the recogniser reads a 6. Read again from the darkest pixels it is a 0. A
    crisp 6 (its box far from filled) is left as read."""
    import cv2
    import numpy as np

    from app.extract.raster_tab import _bold_zeros

    def ink_box(gray):
        ys, xs = np.nonzero(gray < 200)
        return gray[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]

    zero = np.full((40, 30), 255, np.uint8)
    cv2.ellipse(zero, (15, 20), (9, 15), 0, 0, 360, 170, 9)  # the grey that closes the hole
    cv2.ellipse(zero, (15, 20), (8, 14), 0, 0, 360, 40, 4)  # the stroke, the hole open
    six = np.full((40, 30), 255, np.uint8)
    cv2.putText(six, "6", (2, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 40, 4)
    for gray, expected in ((ink_box(zero), "0"), (ink_box(six), "6")):
        results = ["6"]
        _bold_zeros(results, [(0, gray.shape[1], 0, gray.shape[0])], [gray < 200], gray, 6, cv2, np)
        assert results == [expected]


def _graces(gp5: bytes) -> list[tuple[int, int, int | None]]:
    import guitarpro as gp

    song = gp.parse(io.BytesIO(gp5))
    return [
        (note.string, note.value, note.effect.grace.fret if note.effect.grace else None)
        for measure in song.tracks[0].measures
        for beat in measure.voices[0].beats
        for note in beat.notes
    ]


@pytest.mark.parametrize("width", [1300, 1600, 2000])
def test_small_numbers_in_a_picture_are_grace_notes_as_in_the_pdf(width):
    """A grace note printed small before its note: in a picture its digits are shorter than the
    others too (by less than in the PDF's font sizes: a round 9 stands taller than a flat 1)."""
    staves = [
        [[(3, 14, "g"), (3, 16), (2, 5)], [(4, 9, "g"), (4, 12), (1, 3)]],
        [[(2, 7, "g"), (2, 10), (3, 2)], [(5, 3), (5, 5)]],
    ]
    pdf = engraved_tab_pdf(staves, knockout=True)
    expected = _graces(convert(pdf, ConversionOptions()).gp5)
    assert [g for _, _, g in expected if g] == [14, 9, 7]
    assert _graces(convert(tab_png(pdf, width=width), ConversionOptions()).gp5) == expected
