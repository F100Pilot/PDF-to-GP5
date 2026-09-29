"""Playing order with repeats: must match alphaTab's player (orders below were produced by it)."""

import pytest

from app.model import ScoreBeat, ScoreMeasure
from app.repeats import playback_order


def bar(repeat_open=False, times=0, endings=()):
    return ScoreMeasure([ScoreBeat(32)], repeat_open=repeat_open, repeat_times=times, endings=endings)


@pytest.mark.parametrize(
    ("bars", "expected"),
    [
        (
            [bar(True), bar(times=2, endings=(1,)), bar(endings=(2,)), bar(True), bar(times=3)],
            [1, 2, 1, 3, 4, 5, 4, 5, 4, 5],
        ),
        ([bar(True), bar(), bar(times=3, endings=(1, 2)), bar(endings=(3,)), bar()], [1, 2, 3, 1, 2, 3, 1, 2, 4, 5]),
        ([bar(True), bar(times=2), bar(True), bar(times=2), bar()], [1, 2, 1, 2, 3, 4, 3, 4, 5]),
        ([bar(), bar(times=2), bar(), bar(times=3)], [1, 2, 1, 2, 3, 4] * 3),
        ([bar(True), bar(True), bar(times=2), bar(times=2), bar()], [1, 2, 3, 2, 3, 4, 1, 2, 3, 2, 3, 4, 5]),
        ([bar(), bar(True), bar(), bar()], [1, 2, 3, 4]),
        ([bar(), bar(times=2, endings=(1,)), bar(endings=(2,)), bar()], [1, 2, 1, 3, 4]),
    ],
)
def test_order_matches_alphatab(bars, expected):
    assert [i + 1 for i in playback_order(bars)] == expected


def test_order_is_capped():
    assert len(playback_order([bar(True), bar(times=32)] * 3, limit=50)) == 50


def mark(sign=None, jump=None, **kw):
    measure = bar(**kw)
    measure.sign, measure.jump = sign, jump
    return measure


@pytest.mark.parametrize(
    ("bars", "expected"),
    [
        ([mark(), mark(), mark(jump="Da Capo"), mark()], [1, 2, 3, 1, 2, 3, 4]),
        ([mark(), mark("Fine"), mark(), mark(jump="Da Capo al Fine"), mark()], [1, 2, 3, 4, 1, 2]),
        (
            [mark(), mark("Segno"), mark(jump="Da Coda"), mark(), mark(jump="Da Segno al Coda"), mark("Coda"), mark()],
            [1, 2, 3, 4, 5, 2, 3, 6, 7],
        ),
        ([mark(), mark(jump="Da Coda"), mark(jump="Da Capo al Coda"), mark("Coda"), mark()], [1, 2, 3, 1, 2, 4, 5]),
        (
            [mark("Segno", repeat_open=True), mark(times=2), mark("Fine"), mark(jump="Da Segno al Fine")],
            [1, 2, 1, 2, 3, 4, 1, 2, 3],
        ),
        (
            [mark(repeat_open=True), mark(times=2, endings=(1,)), mark(endings=(2,)), mark(jump="Da Capo"), mark()],
            [1, 2, 1, 3, 4, 1, 2, 3, 4, 5],
        ),
        (
            [mark(), mark(repeat_open=True), mark(times=3, jump="Da Coda"), mark(jump="Da Capo al Coda"), mark("Coda")],
            [1, 2, 3, 2, 3, 2, 3, 4, 1, 2, 3, 5],
        ),
        ([mark(), mark(jump="Da Capo al Coda"), mark("Coda"), mark()], [1, 2, 1, 2, 3, 4]),
        ([mark(), mark("Fine"), mark(jump="Da Capo"), mark()], [1, 2, 3, 1, 2, 3, 4]),
        ([mark(), mark(), mark(jump="Da Segno"), mark()], [1, 2, 3, 4]),  # no Segno: ignored
        ([mark(), mark("Fine"), mark()], [1, 2, 3]),
    ],
)
def test_navigation_order_matches_alphatab(bars, expected):
    assert [i + 1 for i in playback_order(bars)] == expected
