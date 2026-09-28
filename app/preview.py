"""Plain-text tab rendering of the parsed score, so users can proofread it."""

from __future__ import annotations

from .model import Score, ScoreNote

_DURATION_MARK = {48: "W.", 32: "W", 24: "H.", 16: "H", 12: "Q.", 8: "Q", 6: "E.", 4: "E", 3: "S.", 2: "S", 1: "T"}
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _cell(note: ScoreNote | None) -> str:
    if note is None:
        return ""
    if note.dead:
        return "x"
    text = f"({note.fret})" if note.ghost or note.tie else str(note.fret)
    if note.slide_in:
        text = ("/" if note.slide_in == "below" else "\\") + text
    if note.bend_semitones:
        text += "b"
    if note.vibrato:
        text += "~"
    if note.hammer:
        text += "h"
    if note.slide or note.slide_shift:
        text += "/"
    if note.slide_out:
        text += "\\" if note.slide_out == "down" else "/"
    return text


def render_preview(score: Score, max_measures: int = 32, per_line: int = 4) -> str:
    labels = [_NOTE_NAMES[m % 12] for m in score.tuning]
    if labels[0] == labels[-1]:
        labels[0] = labels[0].lower()  # conventional "e" for the high string
    width = max(len(label) for label in labels)
    blocks: list[str] = []
    measures = score.measures[:max_measures]
    for start in range(0, len(measures), per_line):
        rhythm = " " * (width + 1)
        rows = [label.ljust(width) + "|" for label in labels]
        for measure in measures[start : start + per_line]:
            for beat in measure.beats:
                cells = [""] * score.string_count
                for note in beat.notes:
                    cells[note.string - 1] = _cell(note)
                mark = _DURATION_MARK[beat.units] if beat.notes else _DURATION_MARK[beat.units].lower()
                col = max(3, max(len(c) for c in cells) + 1, len(mark) + 1)
                rhythm += " " + mark.ljust(col - 1)
                rows = [row + "-" + cell.ljust(col - 1, "-") for row, cell in zip(rows, cells)]
            rows = [row + "-|" for row in rows]
            rhythm += "  "
        blocks.append("\n".join([rhythm.rstrip(), *rows]))
    if len(score.measures) > max_measures:
        blocks.append(f"... (+{len(score.measures) - max_measures} compassos)")
    return "\n\n".join(blocks)
