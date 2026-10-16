"""Playing order of bars with repeats, voltas and D.C./D.S./Coda/Fine, to write a song out.

Rocksmith (and tools converting to it) play a song straight through, so repeated passages must
be written out. The order follows alphaTab's player (the page's playback):

* a repeat end without a start goes back to the song's start; repeats can nest, and a repeat
  inside a repeated passage is played again on every pass;
* a D.C. / D.S. jump is taken once (a D.S. without a Segno is ignored); after it, repeats are no longer
  observed, "To Coda" goes to the Coda and "Fine" ends the song.

One departure from alphaTab, on the return after a D.C. / D.S.: alphaTab plays every volta there (a
1st-time bar sounds again before the 2nd-time one); the usual convention is no repeats and the LAST
ending only, and that is what is written out. A score has no sign saying otherwise, so
``jump_skips_repeats`` tells the caller when the convention changed the bars heard.
"""

from __future__ import annotations

from .model import ScoreMeasure

MAX_PLAYED_BARS = 20_000


def playback_order(
    measures: list[ScoreMeasure], limit: int = MAX_PLAYED_BARS, last_ending_only: bool = True
) -> list[int]:
    """Indexes of ``measures`` in the order they are played (at most ``limit`` bars).

    ``last_ending_only=False`` is alphaTab's own order, every volta played on the return after a
    jump: what the page's player plays from a file that keeps its repeats."""
    return _order(measures, limit, last_ending_only)[0]


def jump_skips_repeats(measures: list[ScoreMeasure], limit: int = MAX_PLAYED_BARS) -> bool:
    """Whether a D.C. / D.S. returns through a repeat or a volta, i.e. whether "no repeats after the
    jump, last ending only" changed the bars heard (the score cannot say which was meant)."""
    return _order(measures, limit, True)[1]


def _last_endings(measures: list[ScoreMeasure]) -> list[int]:
    """For each volta bar, the last pass among the voltas next to it (0 for other bars)."""
    last = [0] * len(measures)
    start = 0
    while start < len(measures):
        if not measures[start].endings:
            start += 1
            continue
        end = start
        while end < len(measures) and measures[end].endings:
            end += 1
        final = max(max(m.endings) for m in measures[start:end])
        last[start:end] = [final] * (end - start)
        start = end
    return last


def _order(measures: list[ScoreMeasure], limit: int, last_ending_only: bool) -> tuple[list[int], bool]:
    last_ending = _last_endings(measures)
    convention = False
    order: list[int] = []
    jumps = [0] * len(measures)  # times each repeat end has sent playback back
    starts = [0]  # open repeats: the bar each goes back to (innermost last)
    current_pass = 0  # 0 the first time through a repeat, 1 the second… (chooses the volta)
    jumped: str | None = None  # the D.C. / D.S. jump taken, if any
    segno = next((i for i, m in enumerate(measures) if m.sign == "Segno"), None)
    coda = next((i for i, m in enumerate(measures) if m.sign == "Coda"), None)
    index = 0
    steps = 0
    while index < len(measures) and len(order) < limit and steps < 4 * limit:
        steps += 1
        measure = measures[index]
        if not jumped:
            if measure.repeat_open and index != starts[-1]:
                starts.append(index)
                current_pass = 0
            if measure.endings and current_pass + 1 not in measure.endings:
                index += 1  # a volta for another pass
                continue
        else:  # the return after a jump: no repeats, the last ending only
            if measure.endings or measure.repeat_times > 1:
                convention = True
            if last_ending_only and measure.endings and last_ending[index] not in measure.endings:
                index += 1
                continue
        order.append(index)
        if not jumped and measure.repeat_times > 1:
            if jumps[index] < measure.repeat_times - 1:
                jumps[index] += 1
                current_pass = jumps[index]
                index = starts[-1]
                continue
            jumps[index] = 0
            current_pass = 0
            if len(starts) > 1:
                starts.pop()
        if jumped:
            if measure.sign == "Fine" and jumped.endswith("al Fine"):
                break
            if measure.jump == "Da Coda" and jumped.endswith("al Coda") and coda is not None:
                index = coda
                continue
        elif measure.jump and (
            measure.jump.startswith("Da Capo") or measure.jump.startswith("Da Segno") and segno is not None
        ):
            jumped = measure.jump  # (a D.S. without a Segno is ignored)
            index = 0 if measure.jump.startswith("Da Capo") else segno
            continue
        index += 1
    return order, convention
