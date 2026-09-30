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
from fractions import Fraction
from typing import Literal

from .i18n import tr
from .model import Link, RhythmMark, ScoreBeat, ScoreMeasure, ScoreNote, TabEvent, TabSystem

# Durations Guitar Pro can express on a single beat (plain or dotted), in 32nds.
REPRESENTABLE_UNITS = (48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1)

RhythmMode = Literal["auto", "spacing", "fixed"]
WHOLE_NOTE_UNITS = 32


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
class RhythmStats:
    """How many bars with notes got their durations from printed rhythm vs. spacing."""

    notated: int = 0
    estimated: int = 0


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
        warnings.append(
            tr(
                f"Página {system.page}: {dropped} nota(s) sobreposta(s) na mesma corda foram ignoradas.",
                f"Page {system.page}: {dropped} overlapping note(s) on the same string were ignored.",
            )
        )
    return columns


def _to_notes(events: list[TabEvent]) -> list[ScoreNote]:
    return [
        ScoreNote(
            string=e.string,
            fret=e.fret if e.fret is not None else 0,
            dead=e.dead,
            parenthesized=e.parenthesized,
            vibrato=e.vibrato,
            let_ring=e.let_ring,
            palm_mute=e.palm_mute,
            stroke=e.stroke,
            velocity=e.velocity,
            bend_semitones=e.bend_semitones,
            bend_release=e.bend_release,
            bend_pre=e.bend_pre,
            link=e.link,
            slide_in=e.slide_in,
            slide_out=e.slide_out,
            harmonic=e.harmonic,
            tapped=e.tapped,
            grace_fret=e.grace_fret,
            grace_hammer=e.grace_hammer,
            staccato=e.staccato,
        )
        for e in sorted(events, key=lambda e: e.string)
    ]


def _ties(notes: list[ScoreNote]) -> list[ScoreNote]:
    return [
        ScoreNote(
            string=n.string, fret=n.fret, tie=True, let_ring=n.let_ring, palm_mute=n.palm_mute, velocity=n.velocity
        )
        for n in notes
        if not n.dead
    ]


class _TiePrevious(list):
    """Marker for a (notes, length) item that continues the notes sounding before it."""

    def __init__(self, vibrato: bool = False) -> None:
        super().__init__()
        self.vibrato = vibrato


def _sequence(items: list[tuple[list[ScoreNote], int]], measure_units: int) -> list[ScoreMeasure]:
    """Lay out (notes, length) items across measures, tying over bar lines."""
    measures: list[ScoreMeasure] = []
    current: list[ScoreBeat] = []
    filled: int | Fraction = 0
    for notes, length, *tuplet in items:
        if tuplet and tuplet[0]:
            # A triplet note is never split: a notated bar holds whole triplets.
            if isinstance(notes, _TiePrevious):
                current.append(ScoreBeat(length, tie_previous=True, tie_vibrato=notes.vibrato, tuplet=True))
            else:
                current.append(ScoreBeat(length, notes, tuplet=True))
            filled += Fraction(2 * length, 3)
            if filled >= measure_units:
                measures.append(ScoreMeasure(current))
                current, filled = [], 0
            continue
        first = True
        while length > 0:
            take = min(measure_units - filled, length)
            for part in split_units(take):
                if isinstance(notes, _TiePrevious):
                    current.append(ScoreBeat(part, tie_previous=True, tie_vibrato=notes.vibrato))
                else:
                    current.append(ScoreBeat(part, notes if first else _ties(notes)))
                first = False
            filled += take
            length -= take
            if filled == measure_units:
                measures.append(ScoreMeasure(current))
                current, filled = [], 0
    if current:
        current.extend(ScoreBeat(part) for part in split_units(int(measure_units - filled)))
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


def _notated_items(
    cols: list[_Column], marks: list[RhythmMark], units: int, tolerance: float
) -> list[tuple[list[ScoreNote], int, bool]] | None:
    """Durations from printed stems/rests, or None if they don't account for the bar exactly.

    A note without a stem is a whole note (editors draw none for it).
    """
    stems = [m for m in marks if not m.is_rest]
    if any(m.units is None for m in marks):
        return None
    entries: list[tuple[float, list[ScoreNote], int, bool]] = []
    used: set[int] = set()
    for col in cols:
        index = min(range(len(stems)), key=lambda i: abs(stems[i].x - col.x), default=None)
        if index is None or abs(stems[index].x - col.x) > tolerance:
            entries.append((col.x, _to_notes(col.events), WHOLE_NOTE_UNITS, False))
            continue
        if index in used:
            return None
        used.add(index)
        entries.append((col.x, _to_notes(col.events), stems[index].units or 0, stems[index].tuplet))
    # A stem without a fret continues the previous notes (editors may hide tied frets).
    entries.extend(
        (stem.x, _TiePrevious(stem.vibrato), stem.units or 0, stem.tuplet)
        for i, stem in enumerate(stems)
        if i not in used
    )
    entries.extend((m.x, [], m.units or 0, m.tuplet) for m in marks if m.is_rest)
    if sum(Fraction(2 * length, 3) if tuplet else length for *_, length, tuplet in entries) != units:
        return None
    return [(notes, length, tuplet) for _, notes, length, tuplet in sorted(entries, key=lambda e: e[0])]


def signature_units(signature: tuple[int, int]) -> int:
    """Bar length in 32nd notes of a time signature (numerator, denominator)."""
    numerator, denominator = signature
    return numerator * 32 // denominator


def _mark_repeats(system: TabSystem, start: float, end: float, produced: list[ScoreMeasure]) -> None:
    """Repeat signs and volta brackets of the bar between two bar lines."""
    tolerance = system.char_width
    if any(abs(x - start) <= tolerance for x in system.repeat_starts):
        produced[0].repeat_open = True
    times = [count for x, count in system.repeat_ends if abs(x - end) <= tolerance]
    if times:
        produced[-1].repeat_times = max(times)
    for x0, x1, passes in system.endings:
        if x0 - tolerance <= start < x1 - tolerance:
            for measure in produced:
                measure.endings = passes


def _spacing_measures(
    system: TabSystem,
    columns: list[_Column],
    signature: tuple[int, int],
    warnings: list[str],
    next_number: int | None = None,
    stats: RhythmStats | None = None,
    track_has_rhythm: bool = False,
) -> tuple[list[ScoreMeasure], tuple[int, int]]:
    """Measures of one line of tab, and the time signature in force at its end.

    A time signature printed in a bar (or before the first bar line) applies from that bar on.
    """
    bounds = sorted(system.bars)
    if not bounds or columns and columns[0].x < bounds[0]:
        bounds.insert(0, system.start_x)
    if columns and columns[-1].x > bounds[-1]:
        bounds.append(system.end_x)
    numbers = system.bar_numbers if len(system.bar_numbers) == len(bounds) - 1 else []
    pending_sections = sorted(system.sections)
    pending_signatures = sorted(system.time_signatures)
    # Tempo marks and Segno / Coda start their bar; jumps and "Fine" are printed at the end of theirs.
    tolerance = system.char_width
    pending_tempos = sorted(system.tempos)
    pending_starts = sorted((x, name) for x, name in system.signs if name != "Fine")
    pending_ends = sorted(
        [(x, "sign", name) for x, name in system.signs if name == "Fine"]
        + [(x, "jump", name) for x, name in system.jumps]
    )
    measures: list[ScoreMeasure] = []
    for index, (start, end) in enumerate(itertools.pairwise(bounds)):
        printed = [(n, d) for x, n, d in pending_signatures if x < end]
        pending_signatures = [item for item in pending_signatures if item[0] >= end]
        if printed:
            signature = printed[-1]
        produced = _segment_measures(
            system,
            columns,
            start,
            end,
            signature_units(signature),
            warnings,
            stats,
            numbers,
            index,
            next_number,
            track_has_rhythm,
        )
        if produced:
            for measure in produced:
                measure.time_signature = signature
            _mark_repeats(system, start, end, produced)
            for x, bpm in pending_tempos:
                if x < end:
                    produced[0].tempo = bpm
            for x, name in pending_starts:
                if x < end:
                    produced[0].sign = name
            for x, kind, name in pending_ends:
                if x - tolerance < end:
                    setattr(produced[-1], kind, name)
            pending_tempos = [item for item in pending_tempos if item[0] >= end]
            pending_starts = [item for item in pending_starts if item[0] >= end]
            pending_ends = [item for item in pending_ends if item[0] - tolerance >= end]
            names = [name for x, name in pending_sections if x < end]
            pending_sections = [(x, name) for x, name in pending_sections if x >= end]
            if names:
                produced[0].marker = " / ".join(names)
        first_number = numbers[index] if index < len(numbers) else None
        if first_number is not None and produced:
            if all(not beat.notes for m in produced for beat in m.beats):
                for offset, measure in enumerate(produced):  # (multi-)bar rest: consecutive numbers
                    measure.number = first_number + offset
            else:
                produced[0].number = first_number
        measures.extend(produced)
    if measures:  # printed past the last bar line: the line's last bar
        for _, kind, name in pending_ends:
            setattr(measures[-1], kind, name)
    return measures, signature


def _segment_measures(
    system: TabSystem,
    columns: list[_Column],
    start: float,
    end: float,
    units: int,
    warnings: list[str],
    stats: RhythmStats | None,
    numbers: list[int | None],
    index: int,
    next_number: int | None,
    track_has_rhythm: bool = False,
) -> list[ScoreMeasure]:
    """Measures for the bar between two bar lines (more than one for multi-bar rests)."""
    unit_width = system.char_width
    cols = [c for c in columns if start <= c.x < end]
    if not cols:
        if any(abs(start - x) <= unit_width for x in system.tied_bars):
            return _sequence([(_TiePrevious(), units)], units)  # a tie runs through the empty bar
        if end - start >= 3 * unit_width:  # an explicit empty bar is a full-bar rest
            return [_rest_bar(units) for _ in range(_bar_span(numbers, index, next_number))]
        return []
    marks = [m for m in system.rhythm if start <= m.x < end]
    notated = _notated_items(cols, marks, units, 0.6 * unit_width) if system.rhythm else None
    if notated is None and not system.rhythm and track_has_rhythm and len(cols) == 1:
        # The part prints rhythm, yet this line has no stems at all: a lone note is a
        # whole note (editors draw it without a stem), so its length is known.
        notated = [(_to_notes(cols[0].events), units)]
    if stats is not None:
        if notated is not None:
            stats.notated += 1
        else:
            stats.estimated += 1
    if notated is not None:
        return _sequence(notated, units)
    if len(cols) > units:
        warnings.append(
            tr(
                f"Página {system.page}: compasso com {len(cols)} notas excede a métrica; notas em fusas (1/32).",
                f"Page {system.page}: bar with {len(cols)} notes exceeds the time signature; "
                "notes written as 32nd notes.",
            )
        )
        return _sequence([(_to_notes(c.events), 1) for c in cols], units)
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
    return _sequence(items, units)


def fill_tied_continuations(measures: list[ScoreMeasure]) -> None:
    """Give stem-only beats tied copies of the notes sounding just before them."""
    sounding: list[ScoreNote] = []
    for measure in measures:
        for beat in measure.beats:
            if beat.tie_previous:
                beat.notes = _ties(sounding)
                for note in beat.notes:
                    note.vibrato = beat.tie_vibrato
                beat.tie_previous = False
            if beat.notes:
                sounding = beat.notes
            else:
                sounding = []  # a rest ends what was ringing


def resolve_links(measures: list[ScoreMeasure]) -> None:
    """Resolve marks that depend on the previous note on the same string.

    * hammer/pull/slide marks move onto the note they start from;
    * a parenthesised fret repeating the previous fret on the string is a tie
      (the note sustains; editors print tied notes in parentheses, and tools
      such as Rocksmith importers turn ties into sustain); a parenthesised
      fret that differs from the previous one is a ghost note;
    * a bend is held on a tied note unless the bend was released; a bend drawn on a tied note
      after an unbent one starts there.
    """
    last: dict[int, ScoreNote] = {}
    for measure in measures:
        for beat in measure.beats:
            for note in beat.notes:
                prev = last.get(note.string)
                if note.parenthesized:
                    if prev is not None and not prev.dead and prev.fret == note.fret:
                        note.tie = True
                    else:
                        note.ghost = True
                if note.tie and note.bend_semitones and prev is not None and prev.bend_semitones:
                    note.bend_pre = True  # a bend going on over a tie is held, not re-bent
                elif note.tie and prev is not None and prev.bend_semitones and not prev.bend_release:
                    note.bend_semitones, note.bend_pre = prev.bend_semitones, True  # hold the bend
                if note.link is not None and prev is not None and not prev.dead:
                    if note.link in (Link.HAMMER, Link.PULL):
                        prev.hammer = True
                    elif note.link is Link.SHIFT_SLIDE:
                        prev.slide_shift = True
                    else:
                        prev.slide = True
                last[note.string] = note


def build_measures(
    systems: list[TabSystem],
    options: RhythmOptions,
    warnings: list[str],
    system_measures: list[int] | None = None,
    stats: RhythmStats | None = None,
) -> list[ScoreMeasure]:
    """Build all measures; ``system_measures`` (if given) receives the bar count per system.

    ``options`` gives the time signature of the first bar; signatures printed later change it.
    """
    units = options.measure_units
    signature = (options.numerator, options.denominator)
    per_system = [(s, _columns(s, warnings)) for s in systems]
    use_spacing = options.mode == "spacing" or (options.mode == "auto" and all(len(s.bars) >= 2 for s in systems))
    if options.mode == "auto" and not use_spacing:
        warnings.append(
            tr(
                "Tablatura sem barras de compasso em todas as linhas: usadas durações fixas.",
                "Tablature without bar lines on every line: fixed durations used.",
            )
        )
    measures: list[ScoreMeasure] = []
    track_has_rhythm = any(s.rhythm for s in systems)
    if use_spacing:
        for index, (system, columns) in enumerate(per_system):
            following = systems[index + 1].bar_numbers if index + 1 < len(systems) else []
            system_bars, signature = _spacing_measures(
                system, columns, signature, warnings, following[0] if following else None, stats, track_has_rhythm
            )
            measures.extend(system_bars)
            if system_measures is not None:
                system_measures.append(len(system_bars))
    else:
        beat_units = 32 // options.fixed_value
        items = [(_to_notes(c.events), beat_units) for _, columns in per_system for c in columns]
        measures = _sequence(items, units)
        for measure in measures:  # no bar lines: one time signature, no repeats
            measure.time_signature = signature
    fill_tied_continuations(measures)
    resolve_links(measures)
    return measures
