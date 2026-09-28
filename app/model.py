"""Intermediate data model shared by extractors, rhythm engine and GP5 writer.

String numbering follows Guitar Pro: string 1 is the highest-pitched string
(top line of a tablature staff).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Link(str, Enum):
    """Technique connecting a note to the previous note on the same string."""

    HAMMER = "h"
    PULL = "p"
    SLIDE_UP = "/"
    SLIDE_DOWN = "\\"


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


@dataclass(frozen=True)
class RhythmMark:
    """A printed rhythm symbol: a note stem (with beams/flags/dots) or a rest.

    ``units`` is the duration in 32nd notes, or None when the symbol was found
    but cannot be expressed (e.g. inside a tuplet).
    """

    x: float
    units: int | None
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
    source: str = "ascii"  # "ascii" | "engraved"
    # Printed number of the bar starting at bars[i] (engraved tabs only), used to
    # detect multi-bar rests. len == len(bars) - 1 when present.
    bar_numbers: list[int | None] = field(default_factory=list)
    rhythm: list[RhythmMark] = field(default_factory=list)  # engraved tabs with rhythm notation
    sections: list[tuple[float, str]] = field(default_factory=list)  # (x, "Chorus") above the staff
    lyrics: list[tuple[float, str, bool]] = field(default_factory=list)  # (x, syllable, joins next word)
    dynamics: list[tuple[float, int]] = field(default_factory=list)  # (x, MIDI velocity)


@dataclass
class ScoreNote:
    string: int
    fret: int
    dead: bool = False
    ghost: bool = False
    vibrato: bool = False
    tie: bool = False
    hammer: bool = False  # legato to the next note on this string
    slide: bool = False  # slide to the next note on this string
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
    units: int  # length in 32nd notes (1..48, always a representable value)
    notes: list[ScoreNote] = field(default_factory=list)
    # Printed stem without a fret: continues (ties) the notes sounding before it.
    tie_previous: bool = False
    tie_vibrato: bool = False

    @property
    def is_rest(self) -> bool:
        return not self.notes


@dataclass
class ScoreMeasure:
    beats: list[ScoreBeat]
    number: int | None = None  # bar number printed in the PDF, when known
    marker: str | None = None  # section name starting at this bar


@dataclass
class Score:
    """One track: its strings, tuning and measures (all tracks share the time signature)."""

    string_count: int
    tuning: list[int]  # MIDI values, string 1 first
    measures: list[ScoreMeasure]
    numerator: int
    denominator: int
    warnings: list[str] = field(default_factory=list)
    name: str = "Guitar"
    instrument: int = 25  # General MIDI program
