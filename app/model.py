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
    # Printed in parentheses: a tied note if it repeats the previous fret on the
    # string, otherwise a ghost note (resolved once notes are in playing order).
    parenthesized: bool = False
    vibrato: bool = False
    bend_semitones: int = 0
    bend_release: bool = False
    link: Link | None = None
    let_ring: bool = False
    palm_mute: bool = False


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
    let_ring: bool = False
    palm_mute: bool = False
    parenthesized: bool = False  # unresolved: becomes tie or ghost
    link: Link | None = None  # unresolved link to previous note


@dataclass
class ScoreBeat:
    units: int  # length in 32nd notes (1..48, always a representable value)
    notes: list[ScoreNote] = field(default_factory=list)

    @property
    def is_rest(self) -> bool:
        return not self.notes


@dataclass
class ScoreMeasure:
    beats: list[ScoreBeat]


@dataclass
class Score:
    string_count: int
    tuning: list[int]  # MIDI values, string 1 first
    measures: list[ScoreMeasure]
    numerator: int
    denominator: int
    warnings: list[str] = field(default_factory=list)
