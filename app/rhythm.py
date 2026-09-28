"""Turn positioned tab events into measures with note durations.

Tablature rarely encodes rhythm explicitly, so two strategies are offered:

* ``spacing``: onsets are quantised from horizontal position inside each bar.
* ``fixed``: every beat gets the same duration and bars are re-built from the
  time signature (useful for tabs without bar lines).

All durations are expressed in 32nd-note units. Every produced measure sums
exactly to the time-signature length, so the GP5 file never has overfull bars.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Literal

from .model import Link, ScoreBeat, ScoreMeasure, ScoreNote, TabEvent, TabSystem

# Durations Guitar Pro can express on a single beat (plain or dotted), in 32nds.
REPRESENTABLE_UNITS = (48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1)

RhythmMode = Literal["auto", "spacing", "fixed"]


@dataclass(frozen=True)
class RhythmOptions:
    mode: RhythmMode = "auto"
    fixed_value: int = 8  # note value used in fixed mode (4, 8 or 16)
    numerator: int = 4
    denominator: int = 4

    @property
    def measure_units(self) -> int:
        return self.numerator * 32 // self.denominator


@dataclass
class _Column:
    x: float
    events: list[TabEvent]


def split_units(units: int) -> list[int]:
    """Decompose a length into representable durations, longest first."""
    parts: list[int] = []
    for value in REPRESENTABLE_UNITS:
        while units >= value:
            parts.append(value)
            units -= value
    return parts


def _columns(system: TabSystem, warnings: list[str]) -> list[_Column]:
    """Group events that are vertically aligned (a chord or a single note)."""
    tolerance = 0.6 * system.char_width
    columns: list[_Column] = []
    dropped = 0
    for event in sorted(system.events, key=lambda e: e.x):
        if columns and event.x - columns[-1].x <= tolerance:
            column = columns[-1]
            if any(e.string == event.string for e in column.events):
                dropped += 1
                continue
            column.events.append(event)
        else:
            columns.append(_Column(event.x, [event]))
    if dropped:
        warnings.append(f"Página {system.page}: {dropped} nota(s) sobreposta(s) na mesma corda foram ignoradas.")
    return columns


def _to_notes(events: list[TabEvent]) -> list[ScoreNote]:
    return [
        ScoreNote(
            string=e.string,
            fret=e.fret if e.fret is not None else 0,
            dead=e.dead,
            ghost=e.ghost,
            vibrato=e.vibrato,
            bend_semitones=e.bend_semitones,
            bend_release=e.bend_release,
            link=e.link,
        )
        for e in sorted(events, key=lambda e: e.string)
    ]


def _ties(notes: list[ScoreNote]) -> list[ScoreNote]:
    return [ScoreNote(string=n.string, fret=n.fret, tie=True) for n in notes if not n.dead]


def _sequence(items: list[tuple[list[ScoreNote], int]], measure_units: int) -> list[ScoreMeasure]:
    """Lay out (notes, length) items across measures, tying over bar lines."""
    measures: list[ScoreMeasure] = []
    current: list[ScoreBeat] = []
    filled = 0
    for notes, length in items:
        first = True
        while length > 0:
            take = min(measure_units - filled, length)
            for part in split_units(take):
                current.append(ScoreBeat(part, notes if first else _ties(notes)))
                first = False
            filled += take
            length -= take
            if filled == measure_units:
                measures.append(ScoreMeasure(current))
                current, filled = [], 0
    if current:
        current.extend(ScoreBeat(part) for part in split_units(measure_units - filled))
        measures.append(ScoreMeasure(current))
    return measures


def _fallback_onsets(xs: list[float], origin: float, end: float, units: int) -> list[int]:
    """Proportional mapping of the bar width onto a 16th (or 32nd) grid."""
    count = len(xs)
    grid = 2 if count * 2 <= units else 1
    span = end - origin if end > origin else 1.0
    onsets: list[int] = []
    for x in xs:
        q = round((x - origin) / span * units / grid) * grid
        q = min(max(q, 0), units - grid)
        if onsets:
            q = max(q, onsets[-1] + grid)
        onsets.append(q)
    for k in range(count - 1, -1, -1):
        onsets[k] = min(onsets[k], units - (count - k) * grid)
    return onsets


def _quantize(xs: list[float], origin: float, end: float, units: int) -> list[int]:
    """Map positions to strictly increasing onsets (32nd units) inside one bar.

    Candidate scales (32nds per point) are derived from the gaps between
    notes: a gap is assumed to be a whole number of grid steps. The candidate
    that lands every note near the grid, keeps the last note inside the bar
    and whose implied bar length best matches the real one wins. Coarser
    grids (8ths) are preferred to finer ones on ties, as tab writers usually
    space notes evenly per beat.
    """
    offsets = [x - origin for x in xs]
    gaps = sorted({round(b - a, 1) for a, b in itertools.pairwise(offsets) if b - a > 0})
    width = end - origin
    best: tuple[float, list[int]] | None = None
    for grid, grid_penalty in ((4, 0.0), (2, 0.05), (1, 0.12)):
        if len(xs) * grid > units:
            continue
        scales = {units / width} if width > 0 else set()
        scales.update(grid * k / gap for gap in gaps for k in range(1, 9))
        for scale in scales:
            positions = [o * scale / grid for o in offsets]
            steps = [round(p) for p in positions]
            onsets = [step * grid for step in steps]
            if any(b <= a for a, b in itertools.pairwise(onsets)) or onsets[0] < 0 or onsets[-1] > units - grid:
                continue
            error = max(abs(p - q) for p, q in zip(positions, steps))
            if error > 0.25:
                continue
            cost = abs(width * scale - units) / units + 0.5 * error + grid_penalty
            if best is None or cost < best[0]:
                best = (cost, onsets)
    return best[1] if best else _fallback_onsets(xs, origin, end, units)


def _rest_bar(units: int) -> ScoreMeasure:
    return ScoreMeasure([ScoreBeat(part) for part in split_units(units)])


def _bar_span(numbers: list[int | None], index: int, next_number: int | None) -> int:
    """How many bars an empty segment stands for (multi-bar rests), from printed bar numbers."""
    current = numbers[index] if index < len(numbers) else None
    following = numbers[index + 1] if index + 1 < len(numbers) else next_number
    if current is not None and following is not None and 1 < following - current <= 64:
        return following - current
    return 1


def _spacing_measures(
    system: TabSystem, columns: list[_Column], units: int, warnings: list[str], next_number: int | None = None
) -> list[ScoreMeasure]:
    unit_width = system.char_width
    bounds = sorted(system.bars)
    if not bounds or columns and columns[0].x < bounds[0]:
        bounds.insert(0, system.start_x)
    if columns and columns[-1].x > bounds[-1]:
        bounds.append(system.end_x)
    numbers = system.bar_numbers if len(system.bar_numbers) == len(bounds) - 1 else []
    measures: list[ScoreMeasure] = []
    for index, (start, end) in enumerate(itertools.pairwise(bounds)):
        cols = [c for c in columns if start <= c.x < end]
        if not cols:
            if end - start >= 3 * unit_width:  # an explicit empty bar is a full-bar rest
                measures.extend(_rest_bar(units) for _ in range(_bar_span(numbers, index, next_number)))
            continue
        if len(cols) > units:
            warnings.append(
                f"Página {system.page}: compasso com {len(cols)} notas excede a métrica; notas em fusas (1/32)."
            )
            measures.extend(_sequence([(_to_notes(c.events), 1) for c in cols], units))
            continue
        content_start = start + unit_width  # skip the bar-line glyph
        if system.source == "engraved" or cols[0].x - content_start <= 1.5 * unit_width:
            origin = cols[0].x
        else:
            origin = content_start + unit_width  # leading rest: assume one spacer before the grid
        onsets = _quantize([c.x for c in cols], origin, end, units)
        items: list[tuple[list[ScoreNote], int]] = []
        if onsets[0] > 0:
            items.append(([], onsets[0]))
        for k, col in enumerate(cols):
            nxt = onsets[k + 1] if k + 1 < len(cols) else units
            items.append((_to_notes(col.events), nxt - onsets[k]))
        measures.extend(_sequence(items, units))
    return measures


def resolve_links(measures: list[ScoreMeasure]) -> None:
    """Move hammer/pull/slide marks onto the note they start from."""
    last: dict[int, ScoreNote] = {}
    for measure in measures:
        for beat in measure.beats:
            for note in beat.notes:
                prev = last.get(note.string)
                if note.link is not None and prev is not None and not prev.dead:
                    if note.link in (Link.HAMMER, Link.PULL):
                        prev.hammer = True
                    else:
                        prev.slide = True
                last[note.string] = note


def build_measures(
    systems: list[TabSystem],
    options: RhythmOptions,
    warnings: list[str],
    system_measures: list[int] | None = None,
) -> list[ScoreMeasure]:
    """Build all measures; ``system_measures`` (if given) receives the bar count per system."""
    units = options.measure_units
    per_system = [(s, _columns(s, warnings)) for s in systems]
    use_spacing = options.mode == "spacing" or (options.mode == "auto" and all(len(s.bars) >= 2 for s in systems))
    if options.mode == "auto" and not use_spacing:
        warnings.append("Tablatura sem barras de compasso em todas as linhas: usadas durações fixas.")
    measures: list[ScoreMeasure] = []
    if use_spacing:
        for index, (system, columns) in enumerate(per_system):
            following = systems[index + 1].bar_numbers if index + 1 < len(systems) else []
            system_bars = _spacing_measures(system, columns, units, warnings, following[0] if following else None)
            measures.extend(system_bars)
            if system_measures is not None:
                system_measures.append(len(system_bars))
    else:
        beat_units = 32 // options.fixed_value
        items = [(_to_notes(c.events), beat_units) for _, columns in per_system for c in columns]
        measures = _sequence(items, units)
    resolve_links(measures)
    return measures
