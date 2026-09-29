"""Signs on the bar lines of an engraved staff: time signatures, repeats and voltas.

Editors print them with SMuFL music-font glyphs (MuseScore: time signature digits, repeat dots)
and plain text (repeat counts "x3", volta numbers "1." over a bracket line).
"""

from __future__ import annotations

import re

from .common import repeat_count
from .metadata import COMMON_TIME, CUT_TIME, TIME_SIGNATURE_DIGITS
from .pdf_reader import Char, Page, group_lines
from .rhythm_marks import glyph_ys

REPEAT_DOT = ""
# Whole repeat bar lines drawn as one glyph: start ("|:"), end (":|") and both (":|:").
_REPEAT_GLYPHS = {"": (True, False), "": (False, True), "": (True, True)}
_VOLTA = re.compile(r"^(?P<n>\d(?:\s*[.,]\s*\d)*)\s*\.$")  # "1.", "2.", "1., 2."
DENOMINATORS = (1, 2, 4, 8, 16, 32)


def _drawn_y(char: Char) -> float:
    return glyph_ys(char)[1]  # music-font glyphs sit about one em above their text box


def time_signatures(
    chars: list[Char], top: float, bottom: float, x0: float, x1: float, spacing: float
) -> list[tuple[float, int, int]]:
    """Time signatures on the staff as (x, numerator, denominator).

    Only two stacked rows of digits count: a single row of the same glyphs is the bar count
    printed over a multi-bar rest.
    """
    signs: list[tuple[float, int, int]] = []
    on_staff = [c for c in chars if x0 - spacing <= c.xc <= x1 and top - spacing <= _drawn_y(c) <= bottom + spacing]
    for char in on_staff:
        if char.text == COMMON_TIME:
            signs.append((char.x0, 4, 4))
        elif char.text == CUT_TIME:
            signs.append((char.x0, 2, 2))
    digits = sorted((c for c in on_staff if c.text in TIME_SIGNATURE_DIGITS), key=lambda c: c.x0)
    groups: list[list[Char]] = []
    for char in digits:
        if groups and char.x0 <= max(c.x1 for c in groups[-1]) + 0.2 * (char.x1 - char.x0):
            groups[-1].append(char)
        else:
            groups.append([char])
    for group in groups:
        size = group[0].bottom - group[0].top
        rows: list[list[Char]] = []
        for char in sorted(group, key=_drawn_y):
            if rows and abs(_drawn_y(char) - _drawn_y(rows[-1][0])) <= 0.2 * size:
                rows[-1].append(char)
            else:
                rows.append([char])
        if len(rows) != 2:
            continue
        numerator, denominator = (
            int("".join(str(TIME_SIGNATURE_DIGITS[c.text]) for c in sorted(row, key=lambda c: c.x0))) for row in rows
        )
        if 1 <= numerator <= 32 and denominator in DENOMINATORS:
            signs.append((min(c.x0 for c in group), numerator, denominator))
    return sorted(signs)


def _nearest(bars: list[float], x: float, limit: float) -> float | None:
    best = min(bars, key=lambda b: abs(b - x), default=None)
    return best if best is not None and abs(best - x) <= limit else None


def repeat_signs(
    chars: list[Char], top: float, bottom: float, spacing: float, bars: list[float]
) -> tuple[list[float], list[float]]:
    """Bar lines opening and closing a repeat (x of the bar line in ``bars``).

    Repeat dots right of a bar line open a repeat, dots left of it close one; at least two dots
    (one per staff space pair) must line up, so a stray dot is not a repeat.
    """
    starts: list[float] = []
    ends: list[float] = []
    dots = sorted(
        (
            c
            for c in chars
            if c.text == REPEAT_DOT and any(top - 0.5 * spacing <= y <= bottom + 0.5 * spacing for y in glyph_ys(c))
        ),
        key=lambda c: c.xc,
    )
    columns: list[list[Char]] = []
    for dot in dots:
        if columns and dot.xc - columns[-1][0].xc <= 0.5 * spacing:
            columns[-1].append(dot)
        else:
            columns.append([dot])
    for column in columns:
        if len(column) < 2:
            continue
        x = column[0].xc
        bar = _nearest(bars, x, 2 * spacing)
        if bar is not None:
            (starts if x > bar else ends).append(bar)
    for char in chars:
        kind = _REPEAT_GLYPHS.get(char.text)
        if kind and any(top - spacing <= y <= bottom + spacing for y in glyph_ys(char)):
            bar = _nearest(bars, char.xc, 2 * spacing)
            if bar is not None:
                if kind[0]:
                    starts.append(bar)
                if kind[1]:
                    ends.append(bar)
    return sorted(set(starts)), sorted(set(ends))


def _texts_above(page: Page, top: float, x0: float, x1: float, spacing: float, height: float) -> list[tuple[Char, str]]:
    """Words printed above the staff (up to ``height`` staff spaces) as (first char, text)."""
    chars = [
        c
        for c in page.chars
        if not ("" <= c.text <= "") and x0 - spacing <= c.x0 <= x1 and top - height * spacing <= c.yc < top
    ]
    words: list[tuple[Char, str]] = []
    for line in group_lines(chars):
        run: list[Char] = []
        for char in [*line.chars, None]:
            if char is not None and run and char.x0 - run[-1].x1 <= 0.6 * (char.bottom - char.top):
                run.append(char)
                continue
            if run:
                words.append((run[0], "".join(c.text for c in run)))
            run = [char] if char is not None else []
    return words


def repeat_counts(
    page: Page, top: float, x0: float, x1: float, spacing: float, ends: list[float]
) -> list[tuple[float, int]]:
    """Each repeat end with how many times it is played: "x3" printed near it, else twice."""
    counts = [
        (first.x0, count)
        for first, text in _texts_above(page, top, x0, x1, spacing, 6)
        if (count := repeat_count(text)) is not None
    ]
    result: list[tuple[float, int]] = []
    for end in ends:
        near = [count for x, count in counts if end - 8 * spacing <= x <= end + 2 * spacing]
        result.append((end, near[-1] if near else 2))
    return result


def voltas(
    page: Page, top: float, x0: float, x1: float, spacing: float, bars: list[float]
) -> list[tuple[float, float, tuple[int, ...]]]:
    """Volta brackets ("1.", "2." over a line) as (x0, x1, passes)."""
    lines = [s for s in page.segments if s.is_horizontal and top - 9 * spacing <= s.top < top]
    found: list[tuple[float, float, tuple[int, ...]]] = []
    for first, text in _texts_above(page, top, x0, x1, spacing, 8):
        match = _VOLTA.match(text.replace(" ", ""))
        if not match:
            continue
        passes = tuple(sorted({int(n) for n in re.findall(r"\d", match.group("n"))}))
        bracket = next(
            (
                s
                for s in lines
                if first.x0 - 1.5 * spacing <= s.x0 <= first.x0 + 0.5 * spacing
                and abs(s.top - first.top) <= 1.5 * spacing
                and s.x1 - s.x0 >= 2 * spacing
            ),
            None,
        )
        if bracket is not None:
            found.append((bracket.x0, bracket.x1, passes))
        else:  # no line found: the bar the number is printed in
            end = next((b for b in bars if b > first.x0 + spacing), x1)
            found.append((first.x0 - spacing, end, passes))
    return found
