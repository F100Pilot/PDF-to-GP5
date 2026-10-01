"""Rhythm notation under an engraved tab staff, on synthetic page geometry."""

from app.extract.pdf_reader import Char, Page, Segment
from app.extract.rhythm_marks import read_rhythm
from app.model import RhythmMark, TabEvent, TabSystem
from app.rhythm import RhythmOptions, RhythmStats, build_measures

SPACING = 10.0
TOP, BOTTOM = 100.0, 150.0  # 6 strings, 10pt apart
STEM_TOP, STEM_BOTTOM = BOTTOM + 5, BOTTOM + 25


def _stem(x: float, top: float = STEM_TOP) -> Segment:
    return Segment(x, x, top, STEM_BOTTOM)  # stems share their far end; half notes start lower


def _beam(x0: float, x1: float, level: int = 0) -> Segment:
    top = STEM_BOTTOM - 3 - level * 5
    return Segment(x0, x1, top, top + 3)


def _read(segments=(), curves=(), chars=()) -> list[RhythmMark]:
    page = Page(1, 600, 800, list(chars), list(segments), list(curves))
    return read_rhythm(page, TOP, BOTTOM, 0, 500, SPACING)


def test_beams_quarter_half_and_dotted():
    marks = _read(
        segments=[_stem(20), _stem(40), _stem(60), _stem(80), _stem(100), _stem(120, STEM_BOTTOM - 9)],
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


def test_bracketed_three_makes_a_triplet():
    """ "3" between the arms of a bracket under three beamed eighths: written eighths, played as a
    triplet; the quarter after it is not part of it."""
    three = Char("3", 38, 43, STEM_BOTTOM + 3, STEM_BOTTOM + 9)
    arms = [Segment(18, 36, STEM_BOTTOM + 6, STEM_BOTTOM + 6), Segment(45, 62, STEM_BOTTOM + 6, STEM_BOTTOM + 6)]
    marks = _read(segments=[_stem(20), _stem(40), _stem(60), _stem(80), *arms], curves=[_beam(20, 60)], chars=[three])
    assert [(m.units, m.tuplet) for m in marks] == [(4, True), (4, True), (4, True), (8, False)]


def test_line_of_only_half_notes_reads_them_as_half_notes():
    """Half-note stems are half as long; with no other stem on the line they are still halves."""
    marks = _read(segments=[_stem(20, STEM_BOTTOM - 10), _stem(200, STEM_BOTTOM - 10)])
    assert [m.units for m in marks] == [16, 16]


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


def test_triplet_bar_sums_to_the_bar_and_keeps_the_written_lengths():
    events = [TabEvent(x=x, string=3, fret=f) for x, f in ((10, 9), (20, 11), (30, 9), (50, 7), (70, 5))]
    rhythm = [*(RhythmMark(x, 4, tuplet=True) for x in (10, 20, 30)), RhythmMark(50, 8), RhythmMark(70, 16)]
    stats = RhythmStats()
    measures = build_measures([_system(events, rhythm)], RhythmOptions(), [], None, stats)
    assert [(b.units, b.tuplet) for b in measures[0].beats] == [(4, True)] * 3 + [(8, False), (16, False)]
    assert measures[0].units == 32 and (stats.notated, stats.estimated) == (1, 0)


def test_tie_into_an_empty_bar_holds_the_notes_through_it():
    system = _system([TabEvent(x=10, string=1, fret=9)], [RhythmMark(10, 32)])
    system.bars, system.end_x, system.tied_bars = [0.0, 100.0, 200.0], 200, [100.0]
    measures = build_measures([system], RhythmOptions(), [])
    assert [(b.units, [(n.fret, n.tie) for n in b.notes]) for b in measures[1].beats] == [(32, [(9, True)])]


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


def test_stem_without_fret_ties_the_previous_notes():
    events = [TabEvent(x=10, string=2, fret=7), TabEvent(x=10, string=3, fret=5)]
    rhythm = [RhythmMark(10, 16), RhythmMark(50, 16)]  # second stem has no fret above it
    measures = build_measures([_system(events, rhythm)], RhythmOptions(), [])
    second = measures[0].beats[1]
    assert second.units == 16 and [(n.string, n.fret, n.tie) for n in second.notes] == [(2, 7, True), (3, 5, True)]


def test_tied_continuation_keeps_the_dynamic():
    """A stem-only tie is not re-struck: it keeps the note's velocity (else the score shows a
    dynamic change to the default f in the middle of the bar)."""
    events = [TabEvent(x=10, string=2, fret=7, velocity=79)]
    measures = build_measures([_system(events, [RhythmMark(10, 16), RhythmMark(50, 16)])], RhythmOptions(), [])
    assert [n.velocity for n in measures[0].beats[1].notes] == [79]


def _flag(x: float) -> Char:
    # Music-font glyph box reported about one em below the drawn flag (as in MuseScore PDFs).
    return Char("", x, x + 5, STEM_BOTTOM + 8, STEM_BOTTOM + 28)


def _dot(x: float) -> Char:
    return Char("", x, x + 3, STEM_TOP + 18, STEM_TOP + 38)


def test_flags_and_dots_with_offset_glyph_boxes():
    marks = _read(segments=[_stem(20), _stem(60), _stem(100, STEM_BOTTOM - 9)], chars=[_dot(24), _flag(60)])
    assert [m.units for m in marks] == [12, 4, 16]  # dotted quarter, flagged eighth, half


def test_stems_must_share_their_far_end():
    tick = Segment(200, 200, STEM_TOP + 10, STEM_BOTTOM + 12)  # e.g. end of a "P.M." line
    assert [m.x for m in _read(segments=[_stem(20), _stem(40), tick])] == [20, 40]


def test_lone_note_on_stemless_line_is_a_whole_note_when_part_has_rhythm():
    notated = _system([TabEvent(x=10, string=1, fret=0)], [RhythmMark(10, 32)])
    stemless = _system([TabEvent(x=40, string=2, fret=7)], [])
    stats = RhythmStats()
    measures = build_measures([notated, stemless], RhythmOptions(), [], None, stats)
    assert (stats.notated, stats.estimated) == (2, 0)
    assert [b.units for b in measures[1].beats] == [32]


def test_stems_of_the_staff_above_are_not_taken():
    """Staves printed close together: the stems hanging from the staff above end two spaces or
    more over this one. They are more than this staff's own, yet its own (starting 2/3 of a space
    under it) are its rhythm."""
    above = [Segment(x, x, TOP - 45, TOP - 25) for x in (30, 60, 90)]  # their ends 2.5 spaces up
    marks = _read(segments=[*above, _stem(40), _stem(80)])
    assert [m.x for m in marks] == [40, 80]
