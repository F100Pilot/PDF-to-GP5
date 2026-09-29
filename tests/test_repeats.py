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
