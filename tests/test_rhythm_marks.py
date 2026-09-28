"""Rhythm notation under an engraved tab staff, on synthetic page geometry."""

from app.extract.pdf_reader import Char, Page, Segment
from app.extract.rhythm_marks import read_rhythm
from app.model import RhythmMark, TabEvent, TabSystem
from app.rhythm import RhythmOptions, RhythmStats, build_measures

SPACING = 10.0
TOP, BOTTOM = 100.0, 150.0  # 6 strings, 10pt apart
STEM_TOP, STEM_BOTTOM = BOTTOM + 5, BOTTOM + 25


def _stem(x: float, bottom: float = STEM_BOTTOM) -> Segment:
    return Segment(x, x, STEM_TOP, bottom)


def _beam(x0: float, x1: float, level: int = 0) -> Segment:
    top = STEM_BOTTOM - 3 - level * 5
    return Segment(x0, x1, top, top + 3)


def _read(segments=(), curves=(), chars=()) -> list[RhythmMark]:
    page = Page(1, 600, 800, list(chars), list(segments), list(curves))
    return read_rhythm(page, TOP, BOTTOM, 0, 500, SPACING)


def test_beams_quarter_half_and_dotted():
    marks = _read(
        segments=[_stem(20), _stem(40), _stem(60), _stem(80), _stem(100), _stem(120, STEM_TOP + 11)],
        curves=[
            _beam(20, 40),
            _beam(60, 80),
            _beam(60, 80, level=1),
            Segment(83, 85.5, STEM_BOTTOM - 1, STEM_BOTTOM + 1.5),
        ],
    )
    assert [m.units for m in marks] == [4, 4, 2, 3, 8, 16]  # 8th, 8th, 16th, dotted 16th, quarter, half


def test_rest_glyph_and_tuplet_number():
    rest = Char("", 200, 210, BOTTOM + 10, BOTTOM + 50)  # glyph box offset below the staff
    tuplet = Char("3", 30, 35, STEM_BOTTOM + 2, STEM_BOTTOM + 8)
    marks = _read(segments=[_stem(20), _stem(40)], curves=[_beam(20, 40)], chars=[rest, tuplet])
    assert [(m.units, m.is_rest) for m in marks] == [(None, False), (None, False), (8, True)]


def test_staff_without_stems_has_no_marks():
    assert _read(segments=[Segment(0, 500, TOP, TOP)]) == []


def _system(events, rhythm):
    return TabSystem(
        page=1,
        string_count=6,
        events=events,
        bars=[0.0, 100.0],
        start_x=0,
        end_x=100,
        char_width=6.0,
        source="engraved",
        rhythm=rhythm,
    )


def test_notated_bar_uses_printed_durations_and_rests():
    events = [TabEvent(x=10, string=1, fret=0), TabEvent(x=20, string=1, fret=2), TabEvent(x=60, string=1, fret=3)]
    rhythm = [RhythmMark(10, 4), RhythmMark(20, 4), RhythmMark(40, 8, is_rest=True), RhythmMark(60, 16)]
    stats = RhythmStats()
    measures = build_measures([_system(events, rhythm)], RhythmOptions(), [], None, stats)
    assert [(b.units, [n.fret for n in b.notes]) for b in measures[0].beats] == [(4, [0]), (4, [2]), (8, []), (16, [3])]
    assert (stats.notated, stats.estimated) == (1, 0)


def test_stemless_single_note_is_a_whole_note():
    events = [TabEvent(x=10, string=2, fret=5)]
    measures = build_measures([_system(events, [RhythmMark(500, 4)])], RhythmOptions(), [])
    assert [(b.units, len(b.notes)) for b in measures[0].beats] == [(32, 1)]


def test_mismatching_notation_falls_back_to_spacing():
    events = [TabEvent(x=10, string=1, fret=0), TabEvent(x=50, string=1, fret=2)]
    stats = RhythmStats()
    measures = build_measures(
        [_system(events, [RhythmMark(10, 4), RhythmMark(50, 4)])], RhythmOptions(), [], None, stats
    )
    assert sum(b.units for b in measures[0].beats) == 32
    assert (stats.notated, stats.estimated) == (0, 1)
