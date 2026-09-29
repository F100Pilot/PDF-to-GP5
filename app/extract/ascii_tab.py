"""Extract text-based ("ASCII") tablature such as ``e|--0--3h5--|``."""

from __future__ import annotations

import re
from statistics import median

from ..model import Link, TabEvent, TabSystem
from .common import repeat_count, shared_bars, split_fret_number
from .metadata import line_text
from .pdf_reader import Char, Page, TextLine, group_lines

_BODY_CHARS = set("-0123456789|hpbrs/\\~xX()<>.:*^=+tTo")
# Repeat dots written against a bar line: "|:--" / "|*--" / "|o--" open a repeat, "--:|" closes it.
_REPEAT_DOTS = set(":*o")
_LABEL_RE = re.compile(r"^[A-Ga-g][#b]?$")
_PROSE_RE = re.compile(r"[A-Za-z]{3,}")
_SECTION_RE = re.compile(
    r"^\s*\[?\s*(?P<name>(?:intro|verse|pre-?chorus|chorus|post-?chorus|bridge|solo|outro|interlude|riff|"
    r"breakdown|instrumental|refr[aã]o|estrofe|ponte)\b[^\]:]*?)\s*\]?\s*:?\s*$",
    re.IGNORECASE,
)
# Share of unrecognised symbols (e.g. "v", "[12]") tolerated in a tab line; they are skipped.
MAX_UNKNOWN_RATIO = 0.15
_LINKS = {"h": Link.HAMMER, "p": Link.PULL, "/": Link.SLIDE_UP, "\\": Link.SLIDE_DOWN, "s": Link.SLIDE_UP}
# "/" and "\" touching only one note: (slide out after it, slide in before it).
_SLIDE_ENDS = {"/": ("up", "below"), "\\": ("down", "above")}
# "PM----|", "P.M. - - -", "let ring---" on a line of their own above the tab.
_RANGE_RE = re.compile(r"P\.?M\.?|let\s*ring|l\.r\.?", re.IGNORECASE)
_RANGE_FILL = set("-._|")
MIN_STRINGS, MAX_STRINGS = 4, 8


def _is_dashy(text: str) -> bool:
    dashes = text.count("-")
    return dashes >= 6 and dashes / len(text) >= 0.35


def _split_tab_line(line: TextLine) -> tuple[str, list[Char]] | None:
    """Return (label, body chars) when the line looks like one tab string."""
    chars = line.chars
    first = next((i for i, c in enumerate(chars) if c.text in "|-"), None)
    if first is None:
        return None
    label = "".join(c.text for c in chars[:first])
    if label and not _LABEL_RE.match(label):
        return None
    body = chars[first:]
    # Drop trailing annotations such as "x4" separated by a wide gap.
    unit = median(c.x1 - c.x0 for c in body)
    for i in range(1, len(body)):
        if body[i].x0 - body[i - 1].x1 > 2 * unit:
            body = body[:i]
            break
    text = "".join(c.text for c in body)
    if not _is_dashy(text) or _PROSE_RE.search(text):
        return None
    if sum(ch not in _BODY_CHARS for ch in text) / len(text) > MAX_UNKNOWN_RATIO:
        return None
    return label, body


def _read_number(chars: list[Char], i: int, unit: float) -> tuple[str, int]:
    """Read adjacent digits starting at ``i``; return (text, next index)."""
    j = i
    while j + 1 < len(chars) and chars[j + 1].text.isdigit() and chars[j + 1].x0 - chars[j].x1 < 0.3 * unit:
        j += 1
    return "".join(c.text for c in chars[i : j + 1]), j + 1


def _ends_note(chars: list[Char], i: int) -> bool:
    return i >= 0 and (chars[i].text.isdigit() or chars[i].text in ")>")


def _starts_note(chars: list[Char], i: int) -> bool:
    return i < len(chars) and (chars[i].text.isdigit() or chars[i].text in "(<")


def _parse_string(
    chars: list[Char], string: int, unit: float
) -> tuple[list[TabEvent], list[float], list[float], list[float]]:
    """Events, bar lines, and bar lines opening / closing a repeat on one tab string."""
    events: list[TabEvent] = []
    bars: list[float] = []
    repeat_starts: list[float] = []
    repeat_ends: list[float] = []
    pending: Link | None = None
    slide_in: str | None = None
    tapped = False
    i = 0
    while i < len(chars):
        char = chars[i]
        t = char.text
        after_note = bool(events) and events[-1].fret is not None and _ends_note(chars, i - 1)
        if t.isdigit():
            text, nxt = _read_number(chars, i, unit)
            paren = i > 0 and chars[i - 1].text == "(" and nxt < len(chars) and chars[nxt].text == ")"
            harmonic = i > 0 and chars[i - 1].text == "<" and nxt < len(chars) and chars[nxt].text == ">"
            frets = split_fret_number(text)
            for k, fret in enumerate(frets):
                x = chars[i + k].x0 if len(frets) > 1 else char.x0
                events.append(
                    TabEvent(
                        x=x,
                        string=string,
                        fret=fret,
                        parenthesized=paren,
                        link=pending,
                        slide_in=slide_in,
                        harmonic="natural" if harmonic else None,
                        tapped=tapped,
                    )
                )
                pending, slide_in, tapped = None, None, False
            i = nxt
            continue
        if t in "xX":
            events.append(TabEvent(x=char.x0, string=string, fret=None, dead=True, link=pending))
            pending, slide_in, tapped = None, None, False
        elif t == "p" and after_note and i + 1 < len(chars) and chars[i + 1].text == "b":
            i = _parse_bend(chars, i + 2, events[-1], unit)  # "7pb9": pre-bend
            events[-1].bend_pre = True
            continue
        elif t in _SLIDE_ENDS and after_note and not _starts_note(chars, i + 1):
            events[-1].slide_out = _SLIDE_ENDS[t][0]  # "5\-"
        elif t in _SLIDE_ENDS and not _ends_note(chars, i - 1) and _starts_note(chars, i + 1):
            slide_in = _SLIDE_ENDS[t][1]  # "-/5"
        elif t in _LINKS:
            pending = _LINKS[t]
        elif t in "tT" and i + 1 < len(chars) and chars[i + 1].text.isdigit():
            tapped = True
        elif t == "b" and events and events[-1].fret is not None and i > 0 and chars[i - 1].text in "0123456789)":
            i = _parse_bend(chars, i + 1, events[-1], unit)
            continue
        elif t == "~" and events:
            events[-1].vibrato = True
        elif t == "|":
            bars.append(char.x0)
            if i + 1 < len(chars) and chars[i + 1].text in _REPEAT_DOTS:
                repeat_starts.append(char.x0)
            if i > 0 and chars[i - 1].text in _REPEAT_DOTS:
                repeat_ends.append(char.x0)
            pending, slide_in, tapped = None, None, False
        i += 1
    return events, bars, repeat_starts, repeat_ends


def _parse_bend(chars: list[Char], i: int, event: TabEvent, unit: float) -> int:
    """Parse the optional target fret and release after ``b``; return next index."""
    semitones = 2
    if i < len(chars) and chars[i].text == "(":
        i += 1
    if i < len(chars) and chars[i].text.isdigit():
        text, i = _read_number(chars, i, unit)
        delta = int(text) - (event.fret or 0)
        if 1 <= delta <= 4:
            semitones = delta
    if i < len(chars) and chars[i].text == ")":
        i += 1
    if i < len(chars) and chars[i].text == "r":
        event.bend_release = True
        i += 1
        if i < len(chars) and chars[i].text.isdigit():
            _, i = _read_number(chars, i, unit)
    event.bend_semitones = semitones
    return i


def _snap(xs: list[float], bars: list[float], tolerance: float) -> list[float]:
    """The bar lines (from ``bars``) near the positions ``xs``."""
    return sorted({b for x in xs for b in bars if abs(b - x) <= tolerance})


def _build_system(page: int, group: list[tuple[str, list[Char]]], times: int | None = None) -> TabSystem:
    """One tab system; ``times``: repeat count written after the lines ("x4"), if any."""
    all_chars = [c for _, body in group for c in body]
    dash_widths = [c.x1 - c.x0 for c in all_chars if c.text == "-"]
    unit = median(dash_widths or [c.x1 - c.x0 for c in all_chars])
    events: list[TabEvent] = []
    bar_lists: list[list[float]] = []
    start_marks: list[float] = []
    end_marks: list[float] = []
    for string, (_, body) in enumerate(group, start=1):
        string_events, string_bars, starts, ends = _parse_string(body, string, unit)
        events.extend(string_events)
        bar_lists.append(string_bars)
        start_marks.extend(starts)
        end_marks.extend(ends)
    labels = [label for label, _ in group]
    bars = shared_bars(bar_lists, 0.6 * unit)
    # Repeat dots are often written on a few strings only: one is enough.
    repeat_starts = _snap(start_marks, bars, 0.6 * unit)
    ends = _snap(end_marks, bars, 0.6 * unit)
    if times and not ends and len(bars) >= 2:
        # "x4" after a line without repeat signs: the whole line is played that many times.
        repeat_starts, ends = [bars[0]], [bars[-1]]
    repeat_ends = [(x, times if times and x == ends[-1] else 2) for x in ends]
    return TabSystem(
        page=page,
        string_count=len(group),
        events=events,
        bars=bars,
        start_x=min(c.x0 for c in all_chars),
        end_x=max(c.x1 for c in all_chars),
        char_width=unit,
        labels=labels if all(labels) else [],
        source="ascii",
        repeat_starts=repeat_starts,
        repeat_ends=repeat_ends,
    )


def _split_stacked(group: list[tuple[str, list[Char]]]) -> list[list[tuple[str, list[Char]]]]:
    """Split systems printed without a blank line between them, using repeating labels."""
    labels = [label for label, _ in group]
    if all(labels):
        for size in range(MAX_STRINGS, MIN_STRINGS - 1, -1):
            if len(group) % size == 0 and all(
                labels[i : i + size] == labels[:size] for i in range(0, len(group), size)
            ):
                return [group[i : i + size] for i in range(0, len(group), size)]
    return []


def _section_above(lines: list[TextLine], index: int) -> str | None:
    """A section label ("[Chorus]", "Verse 2:") on one of the two lines just above a tab block."""
    for back in (1, 2):
        if index - back < 0:
            break
        line = lines[index - back]
        if lines[index].yc - line.yc > 4 * (line.bottom - line.top):
            break
        match = _SECTION_RE.match(line_text(line))
        if match:
            return match.group("name").strip().title()
    return None


def _effect_ranges(line: TextLine) -> list[tuple[str, float, float]]:
    """(attribute, x0, x1) for a line holding only "PM---" / "let ring---" marks."""
    text, chars = line.text, line.chars
    matches = list(_RANGE_RE.finditer(text))
    covered = {i for m in matches for i in range(m.start(), m.end())}
    if not matches or any(i not in covered and ch not in _RANGE_FILL for i, ch in enumerate(text)):
        return []
    unit = median(c.x1 - c.x0 for c in chars)
    ranges: list[tuple[str, float, float]] = []
    for match in matches:
        end = match.end() - 1
        # Dashes (possibly spaced "- - -") continue the range up to an optional "|".
        while end + 1 < len(chars) and end + 1 not in covered and chars[end + 1].x0 - chars[end].x1 <= 1.5 * unit:
            end += 1
            if text[end] == "|":
                break
        attribute = "palm_mute" if match.group().lower().startswith("p") else "let_ring"
        ranges.append((attribute, chars[match.start()].x0, chars[end].x1))
    return ranges


def _ranges_above(lines: list[TextLine], index: int) -> list[tuple[str, float, float]]:
    """Palm mute / let ring lines just above a tab block (a section label may sit among them)."""
    ranges: list[tuple[str, float, float]] = []
    for back in (1, 2, 3):
        if index - back < 0:
            break
        line, below = lines[index - back], lines[index - back + 1]
        if below.yc - line.yc > 4 * (line.bottom - line.top):
            break
        found = _effect_ranges(line)
        if found:
            ranges.extend(found)
        elif not _SECTION_RE.match(line_text(line)):
            break
    return ranges


def _trailing_count(line: TextLine, body: list[Char]) -> int | None:
    """Repeat count written after a tab line ("--3--|   x4")."""
    return repeat_count("".join(c.text for c in line.chars if c.x0 > body[-1].x1))


def extract_ascii_systems(page: Page) -> tuple[list[TabSystem], list[str]]:
    """Find groups of consecutive tab lines on a page."""
    systems: list[TabSystem] = []
    warnings: list[str] = []
    group: list[tuple[str, list[Char]]] = []
    group_ys: list[float] = []
    group_section: str | None = None
    group_ranges: list[tuple[str, float, float]] = []
    group_times: list[int] = []  # repeat counts written after the tab lines ("x4")
    ignored = 0

    def flush() -> None:
        nonlocal ignored
        first = len(systems)
        if MIN_STRINGS <= len(group) <= MAX_STRINGS:
            systems.append(_build_system(page.number, group, max(group_times, default=None)))
        elif len(group) > MAX_STRINGS:
            chunks = _split_stacked(group)
            systems.extend(_build_system(page.number, chunk) for chunk in chunks)
            if not chunks:
                warnings.append(
                    f"Página {page.number}: bloco com {len(group)} linhas de tab ignorado (máx. {MAX_STRINGS})."
                )
        elif len(group) >= 2:
            ignored += len(group)
        if group_section and len(systems) > first:
            systems[first].sections = [(systems[first].start_x, group_section)]
        if group_ranges and len(systems) > first:
            system = systems[first]
            for attribute, start, end in group_ranges:
                for event in system.events:
                    if start - 0.5 * system.char_width <= event.x <= end:
                        setattr(event, attribute, True)

    lines = group_lines(page.chars)
    for index, line in enumerate(lines):
        parsed = _split_tab_line(line)
        adjacent = False
        if parsed and group:
            gap = line.yc - group_ys[-1]
            if len(group_ys) >= 2:
                expected = group_ys[1] - group_ys[0]
                adjacent = abs(gap - expected) <= 0.3 * expected
            else:
                previous = lines[index - 1]
                adjacent = previous.yc == group_ys[-1] and gap <= 2.6 * (previous.bottom - previous.top)
        times = _trailing_count(line, parsed[1]) if parsed else None
        if parsed and adjacent:
            group.append(parsed)
            group_ys.append(line.yc)
        else:
            flush()
            group = [parsed] if parsed else []
            group_ys = [line.yc] if parsed else []
            group_times = []
            group_section = _section_above(lines, index) if parsed else None
            group_ranges = _ranges_above(lines, index) if parsed else []
            if not parsed and _is_dashy(line.text) and len(line.text) >= 12 and not _effect_ranges(line):
                ignored += 1
        if times:
            group_times.append(times)
    flush()
    if ignored:
        warnings.append(
            f"Página {page.number}: {ignored} linha(s) com aspeto de tablatura ignoradas "
            "(símbolos não reconhecidos ou linhas de tab incompletas)."
        )
    return systems, warnings
