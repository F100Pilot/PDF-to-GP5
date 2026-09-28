"""Extract text-based ("ASCII") tablature such as ``e|--0--3h5--|``."""

from __future__ import annotations

import re
from statistics import median

from ..model import Link, TabEvent, TabSystem
from .common import shared_bars, split_fret_number
from .pdf_reader import Char, Page, TextLine, group_lines

_BODY_CHARS = set("-0123456789|hpbrs/\\~xX()<>.:*^=+")
_LABEL_RE = re.compile(r"^[A-Ga-g][#b]?$")
_PROSE_RE = re.compile(r"[A-Za-z]{3,}")
# Share of unrecognised symbols (e.g. "v", "T", "[12]") tolerated in a tab line; they are skipped.
MAX_UNKNOWN_RATIO = 0.15
_LINKS = {"h": Link.HAMMER, "p": Link.PULL, "/": Link.SLIDE_UP, "\\": Link.SLIDE_DOWN, "s": Link.SLIDE_UP}
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


def _parse_string(chars: list[Char], string: int, unit: float) -> tuple[list[TabEvent], list[float]]:
    events: list[TabEvent] = []
    bars: list[float] = []
    pending: Link | None = None
    i = 0
    while i < len(chars):
        char = chars[i]
        t = char.text
        if t.isdigit():
            text, nxt = _read_number(chars, i, unit)
            ghost = i > 0 and chars[i - 1].text == "(" and nxt < len(chars) and chars[nxt].text == ")"
            frets = split_fret_number(text)
            for k, fret in enumerate(frets):
                x = chars[i + k].x0 if len(frets) > 1 else char.x0
                events.append(TabEvent(x=x, string=string, fret=fret, ghost=ghost, link=pending))
                pending = None
            i = nxt
            continue
        if t in "xX":
            events.append(TabEvent(x=char.x0, string=string, fret=None, dead=True, link=pending))
            pending = None
        elif t in _LINKS:
            pending = _LINKS[t]
        elif t == "b" and events and events[-1].fret is not None and i > 0 and chars[i - 1].text in "0123456789)":
            i = _parse_bend(chars, i + 1, events[-1], unit)
            continue
        elif t == "~" and events:
            events[-1].vibrato = True
        elif t == "|":
            bars.append(char.x0)
            pending = None
        i += 1
    return events, bars


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


def _build_system(page: int, group: list[tuple[str, list[Char]]]) -> TabSystem:
    all_chars = [c for _, body in group for c in body]
    dash_widths = [c.x1 - c.x0 for c in all_chars if c.text == "-"]
    unit = median(dash_widths or [c.x1 - c.x0 for c in all_chars])
    events: list[TabEvent] = []
    bar_lists: list[list[float]] = []
    for string, (_, body) in enumerate(group, start=1):
        string_events, string_bars = _parse_string(body, string, unit)
        events.extend(string_events)
        bar_lists.append(string_bars)
    labels = [label for label, _ in group]
    return TabSystem(
        page=page,
        string_count=len(group),
        events=events,
        bars=shared_bars(bar_lists, 0.6 * unit),
        start_x=min(c.x0 for c in all_chars),
        end_x=max(c.x1 for c in all_chars),
        char_width=unit,
        labels=labels if all(labels) else [],
        source="ascii",
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


def extract_ascii_systems(page: Page) -> tuple[list[TabSystem], list[str]]:
    """Find groups of consecutive tab lines on a page."""
    systems: list[TabSystem] = []
    warnings: list[str] = []
    group: list[tuple[str, list[Char]]] = []
    group_ys: list[float] = []
    ignored = 0

    def flush() -> None:
        nonlocal ignored
        if MIN_STRINGS <= len(group) <= MAX_STRINGS:
            systems.append(_build_system(page.number, group))
        elif len(group) > MAX_STRINGS:
            chunks = _split_stacked(group)
            systems.extend(_build_system(page.number, chunk) for chunk in chunks)
            if not chunks:
                warnings.append(
                    f"Página {page.number}: bloco com {len(group)} linhas de tab ignorado (máx. {MAX_STRINGS})."
                )
        elif len(group) >= 2:
            ignored += len(group)

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
        if parsed and adjacent:
            group.append(parsed)
            group_ys.append(line.yc)
        else:
            flush()
            group = [parsed] if parsed else []
            group_ys = [line.yc] if parsed else []
            if not parsed and _is_dashy(line.text) and len(line.text) >= 12:
                ignored += 1
    flush()
    if ignored:
        warnings.append(
            f"Página {page.number}: {ignored} linha(s) com aspeto de tablatura ignoradas "
            "(símbolos não reconhecidos ou linhas de tab incompletas)."
        )
    return systems, warnings
