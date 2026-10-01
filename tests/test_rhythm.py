import random

import pytest

from app.model import Link, TabEvent, TabSystem
from app.rhythm import REPRESENTABLE_UNITS, RhythmOptions, _quantize, build_measures, split_units


def _system(events, bars, start=0.0, end=100.0, source="ascii"):
    return TabSystem(
        page=1, string_count=6, events=events, bars=bars, start_x=start, end_x=end, char_width=1.0, source=source
    )


@pytest.mark.parametrize("units", range(1, 97))
def test_split_units_sums_and_is_representable(units):
    parts = split_units(units)
    assert sum(parts) == units
    assert all(p in REPRESENTABLE_UNITS for p in parts)


def test_quantize_even_quarters():
    assert _quantize([0, 4, 8, 12], origin=0, end=16, units=32) == [0, 8, 16, 24]


def test_quantize_prefers_bar_consistent_scale():
    # "|-0---3---5h7---|": sloppy trailing padding still yields Q Q E Q.
    assert _quantize([3, 7, 11, 13], origin=3, end=17, units=32) == [0, 8, 16, 20]


def test_quantize_sixteenths():
    xs = [float(i) for i in range(16)]
    assert _quantize(xs, origin=0, end=16, units=32) == list(range(0, 32, 2))


def test_every_measure_is_exactly_full():
    rng = random.Random(1234)
    for numerator, denominator in [(4, 4), (3, 4), (6, 8), (7, 8), (5, 4), (2, 2)]:
        options = RhythmOptions(mode="spacing", numerator=numerator, denominator=denominator)
        for _ in range(50):
            xs = sorted(rng.sample(range(2, 60), rng.randint(1, 20)))
            events = [TabEvent(x=float(x), string=rng.randint(1, 6), fret=rng.randint(0, 24)) for x in xs]
            measures = build_measures([_system(events, [0.0, 30.0, 62.0], end=62.0)], options, [])
            for measure in measures:
                assert sum(b.units for b in measure.beats) == options.measure_units
                assert all(b.units in REPRESENTABLE_UNITS for b in measure.beats)


def test_fixed_mode_rebars_and_pads_with_rests():
    events = [TabEvent(x=float(i * 3), string=1, fret=i) for i in range(10)]
    options = RhythmOptions(mode="fixed", fixed_value=8)
    measures = build_measures([_system(events, [])], options, [])
    assert len(measures) == 2
    assert [len(b.notes) for b in measures[1].beats] == [1, 1, 0]  # two 8ths + dotted half rest
    assert measures[1].beats[-1].units == 24


def test_auto_mode_without_bars_warns_and_uses_fixed():
    warnings = []
    events = [TabEvent(x=float(i), string=1, fret=0) for i in range(4)]
    build_measures([_system(events, [])], RhythmOptions(), warnings)
    assert any("durações fixas" in w for w in warnings)


def test_links_are_moved_to_origin_note():
    events = [
        TabEvent(x=2, string=3, fret=5),
        TabEvent(x=6, string=3, fret=7, link=Link.HAMMER),
        TabEvent(x=10, string=3, fret=9, link=Link.SLIDE_UP),
    ]
    measures = build_measures([_system(events, [0.0, 16.0], end=16.0)], RhythmOptions(mode="spacing"), [])
    notes = [n for b in measures[0].beats for n in b.notes if not n.tie]
    assert notes[0].hammer and not notes[0].slide
    assert notes[1].slide and not notes[1].hammer
    assert not notes[2].hammer and not notes[2].slide


def test_shift_slide_and_slide_in_out_reach_the_notes():
    events = [
        TabEvent(x=2, string=3, fret=5, slide_in="below"),
        TabEvent(x=6, string=3, fret=7, link=Link.SHIFT_SLIDE),
        TabEvent(x=10, string=3, fret=9, slide_out="down"),
    ]
    measures = build_measures([_system(events, [0.0, 16.0], end=16.0)], RhythmOptions(mode="spacing"), [])
    notes = [n for b in measures[0].beats for n in b.notes if not n.tie]
    assert notes[0].slide_shift and not notes[0].slide and notes[0].slide_in == "below"
    assert not notes[1].slide_shift
    assert notes[2].slide_out == "down"


def test_chord_columns_merge_and_duplicates_warn():
    events = [
        TabEvent(x=2.0, string=1, fret=0),
        TabEvent(x=2.2, string=2, fret=1),
        TabEvent(x=2.1, string=1, fret=3),
    ]
    warnings = []
    measures = build_measures([_system(events, [0.0, 10.0], end=10.0)], RhythmOptions(mode="spacing"), warnings)
    assert len(measures[0].beats[0].notes) == 2
    assert any("sobreposta" in w for w in warnings)


def test_empty_bar_becomes_full_rest():
    events = [TabEvent(x=2.0, string=1, fret=0)]
    measures = build_measures([_system(events, [0.0, 10.0, 20.0], end=20.0)], RhythmOptions(mode="spacing"), [])
    assert len(measures) == 2
    assert all(b.is_rest for b in measures[1].beats)


def test_multi_bar_rest_from_bar_numbers():
    events = [TabEvent(x=2.0, string=1, fret=0)]
    system = _system(events, [0.0, 10.0, 20.0, 30.0], end=30.0, source="engraved")
    system.bar_numbers = [53, 54, 57]  # bar 54 is a 3-bar rest; bar 57 is 1 bar (end of piece)
    counts = []
    measures = build_measures([system], RhythmOptions(mode="spacing"), [], counts)
    assert counts == [5] and len(measures) == 5


def test_multi_bar_rest_uses_next_system_number():
    first = _system([TabEvent(x=2.0, string=1, fret=0)], [0.0, 10.0, 20.0], end=20.0, source="engraved")
    first.bar_numbers = [1, 2]
    second = _system([TabEvent(x=2.0, string=1, fret=0)], [0.0, 10.0], end=10.0, source="engraved")
    second.bar_numbers = [6]
    counts = []
    build_measures([first, second], RhythmOptions(mode="spacing"), [], counts)
    assert counts == [5, 1]


def test_parentheses_are_ties_when_repeating_the_fret_else_ghost():
    events = [
        TabEvent(x=2, string=4, fret=0),
        TabEvent(x=6, string=4, fret=0, parenthesized=True),
        TabEvent(x=10, string=3, fret=5, parenthesized=True),
    ]
    measures = build_measures([_system(events, [0.0, 16.0], end=16.0)], RhythmOptions(mode="spacing"), [])
    marked = {n.string: n for b in measures[0].beats for n in b.notes if n.parenthesized}
    assert marked[4].tie and not marked[4].ghost
    assert marked[3].ghost and not marked[3].tie


def _parenthesized(events):
    measures = build_measures([_system(events, [0.0, 16.0], end=16.0)], RhythmOptions(mode="spacing"), [])
    return [n for b in measures[0].beats for n in b.notes if n.parenthesized]


def test_tie_needs_the_string_sounding_in_the_beat_before():
    # Jet Lag, bars 78-81: the E string rests while G/D/A play, then comes back in parentheses
    events = [
        TabEvent(x=1, string=6, fret=0),
        TabEvent(x=5, string=5, fret=2),
        TabEvent(x=9, string=6, fret=0, parenthesized=True),
    ]
    (again,) = _parenthesized(events)
    assert again.ghost and not again.tie


@pytest.mark.parametrize(("arc", "tied"), [(True, True), (None, True), (False, False)])
def test_where_ties_are_arcs_a_parenthesized_note_without_one_is_a_ghost_note(arc, tied):
    # MuseScore: (2)(2) with no arc between them are two notes, not one held note
    events = [TabEvent(x=2, string=4, fret=2), TabEvent(x=10, string=4, fret=2, parenthesized=True, tie_arc=arc)]
    (second,) = _parenthesized(events)
    assert (second.tie, second.ghost) == (tied, not tied)


def test_parenthesized_repeat_of_a_bent_note_holds_the_bend():
    events = [
        TabEvent(x=2, string=2, fret=15, bend_semitones=2),
        TabEvent(x=10, string=2, fret=15, parenthesized=True),
    ]
    measures = build_measures([_system(events, [0.0, 16.0], end=16.0)], RhythmOptions(mode="spacing"), [])
    held = next(n for b in measures[0].beats for n in b.notes if n.parenthesized)
    assert held.tie and held.bend_semitones == 2 and held.bend_pre


def test_tie_after_unreleased_bend_holds_it():
    from app.model import ScoreBeat, ScoreMeasure, ScoreNote
    from app.rhythm import resolve_links

    bent = ScoreNote(2, 15, bend_semitones=2)
    tied = ScoreNote(2, 15, tie=True)
    resolve_links([ScoreMeasure([ScoreBeat(16, [bent]), ScoreBeat(16, [tied])])])
    assert tied.bend_semitones == 2 and tied.bend_pre


def test_measure_cap_is_enforced():
    import pytest

    from app.converter import ConversionError, ConversionOptions, convert
    from tests.pdf_factory import ascii_tab_pdf

    tab = [
        "e|-0---|-0---|-0---|",
        "B|-----|-----|-----|",
        "G|-----|-----|-----|",
        "D|-----|-----|-----|",
        "A|-----|-----|-----|",
        "E|-----|-----|-----|",
    ]
    with pytest.raises(ConversionError, match="compassos"):
        convert(ascii_tab_pdf([tab]), ConversionOptions(max_measures=2))


def test_time_signature_change_and_repeat_signs_per_bar():
    events = [TabEvent(x=x, string=1, fret=3) for x in (20, 120, 220)]
    system = TabSystem(
        page=1,
        string_count=6,
        events=events,
        bars=[0, 100, 200, 300],
        start_x=0,
        end_x=300,
        char_width=6,
        time_signatures=[(105, 3, 4)],  # printed at the start of bar 2
        repeat_starts=[100],
        repeat_ends=[(200, 2), (300, 3)],
        endings=[(100, 200, (1,)), (200, 300, (2,))],
    )
    measures = build_measures([system], RhythmOptions(numerator=4, denominator=4), [])
    assert [m.time_signature for m in measures] == [(4, 4), (3, 4), (3, 4)]
    assert [sum(b.units for b in m.beats) for m in measures] == [32, 24, 24]
    assert [m.repeat_open for m in measures] == [False, True, False]
    assert [m.repeat_times for m in measures] == [0, 2, 3]
    assert [m.endings for m in measures] == [(), (1,), (2,)]


def test_time_signature_carries_over_to_the_next_line():
    def line(signatures=()):
        return TabSystem(
            1, 6, [TabEvent(x=20, string=1, fret=0)], [0, 100], 0, 100, 6, time_signatures=list(signatures)
        )

    measures = build_measures([line([(5, 6, 8)]), line()], RhythmOptions(), [])
    assert [m.time_signature for m in measures] == [(6, 8), (6, 8)]
    assert [sum(b.units for b in m.beats) for m in measures] == [24, 24]


def test_navigation_marks_and_tempo_go_to_their_bars():
    events = [TabEvent(x=x, string=1, fret=3) for x in (20, 120, 220)]
    system = TabSystem(
        1,
        6,
        events,
        [0, 100, 200, 300],
        0,
        300,
        6,
        tempos=[(110, 90)],
        signs=[(105, "Segno"), (296, "Fine")],
        jumps=[(198, "Da Coda"), (305, "Da Capo al Fine")],
    )
    measures = build_measures([system], RhythmOptions(), [])
    assert [m.tempo for m in measures] == [None, 90, None]
    assert [m.sign for m in measures] == [None, "Segno", "Fine"]
    assert [m.jump for m in measures] == [None, "Da Coda", "Da Capo al Fine"]
