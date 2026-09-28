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
