"""Extract engraved tablature (vector staff lines + fret numbers as text).

This is the layout produced by Guitar Pro, MuseScore, TuxGuitar and similar
editors when exporting to PDF. Rhythm stems are not interpreted; timing is
inferred later from horizontal spacing.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

from ..model import Link, TabEvent, TabSystem
from .annotations import dynamics, hairpins, lyrics, section_labels
from .bar_signs import navigation_marks, repeat_counts, repeat_signs, tempo_marks, time_signatures, voltas
from .common import shared_bars, split_fret_number
from .pdf_reader import Char, Page, Segment, group_lines
from .rhythm_marks import glyph_ys, read_rhythm

MIN_STRINGS, MAX_STRINGS = 4, 8
_LEGATO_LETTERS = {"H": Link.HAMMER, "P": Link.PULL}
STACCATO = "\ue4a2"  # SMuFL articStaccatoAbove
# SMuFL arrowheads drawn on strum/arpeggio arrows. An arrow pointing up (towards the
# high strings at the top of the tab) is played low-to-high: a downstroke.
_ARROWHEADS = {"\ueb78": "down", "\ueb7c": "up"}
# Text that opens a dashed range applying an effect to every note under it.
# Marks followed by a dashed line to the end of their range: (attribute, value, printed above the staff).
_RANGE_MARKS = {
    "letring": ("let_ring", True, False),
    "P.M.": ("palm_mute", True, False),
    "PH": ("harmonic", "pinch", True),
    "AH": ("harmonic", "artificial", True),
    "N.H.": ("harmonic", "natural", True),
}


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
    heights = sorted(c.bottom - c.top for c in candidates if c.text.isdigit())
    typical = heights[3 * len(heights) // 4] if heights else 0.0  # most digits are normal notes, not grace notes
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
            small = on_line[i].bottom - on_line[i].top < 0.8 * typical  # grace notes are printed small
            if len(frets) == 1:
                center = (on_line[i].x0 + on_line[j].x1) / 2
                events.append(TabEvent(x=center, string=string, fret=frets[0], parenthesized=paren, grace=small))
            else:
                events.extend(
                    TabEvent(x=on_line[i + k].xc, string=string, fret=f, parenthesized=paren, grace=small)
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


def _ties_into_empty_bars(
    curves: list[Segment], staff: list[_StaffLine], spacing: float, events: list[TabEvent], bars: list[float]
) -> list[float]:
    """Bar lines that a tie crosses from a note into an empty bar (the tied note is not printed
    and a whole note has no stem): a flat arc just above a string holding a note before the bar
    line, ending past it, with no fret in the bar that follows."""
    tied: list[float] = []
    for bar, following in itertools.pairwise(bars):
        if any(bar <= e.x < following for e in events):
            continue
        for n, line in enumerate(staff, start=1):
            before = [e for e in events if e.string == n and e.fret is not None and e.x < bar]
            if not before:
                continue
            last = max(e.x for e in before)
            if any(
                c.bottom - c.top < 0.8 * spacing
                and line.y - 1.2 * spacing <= (c.top + c.bottom) / 2 <= line.y
                and last < c.x0 < bar < c.x1 - 0.3 * spacing
                for c in curves
            ):
                tied.append(bar)
                break
    return tied


def _attach_grace_notes(events: list[TabEvent], spacing: float) -> tuple[list[TabEvent], list[float]]:
    """Grace notes (small digits) become part of the note they lead into: the note of the next
    column on the same string, hammered on when an "H"/"P" joins them. Returns the other
    events and the x of the grace columns (their slashed stems are not beats). A grace note with
    no note on its string in the next column is dropped."""
    graces = [e for e in events if e.grace]
    if not graces:
        return events, []
    normal = [e for e in events if not e.grace]
    for grace in graces:
        following = [e.x for e in normal if e.x > grace.x]
        if grace.fret is None or not following:
            continue
        column = min(following)
        main = next(
            (e for e in normal if e.string == grace.string and abs(e.x - column) <= 0.5 * spacing and not e.dead),
            None,
        )
        if main is None or main.grace_fret is not None:
            continue
        main.grace_fret = grace.fret
        if main.link in (Link.HAMMER, Link.PULL):  # the legato comes from the grace note
            main.grace_hammer = True
            main.link = None
    columns = sorted({g.x for g in graces if not any(abs(e.x - g.x) <= 0.5 * spacing for e in normal)})
    return normal, columns


def _apply_staccato(chars: list[Char], staff: list[_StaffLine], spacing: float, events: list[TabEvent]) -> None:
    """Staccato dots above the staff mark the notes of the column below them."""
    top = staff[0].y
    for char in chars:
        if char.text != STACCATO or not any(top - 3 * spacing <= y <= top + 0.3 * spacing for y in glyph_ys(char)):
            continue
        near = [e for e in events if abs(e.x - char.xc) <= 0.6 * spacing]
        if near:
            column = min(near, key=lambda e: abs(e.x - char.xc)).x
            for event in near:
                if abs(event.x - column) <= 0.3 * spacing:
                    event.staccato = True


def _apply_effect_ranges(page: Page, placed: list[tuple[TabSystem, list[_StaffLine], float]]) -> None:
    """Apply dashed ranges to the notes of their staff: "let ring" / "P.M." under it, pinch /
    artificial / natural harmonics ("PH", "AH", "N.H.") over it."""
    for line in group_lines(page.chars):
        text = line.text
        height = line.bottom - line.top
        for mark, (attribute, value, above) in _RANGE_MARKS.items():
            start = text.find(mark)
            while start != -1:
                first_char = line.chars[start]
                last_char = line.chars[start + len(mark) - 1]
                end_x = last_char.x1
                # A mark above the staff is a word of its own: no letter touching it ("PHASE").
                neighbours = [line.chars[i] for i in (start - 1, start + len(mark)) if 0 <= i < len(line.chars)]
                part_of_word = any(
                    c.text.isalpha()
                    and (0 <= first_char.x0 - c.x1 < 0.5 * height or 0 <= c.x0 - last_char.x1 < 0.5 * height)
                    for c in neighbours
                )
                distances = [
                    (item[1][0].y - line.yc if above else line.yc - item[1][-1].y, index)
                    for index, item in enumerate(placed)
                ]
                nearest = min(((d, i) for d, i in distances if 0 < d < 8 * placed[i][2]), default=None)
                owner = placed[nearest[1]] if nearest is not None else None
                if owner is not None and not (above and part_of_word):
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
                        if first_char.x0 - spacing <= event.x <= end_x and not (above and event.dead):
                            setattr(event, attribute, value)
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


def _apply_bends(
    page: Page, staff: list[_StaffLine], spacing: float, events: list[TabEvent], stems: list[float] = ()
) -> None:
    """Bend arrows drawn as a stroke ending in a filled arrowhead.

    Up arrow from a note: bend (curved) or pre-bend (straight, from the note's top);
    a curve may also come in from the left onto a tied note (a held bend). A curve starting on
    a stem without a fret (the note tied over from before) bends that tied note: it becomes a
    parenthesised repeat of the fret, i.e. a tie that carries the bend.
    Down arrow: release of the bend that starts where the arrow starts, else of the last bend
    before it on a string with no other note in between.
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
        elif not straight:
            tied = _tied_bend(events, stems, y_of, up, origin_x, spacing)
            if tied is not None:
                tied.bend_semitones = _bend_amount(page, head, spacing)
                events.append(tied)
    for down in releases:
        bent = [e for e in events if e.bend_semitones and abs(e.x - down.x0) <= 1.8 * spacing]
        if not bent:
            # A release after a held bend: the last bend before it, with nothing struck in between.
            bent = [
                e
                for e in events
                if e.bend_semitones
                and e.x <= down.x0 + 0.5 * spacing
                and not any(o.string == e.string and e.x < o.x <= down.x0 for o in events)
            ]
            bent = [max(bent, key=lambda e: e.x)] if bent else []
        if bent:
            min(bent, key=lambda e: abs(e.x - down.x0)).bend_release = True


def _tied_bend(
    events: list[TabEvent], stems: list[float], y_of: dict[int, float], up: Segment, origin_x: float, spacing: float
) -> TabEvent | None:
    """The tied note a bend curve starts on: a stem with no fret just left of the curve, on the
    string the curve rises from, holding the fret struck before it on that string."""
    free = [
        x
        for x in stems
        if -0.5 * spacing <= origin_x - x <= 1.8 * spacing and not any(abs(e.x - x) <= 0.6 * spacing for e in events)
    ]
    strings = [n for n, y in y_of.items() if y - 1.2 * spacing <= up.bottom <= y + 0.5 * spacing]
    if not free or not strings:
        return None
    stem = max(free)
    string = min(strings, key=lambda n: abs(y_of[n] - up.bottom))
    struck = [e for e in events if e.string == string and e.fret is not None and e.x < stem]
    if not struck:
        return None
    return TabEvent(x=stem, string=string, fret=max(struck, key=lambda e: e.x).fret, parenthesized=True)


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


def _next_top(staves: list[list[_StaffLine]], bottom: float, default: float) -> float:
    """Top of the first staff below ``bottom`` (the page height when none)."""
    return min((staff[0].y for staff in staves if staff[0].y > bottom), default=default)


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
        top, bottom = staff[0].y, staff[-1].y
        x0, x1 = staff[0].x0, staff[0].x1
        rhythm = read_rhythm(page, top, bottom, x0, x1, spacing)
        _apply_bends(page, staff, spacing, events, [m.x for m in rhythm if not m.is_rest])
        _apply_slides(page, staff, spacing, events)
        vibrato_ranges = _apply_vibrato(page, staves, staff, spacing, events)
        _apply_staccato(page.chars, staff, spacing, events)
        events, grace_columns = _attach_grace_notes(events, spacing)
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
        tied_bars = _ties_into_empty_bars(page.curves, staff, spacing, events, bars)
        signs, jumps = navigation_marks(page, top, x0, x1, spacing)
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
            tied_bars=tied_bars,
            hairpins=hairpins(page, bottom, _next_top(staves, bottom, page.height), x0, x1, spacing),
            time_signatures=signatures,
            repeat_starts=starts,
            repeat_ends=repeat_counts(page, top, x0, x1, spacing, ends),
            endings=voltas(page, top, x0, x1, spacing, bars),
            tempos=tempo_marks(page, top, x0, x1, spacing),
            signs=signs,
            jumps=jumps,
            rhythm=[
                replace(m, vibrato=True) if not m.is_rest and any(a <= m.x <= b for a, b in vibrato_ranges) else m
                for m in rhythm
                if not any(abs(m.x - g) <= 0.6 * spacing for g in grace_columns)
            ],
        )
        systems.append(system)
        placed.append((system, staff, spacing))
    _apply_effect_ranges(page, placed)
    return systems
