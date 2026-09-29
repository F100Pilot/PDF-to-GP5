"""Extract engraved tablature (vector staff lines + fret numbers as text).

This is the layout produced by Guitar Pro, MuseScore, TuxGuitar and similar
editors when exporting to PDF. Rhythm stems are not interpreted; timing is
inferred later from horizontal spacing.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

from ..model import Link, TabEvent, TabSystem
from .annotations import dynamics, lyrics, section_labels
from .bar_signs import repeat_counts, repeat_signs, time_signatures, voltas
from .common import shared_bars, split_fret_number
from .pdf_reader import Char, Page, Segment, group_lines
from .rhythm_marks import glyph_ys, read_rhythm

MIN_STRINGS, MAX_STRINGS = 4, 8
_LEGATO_LETTERS = {"H": Link.HAMMER, "P": Link.PULL}
# SMuFL arrowheads drawn on strum/arpeggio arrows. An arrow pointing up (towards the
# high strings at the top of the tab) is played low-to-high: a downstroke.
_ARROWHEADS = {"\ueb78": "down", "\ueb7c": "up"}
# Text that opens a dashed range applying an effect to every note under it.
_RANGE_MARKS = {"letring": "let_ring", "P.M.": "palm_mute"}


@dataclass
class _StaffLine:
    y: float
    x0: float
    x1: float


def _staff_lines(segments: list[Segment], page_width: float) -> list[_StaffLine]:
    """Merge horizontal segments sharing the same y into full-width lines."""
    horizontals = sorted(
        (s for s in segments if s.is_horizontal and (s.x1 - s.x0) > 0.02 * page_width),
        key=lambda s: (round((s.top + s.bottom) / 2, 1), s.x0),
    )
    lines: list[_StaffLine] = []
    for seg in horizontals:
        y = (seg.top + seg.bottom) / 2
        if lines and abs(lines[-1].y - y) <= 0.5 and seg.x0 <= lines[-1].x1 + 0.1 * page_width:
            lines[-1].x0 = min(lines[-1].x0, seg.x0)
            lines[-1].x1 = max(lines[-1].x1, seg.x1)
        else:
            lines.append(_StaffLine(y, seg.x0, seg.x1))
    # Short staves exist (e.g. a final bar on its own line); equal spacing and extent
    # checks in _staves filter out unrelated lines.
    return [line for line in lines if (line.x1 - line.x0) > 0.08 * page_width]


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
            # A shorter line inside the staff (e.g. the thick bar of a multi-bar rest)
            # must not split the staff.
            inside = len(run) >= 2 and gap < (run[1].y - run[0].y)
            if inside and (line.x1 - line.x0) < 0.9 * (prev.x1 - prev.x0):
                continue
        runs.append([line])
    return [run for run in runs if MIN_STRINGS <= len(run) <= MAX_STRINGS]


def _is_parenthesized(x0: float, x1: float, top: float, bottom: float, curves: list[Segment], spacing: float) -> bool:
    """Parentheses drawn as thin curved paths hugging both sides of the number."""
    height = bottom - top

    def bracket(c: Segment) -> bool:
        return (
            (c.x1 - c.x0) <= 0.4 * spacing
            and 0.5 * height <= (c.bottom - c.top) <= 1.5 * height
            and c.top < bottom
            and c.bottom > top
        )

    left = any(bracket(c) and x0 - 0.35 * spacing <= c.x1 <= x0 + 0.1 * spacing for c in curves)
    right = any(bracket(c) and x1 - 0.1 * spacing <= c.x0 <= x1 + 0.35 * spacing for c in curves)
    return left and right


def _numbers_on_staff(
    chars: list[Char], staff: list[_StaffLine], spacing: float, curves: list[Segment]
) -> list[TabEvent]:
    x0, x1 = staff[0].x0, staff[0].x1
    # Fret digits are about one staff space tall; time signatures are about two.
    candidates = [
        c
        for c in chars
        if x0 <= c.xc <= x1 and (c.text.isdigit() or c.text in "xX()") and (c.bottom - c.top) <= 1.6 * spacing
    ]
    events: list[TabEvent] = []
    for string, line in enumerate(staff, start=1):
        on_line = sorted(
            (c for c in candidates if abs(c.yc - line.y) <= 0.4 * spacing),
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
            paren = (
                i > 0 and on_line[i - 1].text == "(" and j + 1 < len(on_line) and on_line[j + 1].text == ")"
            ) or _is_parenthesized(on_line[i].x0, on_line[j].x1, on_line[i].top, on_line[i].bottom, curves, spacing)
            frets = split_fret_number(text)
            if len(frets) == 1:
                center = (on_line[i].x0 + on_line[j].x1) / 2
                events.append(TabEvent(x=center, string=string, fret=frets[0], parenthesized=paren))
            else:
                events.extend(
                    TabEvent(x=on_line[i + k].xc, string=string, fret=f, parenthesized=paren)
                    for k, f in enumerate(frets)
                )
            i = j + 1
    return events


def _is_isolated_letter(char: Char, chars: list[Char]) -> bool:
    """True for a standalone "H"/"P" (not part of "Post-Chorus" or "P.M.")."""
    width = char.x1 - char.x0
    return not any(
        other is not char
        and abs(other.yc - char.yc) < 0.3 * (char.bottom - char.top)
        and (other.text.isalpha() or other.text == ".")
        and (0 <= other.x0 - char.x1 < 0.5 * width or 0 <= char.x0 - other.x1 < 0.5 * width)
        for other in chars
    )


def _apply_legato_marks(chars: list[Char], staff: list[_StaffLine], spacing: float, events: list[TabEvent]) -> None:
    """Attach "H"/"P" printed above the staff to the note pair they sit between."""
    top = staff[0].y
    by_string: dict[int, list[TabEvent]] = {}
    for event in sorted(events, key=lambda e: e.x):
        by_string.setdefault(event.string, []).append(event)
    for char in chars:
        if char.text not in _LEGATO_LETTERS or not (top - 3 * spacing <= char.yc < top):
            continue
        if not (staff[0].x0 <= char.xc <= staff[0].x1) or not _is_isolated_letter(char, chars):
            continue
        best: tuple[float, TabEvent] | None = None
        for string_events in by_string.values():
            for first, second in itertools.pairwise(string_events):
                if first.fret is None or second.fret is None or not (first.x < char.xc < second.x):
                    continue
                span = second.x - first.x
                if span > 6 * spacing:
                    continue
                cost = abs((first.x + second.x) / 2 - char.xc) + 0.5 * span
                if best is None or cost < best[0]:
                    best = (cost, second)
        if best is not None:
            best[1].link = _LEGATO_LETTERS[char.text]


def _apply_effect_ranges(page: Page, placed: list[tuple[TabSystem, list[_StaffLine], float]]) -> None:
    """Apply "let ring" / "P.M." dashed ranges to the notes of the staff above them."""
    for line in group_lines(page.chars):
        text = line.text
        height = line.bottom - line.top
        for mark, attribute in _RANGE_MARKS.items():
            start = text.find(mark)
            while start != -1:
                first_char = line.chars[start]
                end_x = line.chars[start + len(mark) - 1].x1
                owner = min(
                    (item for item in placed if 0 < line.yc - item[1][-1].y < 8 * item[2]),
                    key=lambda item: line.yc - item[1][-1].y,
                    default=None,
                )
                if owner is not None:
                    system, _, spacing = owner
                    dashes = sorted(
                        (
                            seg
                            for seg in page.segments
                            if abs((seg.top + seg.bottom) / 2 - line.yc) <= 0.6 * height and seg.x0 >= end_x - 1
                        ),
                        key=lambda seg: seg.x0,
                    )
                    for seg in dashes:
                        if seg.x0 - end_x > 1.5 * spacing:
                            break
                        end_x = max(end_x, seg.x1)
                    for event in system.events:
                        if first_char.x0 - spacing <= event.x <= end_x:
                            setattr(event, attribute, True)
                start = text.find(mark, start + len(mark))


def _strum_arrows(page: Page, staff: list[_StaffLine], spacing: float) -> list[tuple[float, str]]:
    """(x, stroke) for vertical arrows with an arrowhead glyph across the staff."""
    top, bottom = staff[0].y, staff[-1].y
    heads = [c for c in page.chars if c.text in _ARROWHEADS and staff[0].x0 <= c.xc <= staff[0].x1]
    arrows: list[tuple[float, str]] = []
    for seg in page.segments:
        if not seg.is_vertical or seg.bottom < top or seg.top > bottom or seg.bottom - seg.top < spacing:
            continue
        x = (seg.x0 + seg.x1) / 2
        head = next(
            (c for c in heads if abs(c.xc - x) <= 0.6 * spacing and top - 3 * spacing <= c.top <= bottom + 3 * spacing),
            None,
        )
        if head is not None:
            arrows.append((x, _ARROWHEADS[head.text]))
    return arrows


def _apply_strums(arrows: list[tuple[float, str]], events: list[TabEvent], spacing: float) -> None:
    """A strum arrow applies to the chord just right of it."""
    for x, stroke in arrows:
        following = [e for e in events if 0 < e.x - x <= 2.5 * spacing]
        if following:
            nearest = min(e.x for e in following)
            for event in following:
                if event.x - nearest <= 0.5 * spacing:
                    event.stroke = stroke


def _note_beside(
    events: list[TabEvent], staff: list[_StaffLine], spacing: float, x: float, y: float, *, left: bool
) -> TabEvent | None:
    """The fret number whose edge is next to point (x, y): left of it or right of it."""
    best: tuple[float, TabEvent] | None = None
    for event in events:
        if event.fret is None or abs(staff[event.string - 1].y - y) > 0.6 * spacing:
            continue
        half = len(str(event.fret)) * 0.33 * spacing  # fret digits are about 0.6-0.7 spaces wide
        gap = x - (event.x + half) if left else (event.x - half) - x
        if -0.3 * spacing <= gap <= 0.8 * spacing and (best is None or gap < best[0]):
            best = (gap, event)
    return best[1] if best else None


def _apply_slides(page: Page, staff: list[_StaffLine], spacing: float, events: list[TabEvent]) -> None:
    """Slides drawn as short oblique strokes beside fret numbers.

    Between two notes on one string: slide to the second note, legato when a slur
    arc spans both, otherwise a shift slide. Only after a note: slide out (down for
    a falling stroke). Only before a note: slide in (from below for a rising stroke).
    """
    top, bottom = staff[0].y, staff[-1].y
    for seg in page.segments:
        if seg.rising is None:
            continue
        width, height = seg.x1 - seg.x0, seg.bottom - seg.top
        if not (0.3 * spacing <= width <= 8 * spacing and 0.15 * spacing <= height <= 1.2 * spacing):
            continue
        if (
            seg.x0 < staff[0].x0
            or seg.x1 > staff[0].x1
            or seg.bottom < top - 0.5 * spacing
            or seg.top > bottom + spacing
        ):
            continue
        left_y, right_y = (seg.bottom, seg.top) if seg.rising else (seg.top, seg.bottom)
        before = _note_beside(events, staff, spacing, seg.x0, left_y, left=True)
        after = _note_beside(events, staff, spacing, seg.x1, right_y, left=False)
        if before is not None and after is not None:
            if before.string != after.string:
                continue
            string_y = staff[before.string - 1].y
            # The slur may arch over a chord at the target, so only its ends are checked.
            slurred = any(
                abs(c.x0 - before.x) <= 0.8 * spacing
                and abs(c.x1 - after.x) <= 0.8 * spacing
                and top - 3 * spacing <= c.top
                and c.bottom <= string_y
                for c in page.curves
            )
            after.link = Link.SLIDE_UP if slurred else Link.SHIFT_SLIDE
        elif width > 2.5 * spacing:
            continue  # a long stroke with a note on one side only is not a slide in/out
        elif before is not None:
            before.slide_out = "up" if seg.rising else "down"
        elif after is not None:
            after.slide_in = "below" if seg.rising else "above"


# Bend amount printed above the arrow, in semitones.
_BEND_AMOUNTS = {"¼": 1, "½": 1, "1/2": 1, "1": 2, "full": 2, "1½": 3, "11/2": 3, "2": 4}
_WIGGLES = {chr(c) for c in range(0xEAA0, 0xEAC0)}  # SMuFL wiggle lines (vibrato, trill)


def _bend_amount(page: Page, head: Segment, spacing: float) -> int:
    xc = (head.x0 + head.x1) / 2
    label = "".join(
        c.text
        for c in sorted(page.chars, key=lambda c: c.x0)
        if abs(c.xc - xc) <= 0.8 * spacing and head.top - 2 * spacing <= c.top and c.bottom <= head.top + 0.3 * spacing
    )
    return _BEND_AMOUNTS.get(label.strip().lower(), 2)


def _apply_bends(page: Page, staff: list[_StaffLine], spacing: float, events: list[TabEvent]) -> None:
    """Bend arrows drawn as a stroke ending in a filled arrowhead.

    Up arrow from a note: bend (curved) or pre-bend (straight, from the note's top);
    a curve may also come in from the left onto a tied note (a held bend).
    Down arrow: release of the bend that starts where the arrow starts.
    """
    top, bottom = staff[0].y, staff[-1].y
    heads = [
        c
        for c in page.curves
        if 0.3 * spacing <= c.x1 - c.x0 <= 0.8 * spacing
        and 0.3 * spacing <= c.bottom - c.top <= 0.8 * spacing
        and top - 4 * spacing <= c.top <= bottom
        and staff[0].x0 <= c.x0 <= staff[0].x1
    ]
    strokes = [
        s
        for s in (*page.curves, *page.segments)
        if max(s.x1 - s.x0, s.bottom - s.top) >= 0.8 * spacing and (s.bottom - s.top) >= 0.5 * spacing
    ]
    y_of = {n: line.y for n, line in enumerate(staff, start=1)}
    releases: list[Segment] = []
    for head in heads:  # bends first: a release refers to a bend that may be drawn later
        xc = (head.x0 + head.x1) / 2
        up = next(
            (
                s
                for s in strokes
                if abs(s.top - head.bottom) <= 0.2 * spacing and s.x0 - 0.2 * spacing <= xc <= s.x1 + 0.2 * spacing
            ),
            None,
        )
        if up is None:
            down = next(
                (
                    s
                    for s in strokes
                    if abs(s.bottom - head.top) <= 0.2 * spacing and s.x0 - 0.2 * spacing <= xc <= s.x1 + 0.2 * spacing
                ),
                None,
            )
            if down is not None:
                releases.append(down)
            continue
        straight = up.x1 - up.x0 < 0.2 * spacing
        origin_x = (up.x0 + up.x1) / 2 if straight else up.x0
        candidates = [
            e
            for e in events
            if e.fret is not None
            and y_of[e.string] - 1.2 * spacing <= up.bottom <= y_of[e.string] + 0.5 * spacing
            and (
                abs(origin_x - e.x) <= 0.5 * spacing if straight else -1.5 * spacing <= origin_x - e.x <= 1.8 * spacing
            )
        ]
        if candidates:
            note = min(candidates, key=lambda e: abs(origin_x - e.x))
            note.bend_semitones = _bend_amount(page, head, spacing)
            note.bend_pre = straight
    for down in releases:
        bent = [e for e in events if e.bend_semitones and abs(e.x - down.x0) <= 1.8 * spacing]
        if bent:
            min(bent, key=lambda e: abs(e.x - down.x0)).bend_release = True


def _apply_vibrato(
    page: Page, staves: list[list[_StaffLine]], staff: list[_StaffLine], spacing: float, events: list[TabEvent]
) -> list[tuple[float, float]]:
    """Wavy lines above the staff give vibrato to the notes they span; returns their x ranges."""
    ranges: list[tuple[float, float]] = []
    wiggles = sorted((c for c in page.chars if c.text in _WIGGLES), key=lambda c: (round(c.top), c.x0))
    groups: list[list[Char]] = []
    for char in wiggles:
        if groups and abs(groups[-1][-1].top - char.top) < 1 and char.x0 - groups[-1][-1].x1 < spacing:
            groups[-1].append(char)
        else:
            groups.append([char])
    top = staff[0].y
    for group in groups:
        y = glyph_ys(group[0])[1]  # music-font glyph drawn about one em above its box
        owner = min(staves, key=lambda st: abs(st[0].y - y) if st[0].y >= y - spacing else float("inf"))
        if owner is not staff or not (0 <= top - y <= 5 * spacing):
            continue
        for event in events:
            if group[0].x0 - 0.5 * spacing <= event.x <= group[-1].x1:
                event.vibrato = True
        ranges.append((group[0].x0 - 0.5 * spacing, group[-1].x1))
    return ranges


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


def _measure_numbers(chars: list[Char], staff: list[_StaffLine], spacing: float, bars: list[float]) -> list[int | None]:
    """Read the bar numbers printed just above the staff at the start of each bar."""
    top = staff[0].y
    digits = sorted(
        (c for c in chars if c.text.isdigit() and top - 1.5 * spacing <= c.yc < top - 0.2 * spacing),
        key=lambda c: c.x0,
    )
    numbers: list[tuple[float, int]] = []
    run: list[Char] = []
    for c in [*digits, None]:
        if c is not None and run and c.x0 - run[-1].x1 < 0.3 * (c.x1 - c.x0) and abs(c.yc - run[-1].yc) < 1:
            run.append(c)
            continue
        if run:
            numbers.append((run[0].x0, int("".join(ch.text for ch in run))))
        run = [c] if c is not None else []
    result: list[int | None] = []
    for bar in bars[:-1]:
        near = [n for x, n in numbers if abs(x - bar) <= 1.2 * spacing]
        result.append(near[0] if len(near) == 1 else None)
    return result


def _trim_margins(
    bars: list[float],
    signatures: list[tuple[float, int, int]],
    repeat_starts: list[float],
    events: list[TabEvent],
    spacing: float,
) -> tuple[list[float], list[tuple[float, int, int]]]:
    """Drop the staff margins that are not bars.

    * A repeat opening a line is drawn after the clef (and time signature): the narrow space
      before it holds no notes and is not a bar.
    * A time signature after the last bar line of a line only announces the next line's
      (courtesy signature): it is not a bar, and the next line prints the signature again.
    """

    def empty(start: float, end: float) -> bool:
        return end - start < 6 * spacing and not any(start <= e.x < end for e in events)

    if len(bars) >= 3 and bars[1] in repeat_starts and empty(bars[0], bars[1]):
        bars = bars[1:]
    if len(bars) >= 3 and empty(bars[-2], bars[-1]) and any(x >= bars[-2] for x, _, _ in signatures):
        signatures = [sign for sign in signatures if sign[0] < bars[-2]]
        bars = bars[:-1]
    return bars, signatures


def extract_engraved_systems(page: Page) -> list[TabSystem]:
    """Tab staves on the page; staves without fret numbers are kept as rest bars."""
    systems: list[TabSystem] = []
    placed: list[tuple[TabSystem, list[_StaffLine], float]] = []
    verticals = [s for s in page.segments if s.is_vertical]
    staves = _staves(_staff_lines(page.segments, page.width))
    for staff in staves:
        spacing = (staff[-1].y - staff[0].y) / (len(staff) - 1)
        events = _numbers_on_staff(page.chars, staff, spacing, page.curves)
        _apply_legato_marks(page.chars, staff, spacing, events)
        _apply_bends(page, staff, spacing, events)
        _apply_slides(page, staff, spacing, events)
        vibrato_ranges = _apply_vibrato(page, staves, staff, spacing, events)
        top, bottom = staff[0].y, staff[-1].y
        x0, x1 = staff[0].x0, staff[0].x1
        arrows = _strum_arrows(page, staff, spacing)
        _apply_strums(arrows, events, spacing)
        bar_xs = [
            (v.x0 + v.x1) / 2
            for v in verticals
            if v.top <= top + 0.3 * spacing
            and v.bottom >= bottom - 0.3 * spacing
            and x0 - 1 <= v.x0 <= x1 + 1
            and not any(abs((v.x0 + v.x1) / 2 - ax) < 1 for ax, _ in arrows)
        ]
        digit_width = spacing * 0.6  # fret digits are roughly 0.6 staff spaces wide
        drawn = shared_bars([bar_xs], 0.5 * digit_width)
        bars = list(drawn)
        if not bars or bars[0] - x0 > digit_width:
            bars.insert(0, x0)
        if x1 - bars[-1] > digit_width:
            bars.append(x1)
        signatures = time_signatures(page.chars, top, bottom, x0, x1, spacing)
        starts, ends = repeat_signs(page.chars, top, bottom, spacing, drawn)
        bars, signatures = _trim_margins(bars, signatures, starts, events, spacing)
        system = TabSystem(
            page=page.number,
            string_count=len(staff),
            events=events,
            bars=bars,
            start_x=x0,
            end_x=x1,
            char_width=digit_width,
            labels=_labels(page.chars, staff, spacing),
            source="engraved",
            bar_numbers=_measure_numbers(page.chars, staff, spacing, bars),
            sections=section_labels(page, top, x0, x1, spacing),
            lyrics=lyrics(page, bottom, x0, x1, spacing),
            dynamics=dynamics(page, top, bottom, x0, x1, spacing),
            time_signatures=signatures,
            repeat_starts=starts,
            repeat_ends=repeat_counts(page, top, x0, x1, spacing, ends),
            endings=voltas(page, top, x0, x1, spacing, bars),
            rhythm=[
                replace(m, vibrato=True) if not m.is_rest and any(a <= m.x <= b for a, b in vibrato_ranges) else m
                for m in read_rhythm(page, top, bottom, x0, x1, spacing)
            ],
        )
        systems.append(system)
        placed.append((system, staff, spacing))
    _apply_effect_ranges(page, placed)
    return systems
