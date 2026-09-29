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
