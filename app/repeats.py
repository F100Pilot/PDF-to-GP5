"""Playing order of bars with repeats and voltas, to write a song out without repeat signs.

Rocksmith (and tools converting to it) play a song straight through, so repeated passages must
be written out. The order follows alphaTab's player (the page's playback): a repeat end without
a start goes back to the song's start, repeats can nest, and a repeat inside a repeated passage
is played again on every pass.
"""

from __future__ import annotations

from .model import ScoreMeasure

MAX_PLAYED_BARS = 20_000


def playback_order(measures: list[ScoreMeasure], limit: int = MAX_PLAYED_BARS) -> list[int]:
    """Indexes of ``measures`` in the order they are played (at most ``limit`` bars)."""
    order: list[int] = []
    jumps = [0] * len(measures)  # times each repeat end has sent playback back
    starts = [0]  # open repeats: the bar each goes back to (innermost last)
    current_pass = 0  # 0 the first time through a repeat, 1 the second… (chooses the volta)
    index = 0
    steps = 0
    while index < len(measures) and len(order) < limit and steps < 4 * limit:
        steps += 1
        measure = measures[index]
        if measure.repeat_open and index != starts[-1]:
            starts.append(index)
            current_pass = 0
        if measure.endings and current_pass + 1 not in measure.endings:
            index += 1  # a volta for another pass
            continue
        order.append(index)
        if measure.repeat_times > 1:
            if jumps[index] < measure.repeat_times - 1:
                jumps[index] += 1
                current_pass = jumps[index]
                index = starts[-1]
                continue
            jumps[index] = 0
            current_pass = 0
            if len(starts) > 1:
                starts.pop()
        index += 1
    return order
