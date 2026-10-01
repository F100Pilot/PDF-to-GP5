"""Intermediate data model shared by extractors, rhythm engine and GP5 writer.

String numbering follows Guitar Pro: string 1 is the highest-pitched string
(top line of a tablature staff).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction


class Link(str, Enum):
    """Technique connecting a note to the previous note on the same string."""

    HAMMER = "h"
    PULL = "p"
    SLIDE_UP = "/"
    SLIDE_DOWN = "\\"
    SHIFT_SLIDE = "sl"  # slide where the second note is picked again


@dataclass
class TabEvent:
    """A single mark on one tablature string at horizontal position ``x``."""

    x: float
    string: int
    fret: int | None  # None for dead notes
    dead: bool = False
    # Printed in parentheses: a tie (sustain) when it repeats the previous fret on
    # the string, otherwise a ghost note (resolved once notes are in playing order).
    parenthesized: bool = False
    vibrato: bool = False
    bend_semitones: int = 0
    bend_release: bool = False
    bend_pre: bool = False  # string bent before picking (straight arrow), or bend held on a tie
    link: Link | None = None
    let_ring: bool = False
    palm_mute: bool = False
    stroke: str | None = None  # "down" (low to high strings) or "up"; strum arrows
    velocity: int | None = None  # MIDI velocity from the dynamic in force (None = default)
    slide_in: str | None = None  # "below" or "above": slide into the note from an unpitched start
    slide_out: str | None = None  # "down" or "up": slide away from the note to no target
    harmonic: str | None = None  # "natural", "pinch" (PH) or "artificial" (AH)
    tapped: bool = False  # right-hand tap
    grace: bool = False  # printed small: a grace note, played just before the next note on its string
    grace_fret: int | None = None  # the grace note played just before this note
    grace_hammer: bool = False  # the grace note is hammered on / pulled off into this note
    staccato: bool = False


@dataclass(frozen=True)
class RhythmMark:
    """A printed rhythm symbol: a note stem (with beams/flags/dots) or a rest.

    ``units`` is the duration in 32nd notes, or None when the symbol was found
    but cannot be expressed (e.g. inside a tuplet other than a triplet).
    """

    x: float
    units: int | None
    tuplet: bool = False  # under a "3" (or "6") bracket: played in 2/3 of its written length
    is_rest: bool = False
    vibrato: bool = False  # under a vibrato line (matters for stem-only tied notes)


@dataclass
class TabSystem:
    """One tablature staff (a line of tab) as found on a page."""

    page: int
    string_count: int
    events: list[TabEvent]
    bars: list[float]  # x positions of bar lines, sorted
    start_x: float
    end_x: float
    char_width: float  # horizontal clustering unit
    labels: list[str] = field(default_factory=list)  # tuning labels, string 1 first
    source: str = "ascii"  # "ascii" | "engraved" | "image" (engraved, read from a picture)
    # Printed number of the bar starting at bars[i] (engraved tabs only), used to
    # detect multi-bar rests. len == len(bars) - 1 when present.
    bar_numbers: list[int | None] = field(default_factory=list)
    rhythm: list[RhythmMark] = field(default_factory=list)  # engraved tabs with rhythm notation
    sections: list[tuple[float, str]] = field(default_factory=list)  # (x, "Chorus") above the staff
    lyrics: list[tuple[float, str, bool]] = field(default_factory=list)  # (x, syllable, joins next word)
    dynamics: list[tuple[float, int]] = field(default_factory=list)  # (x, MIDI velocity)
    # Crescendo (+1) / diminuendo (-1) hairpins below the staff as (x0, x1, direction).
    hairpins: list[tuple[float, float, int]] = field(default_factory=list)
    # Bar lines (x) starting an empty bar that a tie enters: the notes before it sound through the bar.
    tied_bars: list[float] = field(default_factory=list)
    time_signatures: list[tuple[float, int, int]] = field(default_factory=list)  # (x, numerator, denominator)
    tempos: list[tuple[float, int]] = field(default_factory=list)  # (x, BPM) tempo marks above the staff
    signs: list[tuple[float, str]] = field(default_factory=list)  # (x, "Segno" / "Coda" / "Fine")
    jumps: list[tuple[float, str]] = field(default_factory=list)  # (x, "Da Segno al Coda"…) at the end of a bar
    repeat_starts: list[float] = field(default_factory=list)  # x of bar lines opening a repeat ("|:")
    repeat_ends: list[tuple[float, int]] = field(default_factory=list)  # (x of the ":|" bar line, times played)
    endings: list[tuple[float, float, tuple[int, ...]]] = field(default_factory=list)  # volta (x0, x1, passes)


@dataclass
class ScoreNote:
    string: int
    fret: int
    dead: bool = False
    ghost: bool = False
    vibrato: bool = False
    tie: bool = False
    hammer: bool = False  # legato to the next note on this string
    slide: bool = False  # legato slide to the next note on this string
    slide_shift: bool = False  # shift slide (next note picked again)
    slide_in: str | None = None  # "below" / "above"
    slide_out: str | None = None  # "down" / "up"
    harmonic: str | None = None  # "natural", "pinch" or "artificial"
    tapped: bool = False
    grace_fret: int | None = None  # grace note just before this note
    grace_hammer: bool = False
    staccato: bool = False
    bend_semitones: int = 0
    bend_release: bool = False
    bend_pre: bool = False
    let_ring: bool = False
    palm_mute: bool = False
    stroke: str | None = None
    velocity: int | None = None
    parenthesized: bool = False  # unresolved: becomes tie or ghost
    link: Link | None = None  # unresolved link to previous note


@dataclass
class ScoreBeat:
    units: int  # written length in 32nd notes (1..48, always a representable value)
    notes: list[ScoreNote] = field(default_factory=list)
    # Printed stem without a fret: continues (ties) the notes sounding before it.
    tie_previous: bool = False
    tie_vibrato: bool = False
    tuplet: bool = False  # triplet: three in the time of two (sounds 2/3 of ``units``)

    @property
    def is_rest(self) -> bool:
        return not self.notes

    @property
    def duration(self) -> Fraction | int:
        """Sounding length in 32nd notes (a fraction inside a triplet)."""
        return Fraction(2 * self.units, 3) if self.tuplet else self.units


@dataclass
class ScoreMeasure:
    beats: list[ScoreBeat]
    number: int | None = None  # bar number printed in the PDF, when known
    marker: str | None = None  # section name starting at this bar
    time_signature: tuple[int, int] | None = None  # (numerator, denominator); None: not read (filler bar)
    repeat_open: bool = False  # a repeat starts at this bar ("|:")
    repeat_times: int = 0  # a repeat ends with this bar (":|"), played this many times in all
    endings: tuple[int, ...] = ()  # volta ("1.", "2."): bar played only on these passes of the repeat
    tempo: int | None = None  # BPM from the start of this bar (a tempo change printed here)
    sign: str | None = None  # jump target at this bar: "Segno", "Coda"; or "Fine" (the song ends after it)
    jump: str | None = None  # after this bar: "Da Capo", "Da Segno al Coda", … or "Da Coda" (To Coda)

    @property
    def units(self) -> int | Fraction:
        """Length of the bar's contents in 32nd notes (whole unless a triplet is incomplete)."""
        total = sum((beat.duration for beat in self.beats), Fraction(0))
        return int(total) if total.denominator == 1 else total


@dataclass
class Score:
    """One track: its strings, tuning and measures.

    ``numerator``/``denominator`` are the song's first time signature; bars that change it carry
    their own (``ScoreMeasure.time_signature``). Time signatures and repeats are shared by all tracks.
    """

    string_count: int
    tuning: list[int]  # MIDI values, string 1 first
    measures: list[ScoreMeasure]
    numerator: int
    denominator: int
    warnings: list[str] = field(default_factory=list)
    name: str = "Guitar"
    instrument: int = 25  # General MIDI program
    muted: bool = False  # silent track (e.g. the lyrics carrier)
