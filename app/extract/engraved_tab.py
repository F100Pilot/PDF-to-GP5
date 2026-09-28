"""Extract engraved tablature (vector staff lines + fret numbers as text).

This is the layout produced by Guitar Pro, MuseScore, TuxGuitar and similar
editors when exporting to PDF. Rhythm stems are not interpreted; timing is
inferred later from horizontal spacing.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from ..model import TabEvent, TabSystem
from .common import shared_bars, split_fret_number
from .pdf_reader import Char, Page, Segment

MIN_STRINGS, MAX_STRINGS = 4, 8


@dataclass
class _StaffLine:
    y: float
    x0: float
    x1: float


def _staff_lines(segments: list[Segment], page_width: float) -> list[_StaffLine]:
    """Merge horizontal segments sharing the same y into full-width lines."""
    horizontals = sorted(
        (s for s in segments if s.is_horizontal and (s.x1 - s.x0) > 0.02 * page_width),
        key=lambda s: (s.top + s.bottom) / 2,
    )
    lines: list[_StaffLine] = []
    for seg in horizontals:
        y = (seg.top + seg.bottom) / 2
        if lines and abs(lines[-1].y - y) <= 0.5 and seg.x0 <= lines[-1].x1 + 0.1 * page_width:
            lines[-1].x0 = min(lines[-1].x0, seg.x0)
            lines[-1].x1 = max(lines[-1].x1, seg.x1)
        else:
            lines.append(_StaffLine(y, seg.x0, seg.x1))
    return [line for line in lines if (line.x1 - line.x0) > 0.3 * page_width]


def _staves(lines: list[_StaffLine]) -> list[list[_StaffLine]]:
    """Split staff lines into runs of equally spaced, equally long lines."""
    runs: list[list[_StaffLine]] = []
    for line in lines:
        if runs:
            run = runs[-1]
            prev = run[-1]
            gap = line.y - prev.y
            same_extent = abs(line.x0 - prev.x0) < 5 and abs(line.x1 - prev.x1) < 5
            spacing_ok = gap > 2 and (len(run) < 2 or abs(gap - (run[1].y - run[0].y)) <= 0.15 * gap)
            if same_extent and spacing_ok:
                run.append(line)
                continue
        runs.append([line])
    return [run for run in runs if MIN_STRINGS <= len(run) <= MAX_STRINGS]


def _numbers_on_staff(chars: list[Char], staff: list[_StaffLine], spacing: float) -> list[TabEvent]:
    x0, x1 = staff[0].x0, staff[0].x1
    candidates = [c for c in chars if x0 <= c.xc <= x1 and (c.text.isdigit() or c.text in "xX()")]
    digit_heights = [c.bottom - c.top for c in candidates if c.text.isdigit()]
    if not digit_heights:
        return []
    typical_height = median(digit_heights)
    events: list[TabEvent] = []
    for string, line in enumerate(staff, start=1):
        on_line = sorted(
            (
                c
                for c in candidates
                if abs(c.yc - line.y) <= 0.4 * spacing and (c.bottom - c.top) <= 1.4 * typical_height
            ),
            key=lambda c: c.x0,
        )
        i = 0
        while i < len(on_line):
            c = on_line[i]
            if c.text in "xX":
                events.append(TabEvent(x=c.xc, string=string, fret=None, dead=True))
                i += 1
                continue
            if not c.text.isdigit():
                i += 1
                continue
            j = i
            width = c.x1 - c.x0
            while (
                j + 1 < len(on_line)
                and on_line[j + 1].text.isdigit()
                and on_line[j + 1].x0 - on_line[j].x1 < 0.3 * width
            ):
                j += 1
            text = "".join(ch.text for ch in on_line[i : j + 1])
            ghost = i > 0 and on_line[i - 1].text == "(" and j + 1 < len(on_line) and on_line[j + 1].text == ")"
            frets = split_fret_number(text)
            if len(frets) == 1:
                center = (on_line[i].x0 + on_line[j].x1) / 2
                events.append(TabEvent(x=center, string=string, fret=frets[0], ghost=ghost))
            else:
                events.extend(
                    TabEvent(x=on_line[i + k].xc, string=string, fret=f, ghost=ghost) for k, f in enumerate(frets)
                )
            i = j + 1
    return events


def _labels(chars: list[Char], staff: list[_StaffLine], spacing: float) -> list[str]:
    """Read tuning letters printed left of the staff, if present for every string."""
    labels: list[str] = []
    for line in staff:
        near = sorted(
            (
                c
                for c in chars
                if c.x1 <= line.x0 + 1 and line.x0 - c.x0 < 6 * spacing and abs(c.yc - line.y) <= 0.4 * spacing
            ),
            key=lambda c: c.x0,
        )
        text = "".join(c.text for c in near)
        if not text or text[0].upper() not in "ABCDEFG":
            return []
        labels.append(text)
    return labels


def extract_engraved_systems(page: Page) -> list[TabSystem]:
    systems: list[TabSystem] = []
    verticals = [s for s in page.segments if s.is_vertical]
    for staff in _staves(_staff_lines(page.segments, page.width)):
        spacing = (staff[-1].y - staff[0].y) / (len(staff) - 1)
        events = _numbers_on_staff(page.chars, staff, spacing)
        if not events:
            continue  # e.g. a standard-notation staff
        top, bottom = staff[0].y, staff[-1].y
        x0, x1 = staff[0].x0, staff[0].x1
        bar_xs = [
            (v.x0 + v.x1) / 2
            for v in verticals
            if v.top <= top + 0.3 * spacing and v.bottom >= bottom - 0.3 * spacing and x0 - 1 <= v.x0 <= x1 + 1
        ]
        digit_width = spacing * 0.6  # fret digits are roughly 0.6 staff spaces wide
        bars = shared_bars([bar_xs], 0.5 * digit_width)
        if not bars or bars[0] - x0 > digit_width:
            bars.insert(0, x0)
        if x1 - bars[-1] > digit_width:
            bars.append(x1)
        systems.append(
            TabSystem(
                page=page.number,
                string_count=len(staff),
                events=events,
                bars=bars,
                start_x=x0,
                end_x=x1,
                char_width=digit_width,
                labels=_labels(page.chars, staff, spacing),
                source="engraved",
            )
        )
    return systems
