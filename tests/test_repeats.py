"""Repeats and time signatures from the PDF to the GP5 file."""

import io

import guitarpro as gp

from app.converter import ConversionOptions, convert
from tests.pdf_factory import ascii_tab_pdf

TAB = [
    "e|:-0---3-:|-5---5-|   x3",
    "B|--1------|-------|",
    "G|:-------:|-------|",
    "D|---------|-------|",
    "A|---------|-------|",
    "E|---------|-------|",
]


def test_text_tab_repeat_reaches_the_gp5():
    result = convert(ascii_tab_pdf([TAB]), ConversionOptions())
    headers = gp.parse(io.BytesIO(result.gp5)).measureHeaders
    assert [h.isRepeatOpen for h in headers] == [True, False]
    assert [h.repeatClose for h in headers] == [2, -1]  # played 3 times in all
    assert result.report["repeats"] == 1
    assert result.report["time_signature_changes"] == []
    assert "x3" in result.report["tracks"][0]["preview"]


def test_user_time_signature_replaces_only_the_opening_one():
    from app.converter import _drop_opening_signature
    from app.model import TabSystem

    first = TabSystem(1, 6, [], [0, 100], 0, 100, 6, time_signatures=[(5, 4, 4)])
    second = TabSystem(1, 6, [], [0, 100], 0, 100, 6, time_signatures=[(5, 3, 4)])
    _drop_opening_signature([first, second])
    assert first.time_signatures == [] and second.time_signatures == [(5, 3, 4)]


def test_repeats_written_out_for_rocksmith():
    result = convert(ascii_tab_pdf([TAB]), ConversionOptions(expand_repeats=True))
    song = gp.parse(io.BytesIO(result.gp5))
    assert len(song.measureHeaders) == 4  # bar 1 three times, then bar 2
    assert not any(h.isRepeatOpen or h.repeatClose > 0 or h.repeatAlternative for h in song.measureHeaders)
    frets = [[n.value for b in m.voices[0].beats for n in b.notes] for m in song.tracks[0].measures]
    assert frets[0] == frets[1] == frets[2] != frets[3]
    assert result.report["repeats"] == 1 and result.report["repeats_expanded"]
    assert result.report["measures"] == 4


def test_written_out_repeat_copies_the_lyrics_of_each_pass():
    from app.converter import _expand_repeats
    from app.model import Score, ScoreBeat, ScoreMeasure

    score = Score(6, [64] * 6, [ScoreMeasure([ScoreBeat(32)], repeat_times=2), ScoreMeasure([ScoreBeat(32)])], 4, 4)
    report = {"_lyrics": [(1, 0.0, "la", False), (2, 0.5, "end", False)]}
    _expand_repeats([score], [report], [0, 0, 1])
    assert report["_lyrics"] == [(1, 0.0, "la", False), (2, 0.0, "la", False), (3, 0.5, "end", False)]
    assert [m.number for m in score.measures] == [1, 2, 3] and not any(m.repeat_times for m in score.measures)
    assert score.measures[0] is not score.measures[1]
