"""Helpers shared by the tablature extractors."""

from __future__ import annotations

from statistics import median

MAX_FRET = 29  # highest fret Guitar Pro 5 accepts on a track


def cluster_positions(xs: list[float], tolerance: float) -> list[list[float]]:
    """Group sorted positions whose successive distance is within ``tolerance``."""
    clusters: list[list[float]] = []
    for x in sorted(xs):
        if clusters and x - clusters[-1][-1] <= tolerance:
            clusters[-1].append(x)
        else:
            clusters.append([x])
    return clusters


def shared_bars(bar_xs_per_string: list[list[float]], tolerance: float) -> list[float]:
    """Keep bar positions present on at least half of the strings."""
    string_count = len(bar_xs_per_string)
    tagged = sorted((x, s) for s, xs in enumerate(bar_xs_per_string) for x in xs)
    bars: list[float] = []
    group: list[tuple[float, int]] = []

    def flush() -> None:
        if group and len({s for _, s in group}) * 2 >= string_count:
            bars.append(median(x for x, _ in group))

    for x, s in tagged:
        if group and x - group[-1][0] > tolerance:
            flush()
            group = []
        group.append((x, s))
    flush()
    return bars


def split_fret_number(text: str) -> list[int]:
    """Parse a run of digits as one fret, or as single frets if out of range."""
    value = int(text)
    if value <= MAX_FRET:
        return [value]
    return [int(d) for d in text]
