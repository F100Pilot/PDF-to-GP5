"""Tablature in a picture (a screenshot, a photo of a print, a PDF page that is only an image).

The picture is turned into the same ``Page`` model the vector reader produces — staff and bar
lines as segments, fret numbers as characters — so ``extract_engraved_systems`` reads it like an
engraved PDF. Staff and bar lines are found with image morphology (OpenCV); the fret numbers are
read by a small text-recognition model (RapidOCR's PP-OCR recogniser, run with ONNX Runtime).

Only fret numbers, staff lines and bar lines are read: rhythm comes from the horizontal spacing,
and techniques (bends, slides, ties…) are not seen.
"""

from __future__ import annotations

import io
import itertools
import os
import re
from collections.abc import Callable
from pathlib import Path

from ..i18n import tr
from .pdf_reader import Char, Page, PdfReadError, Segment

# Staff spacing (pixels) the line and digit thresholds below were tuned at; a picture is
# rescaled to it before reading. Coordinates handed on are scaled so the spacing is 7 units,
# about an engraved PDF's staff spacing in points.
_TARGET_SPACING = 16.0
_OUTPUT_SPACING = 7.0
_DARK = 200  # gray level: thin anti-aliased lines are mid-grey
_CORE = 128  # gray level of the darkest pixels, the cores of strokes
_MAX_RENDER_SIDE = 6000  # pixels, after rescaling
_FIRST_WIDTH = 1300  # pixels across at the first look (see _normalized)

IMAGE_KINDS = {"png": b"\x89PNG\r\n\x1a\n", "jpeg": b"\xff\xd8\xff"}


def image_kind(head: bytes) -> str | None:
    """Kind of picture from the file's signature: "png", "jpeg", "webp", or None."""
    for kind, magic in IMAGE_KINDS.items():
        if head.startswith(magic):
            return kind
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _missing() -> PdfReadError:
    return PdfReadError(
        tr(
            "A leitura de imagens (OCR) não está instalada: falta o pacote rapidocr-onnxruntime.",
            "Image reading (OCR) is not installed: the rapidocr-onnxruntime package is missing.",
        )
    )


_RECOGNIZER = None


def _recognizer():
    """The text recogniser (reads one line of text from its picture), loaded once."""
    global _RECOGNIZER
    if _RECOGNIZER is None:
        # ONNX Runtime sends usage telemetry to Microsoft from a background thread unless this is
        # set before it is imported; nothing leaves the computer
        os.environ["ORT_DISABLE_TELEMETRY"] = "1"
        try:
            from rapidocr_onnxruntime.ch_ppocr_rec import TextRecognizer
        except ImportError as exc:
            raise _missing() from exc
        _RECOGNIZER = TextRecognizer(_model_config("Rec"))
    return _RECOGNIZER


_DETECTOR = None


def _detector():
    """The text detector (boxes around lines of text), loaded once: only for the page heading."""
    global _DETECTOR
    if _DETECTOR is None:
        _recognizer()  # same package checks and telemetry switch
        from rapidocr_onnxruntime.ch_ppocr_det import TextDetector

        _DETECTOR = TextDetector(_model_config("Det"))
    return _DETECTOR


def _model_config(section: str) -> dict:
    import rapidocr_onnxruntime
    from rapidocr_onnxruntime.utils import read_yaml

    root = Path(rapidocr_onnxruntime.__file__).parent
    config = read_yaml(str(root / "config.yaml"))[section]
    config["model_path"] = str(root / config["model_path"])
    config["intra_op_num_threads"] = config["inter_op_num_threads"] = 1
    return config


def _cv():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise _missing() from exc
    return cv2, np


def _staff_lines(dark, cv2, np) -> list[tuple[float, int, int, int, int]]:
    """(y, top row, bottom row, x0, x1) of each staff line. A horizontal opening keeps the
    line's pieces between the digits; a row is a line when those pieces cover most of its
    own extent — a row of digit strokes (a dense strummed part) covers only the digits."""
    w = dark.shape[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, w // 300), 1))
    opened = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, kernel)
    rows = opened.sum(axis=1)
    lines: list[list[int]] = []
    long_piece = max(8, w // 100)  # longer than a stroke of a letter beside the staff (a tuning label)
    for y in np.where(rows >= w * 0.10)[0]:
        xs = np.where(opened[y])[0]
        edges = np.flatnonzero(np.diff(np.concatenate(([0], opened[y].astype(np.int8), [0]))))
        pieces = [(a, b) for a, b in zip(edges[::2], edges[1::2], strict=True) if b - a >= long_piece]
        if pieces:  # the line starts at its first long piece (pieces between digits can be short)
            xs = xs[xs >= pieces[0][0]]
        if rows[y] / (xs[-1] - xs[0] + 1) < 0.55:
            continue
        if lines and y - lines[-1][1] <= 1:
            last = lines[-1]
            last[1], last[2], last[3] = int(y), min(last[2], int(xs[0])), max(last[3], int(xs[-1]))
        else:
            lines.append([int(y), int(y), int(xs[0]), int(xs[-1])])
    # a staff line is thin; a thicker band is a multi-bar rest or a beam
    return [((a + b) / 2, a, b, x0, x1) for a, b, x0, x1 in lines if b - a <= 3]


def _complete(lines, dark, np):
    """Add lines missing at the edge of an equally spaced group (covered by many digits: a chord
    on every string, as Songsterr prints), testing the expected row with a looser rule. Repeated
    while it finds more, since several lines in a row can be missing."""
    if len(lines) < 4:
        return lines
    spacing = float(np.median(np.diff([line[0] for line in lines])))
    out = sorted(lines)
    for _ in range(4):
        added = []
        replaced = set()
        for y0, _, _, x0, x1 in out:
            for y in (y0 - spacing, y0 + spacing):
                if not 1 <= y < dark.shape[0] - 2 or any(abs(o[0] - y) < spacing * 0.3 for o in added):
                    continue
                there = [o for o in out if abs(o[0] - y) < spacing * 0.3]
                # a line found there already, unless only a part of it (a bar where a chord covers
                # every string): then it is tested at the neighbour's width and widened
                if there and (there[0][4] - there[0][3] >= 0.9 * (x1 - x0) or there[0] in replaced):
                    continue
                if not any(abs(o[0] - (2 * y0 - y)) < 2 for o in out):  # a neighbour on the other side
                    continue
                # a nearly solid line, or its pieces with digits on it: the digits, taller than the
                # line, add ink around the row; a dashed "let ring" line beside the staff adds none
                reach = max(2, round(0.35 * spacing))
                row = dark[int(y) - 1 : int(y) + 2, x0:x1].any(axis=0).mean()
                band = dark[max(0, int(y) - reach) : int(y) + reach + 1, x0:x1].any(axis=0).mean()
                if row >= 0.8 or (row >= 0.35 and band >= row + 0.05):
                    if there:
                        replaced.add(there[0])
                        y = there[0][0]
                    added.append((y, int(y), int(y), x0, x1))
        if not added:
            break
        out = sorted([o for o in out if o not in replaced] + added)
    return out


def _same_extent(line, other, step: float) -> bool:
    """Two lines of the same staff: one end at the same place, the other within a few spaces
    (ties hanging over from the line before, or on to the next, cover the start or the end of
    the outer lines in Songsterr)."""
    start, end = abs(line[3] - other[3]), abs(line[4] - other[4])
    return (start <= step and end <= 8 * step) or (end <= step and start <= 8 * step)


def _staves(lines):
    """Groups of 4–7 equally spaced lines with the same extent. A line that does not fit the
    spacing (a lyrics underline, a stray rule) is skipped instead of breaking the staff."""
    ys = [line[0] for line in lines]
    out, used = [], set()
    for i, top in enumerate(lines):
        if i in used:
            continue
        best: list[int] | None = None
        for j in range(i + 1, len(lines)):
            spacing = ys[j] - ys[i]
            if spacing < 5:
                continue
            if spacing > 60:
                break
            group, last, step = [i], i, spacing
            for n in range(1, 7):
                # from the last line found, with the mean spacing so far: line positions are
                # whole pixels, so one gap alone can be half a pixel off and the error adds up
                want = ys[last] + step
                near = [
                    m
                    for m in range(last + 1, len(lines))
                    if abs(ys[m] - want) <= max(1.5, step * 0.08) and _same_extent(lines[m], top, step)
                ]
                if not near:
                    break
                last = min(near, key=lambda m: abs(ys[m] - want))
                group.append(last)
                step = (ys[last] - ys[i]) / n
            if len(group) >= 4 and (best is None or len(group) > len(best)):
                best = group
        if best:
            _extend(best, lines, ys, used)
            out.append([lines[m] for m in sorted(best)])
            used.update(best)
    return out


def _extend(group: list[int], lines, ys, used: set[int]) -> None:
    """Add a line just above or below the group at its median spacing: the group may have
    been started from its second line when the first gap was a pixel off."""
    step = sorted(ys[b] - ys[a] for a, b in itertools.pairwise(group))[(len(group) - 1) // 2]
    for edge, sign in ((group[0], -1), (group[-1], 1)):
        if len(group) >= 7:
            return
        want = ys[edge] + sign * step
        near = [
            m
            for m in range(len(lines))
            if m not in used
            and m not in group
            and abs(ys[m] - want) <= max(1.5, step * 0.08)
            and _same_extent(lines[m], lines[edge], step)
        ]
        if near:
            group.append(min(near, key=lambda m: abs(ys[m] - want)))


def _find_staves(gray, cv2, np):
    dark = gray < _DARK
    groups = _staves(_complete(_staff_lines(dark, cv2, np), dark, np))
    spacing = float(np.median([np.median(np.diff([line[0] for line in g])) for g in groups])) if groups else 0.0
    return dark, groups, spacing


def _brackets(blobs):
    """(left parenthesis, the number's own blobs, right parenthesis) of a group of blobs on a
    line. The recogniser reads a parenthesis as "1", "[" or "]", so it is kept out of the crop and
    put back as a character (the tab reader makes the note a tie or a ghost note). A parenthesis
    is a blob at an end of the group about as tall as the digits and far narrower. A "1" can be
    nearly as narrow: a blob only somewhat narrow counts as one of a pair round the number."""

    def shape(blob, inner, ratio: float, relative: float) -> bool:
        _, _, w, h, _ = blob
        widest, tallest = max(b[2] for b in inner), max(b[3] for b in inner)
        return w <= ratio * h and w <= relative * widest and h >= 0.7 * tallest

    def strict(blob, inner) -> bool:
        return shape(blob, inner, 0.25, 0.4)

    def loose(blob, inner) -> bool:
        return shape(blob, inner, 0.35, 0.45)

    blobs = list(blobs)
    if len(blobs) < 2:
        return None, blobs, None
    first, last = blobs[0], blobs[-1]
    middle = blobs[1:-1] or None
    if middle and loose(first, middle) and loose(last, middle):
        return first, middle, last  # a pair of parentheses round the number
    left = first if strict(first, blobs[1:]) else None
    right = last if strict(last, blobs[:-1]) and len(blobs) > (2 if left else 1) else None
    return left, blobs[1 if left else 0 : len(blobs) - 1 if right else len(blobs)], right


def _chord_brackets(numbers, spacing: float):
    """_brackets of each group, with what a chord says: in a column where the other notes are in
    parentheses, a narrow blob at the end of a number is its parenthesis too (one of the pair
    may have been lost to a neighbour or read on its own)."""
    parts = [_brackets(group) for group in numbers]
    columns = [(group[0][0] + group[-1][0] + group[-1][2]) / 2 for group in numbers]
    bracketed = [x for x, (left, _, right) in zip(columns, parts, strict=True) if left and right]
    out = []
    for x, (left, blobs, right) in zip(columns, parts, strict=True):
        if len(blobs) >= 2 and any(abs(x - other) <= 0.6 * spacing for other in bracketed):
            if not left and _narrow(blobs[0], blobs[1:]):
                left, blobs = blobs[0], blobs[1:]
            if not right and len(blobs) >= 2 and _narrow(blobs[-1], blobs[:-1]):
                right, blobs = blobs[-1], blobs[:-1]
        out.append((left, blobs, right))
    return out


def _narrow(blob, inner) -> bool:
    """A blob shaped like a parenthesis beside the digits ``inner``: thin, nearly as tall."""
    _, _, w, h, _ = blob
    return w <= 0.45 * h and h >= 0.7 * max(b[3] for b in inner) and w < max(b[2] for b in inner)


def _stacked(blobs) -> bool:
    """Blobs one above the other (a rest drawn on the staff, read as "1"): the digits of a
    number stand side by side."""
    for a, b in itertools.combinations(blobs, 2):
        overlap = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
        if overlap > 0.5 * min(a[2], b[2]):
            return True
    return False


def _misread_digit(text: str) -> bool:
    """A free reading with no digit that may still be one: a Latin letter, or a character of
    another script (the model reads Chinese). Not the TAB clef's capitals, an accent read as "A",
    nor a rest read as "y"."""
    return any((ch.isalpha() or not ch.isascii()) and ch not in "TABYy" for ch in text)


def _clean(text: str) -> str:
    """Fret text only: letters the recogniser confuses with digits are mapped back (the model also
    reads Chinese, and a lone round 0 can come out as the ideographic full stop)."""
    text = text.strip().translate(
        str.maketrans({"O": "0", "o": "0", "。": "0", "〇": "0", "○": "0", "l": "1", "I": "1", "|": "1"})
    )
    return "".join(ch for ch in text if ch.isdigit() or ch in "()xX")


def _read_page(gray, number: int, heading: bool = False, frets: bool = True) -> tuple[Page, Page | None]:
    """The tab page read from the picture, and with ``heading`` the text above its first staff.
    Without ``frets`` (inspecting a file to fill in the form) only the staves, bar lines and
    time signatures are read: the fret numbers and bar numbers are most of the work."""
    cv2, np = _cv()
    dark, groups, spacing = _find_staves(gray, cv2, np)
    height, width = gray.shape
    if not groups:
        return Page(number, float(width), float(height), [], []), None
    k = _OUTPUT_SPACING / spacing
    segments: list[Segment] = []
    on_line = np.zeros_like(dark)
    # the line's own pixels are its long horizontal runs, so a digit's short stroke
    # crossing the line (the middle of a 2 or a 5) is kept
    run = cv2.getStructuringElement(cv2.MORPH_RECT, (max(8, int(spacing * 0.9)), 1))
    long_runs = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, run).astype(bool)
    # in a small print the gap behind a number is one faint pixel, so the line's run goes on
    # through the digit's stroke (the top of a 6's loop, the bar of a 4). Among the darkest
    # pixels that gap still breaks the run: a short run of them is the digit's, kept.
    core = gray < _CORE
    long_runs &= ~core | cv2.morphologyEx(core.astype(np.uint8), cv2.MORPH_OPEN, run).astype(bool)
    bars: list[list[float]] = []  # bar line x per staff, in pixels
    for group in groups:
        bars.append([])
        x0, x1 = min(line[3] for line in group), max(line[4] for line in group)
        for y, a, b, lx0, lx1 in group:
            # the staff's whole width: an outer line's start can be hidden (see _same_extent)
            segments.append(Segment(x0 * k, x1 * k, y * k, y * k))
            on_line[a - 1 : b + 2, lx0 : lx1 + 1] |= long_runs[a - 1 : b + 2, lx0 : lx1 + 1]
        top, bottom = group[0][0], group[-1][0]
        ya, yb = round(top), round(bottom)
        # bar lines: thin columns dark over the whole staff height
        xs = np.where(dark[ya : yb + 1, x0:x1].mean(axis=0) >= 0.92)[0]
        for cols in np.split(xs, np.where(np.diff(xs) > 1)[0] + 1) if len(xs) else []:
            if len(cols) <= max(3, spacing * 0.35):
                xc = x0 + float(cols.mean())
                on_line[ya : yb + 1, x0 + int(cols[0]) : x0 + int(cols[-1]) + 1] = True
                if bars[-1] and xc - bars[-1][-1] < 0.6 * spacing:
                    continue  # the second stroke of a double bar line: one bar line
                bars[-1].append(xc)
                segments.append(Segment(xc * k, xc * k, top * k, bottom * k))

    glyph = dark & ~on_line
    chars = _frets(glyph, groups, spacing, k) if frets else []
    signatures = _time_signatures(gray, glyph, groups, bars, spacing, k)
    numbers = _bar_numbers(gray, dark, groups, bars, spacing, k) if frets else []
    labels = _tuning_labels(dark, groups, spacing, k)  # also when inspecting: the form shows the tuning
    page = Page(number, width * k, height * k, chars + signatures + numbers + labels, segments)
    if frets:
        stems, shapes, flags = _rhythm(dark, groups, spacing, k)
        page.segments.extend(stems)
        page.curves.extend(shapes)
        rests, rest_dots, misread = _rests(dark, glyph, groups, spacing, k, chars)
        page.chars = [c for c in page.chars if not any(c is m for m in misread)]
        page.chars.extend(flags + rests)
        page.curves.extend(rest_dots)
    if not heading:
        return page, None
    head = _heading(gray, groups, spacing, k, number)
    first = min(groups, key=lambda group: group[0][0])  # the time signature at the start, for the form
    head.chars.extend(c for c in signatures if first[0][0] * k <= c.top - 0.9 * (c.bottom - c.top) <= first[-1][0] * k)
    return page, head


def _split_chords(blobs, line_ys: list[float], spacing: float):
    """The blobs, with two digits of a chord that touch (one above the other, on neighbouring
    strings, in a small picture) cut apart halfway between their strings."""
    for x, y, w, h, area in blobs:
        inside = [ly for ly in line_ys if y < ly < y + h]
        if 1.25 * spacing < h <= 2.6 * spacing and len(inside) == 2 and inside[1] - inside[0] < 1.3 * spacing:
            cut = round((inside[0] + inside[1]) / 2)
            yield x, y, w, cut - y, area
            yield x, cut, w, y + h - cut, area
        else:
            yield x, y, w, h, area


def _frets(glyph, groups, spacing: float, k: float) -> list[Char]:
    """Fret numbers: digit-sized blobs centred on a staff line, read by the recogniser."""
    cv2, np = _cv()
    count, _, stats, _ = cv2.connectedComponentsWithStats(glyph.astype(np.uint8), connectivity=8)
    line_ys = [line[0] for group in groups for line in group]
    line_rows = {line[0]: (line[1], line[2]) for group in groups for line in group}
    # the staff's width, per line: a letter left of the staff (a tuning label) is not a fret
    line_span = {
        line[0]: (min(other[3] for other in group), max(other[4] for other in group))
        for group in groups
        for line in group
    }
    candidates = []  # digit-sized blobs centred on a staff line: (x, y, w, h, line y)
    for x, y, w, h, area in _split_chords(stats[1:count], line_ys, spacing):
        # a digit is taller than wide (a wide blob is a rest or a beam)
        if area < 4 or not (0.45 * spacing <= h <= 1.25 * spacing and w <= 1.6 * spacing and w <= h):
            continue
        line_y = min(line_ys, key=lambda ly, yc=y + h / 2: abs(ly - yc))
        start, end = line_span[line_y]
        if abs(line_y - (y + h / 2)) <= 0.4 * spacing and x + w > start and x < end:
            candidates.append((int(x), int(y), int(w), int(h), line_y))
    candidates.sort(key=lambda c: (c[4], c[0]))
    numbers: list[list[tuple[int, int, int, int, float]]] = []  # neighbouring blobs: one number
    for c in candidates:
        last = numbers[-1][-1] if numbers else None
        if last and last[4] == c[4] and c[0] - (last[0] + last[2]) <= 0.35 * spacing:
            numbers[-1].append(c)
        else:
            numbers.append([c])

    boxes, crops, brackets = [], [], []
    pad = int(spacing * 0.4)
    for left, blobs, right in _chord_brackets([g for g in numbers if not _stacked(g)], spacing):
        brackets.append((left, right))
        gx0, gx1 = min(c[0] for c in blobs), max(c[0] + c[2] for c in blobs)
        gy0, gy1 = min(c[1] for c in blobs), max(c[1] + c[3] for c in blobs)
        pixels = glyph[gy0:gy1, gx0:gx1].copy()
        # where the gap behind the number is a pixel or two, the end of the staff line stays
        # stuck to it: in the line's rows, keep only what lies under the number's own width
        # (the line's own rows and one more each side: a stroke just beside the line, like the bar
        # of a 4 in a small print, belongs to the digit)
        first, last = line_rows[blobs[0][4]]
        band = slice(max(0, first - 1 - gy0), max(0, last + 2 - gy0))
        outside = pixels.copy()
        outside[band] = False
        cols = np.where(outside.any(axis=0))[0]
        if len(cols):
            pixels[band, : cols[0]] = False
            pixels[band, cols[-1] + 1 :] = False
            gx0, gx1 = gx0 + int(cols[0]), gx0 + int(cols[-1]) + 1
            pixels = pixels[:, cols[0] : cols[-1] + 1]
        crop = np.full((gy1 - gy0 + 2 * pad, gx1 - gx0 + 2 * pad), 255, np.uint8)
        crop[pad : pad + gy1 - gy0, pad : pad + gx1 - gx0][pixels] = 0
        scale = 48 / crop.shape[0]
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        crops.append(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR))
        boxes.append((gx0, gx1, gy0, gy1))
    chars: list[Char] = []
    if crops:
        results = _recognize(crops)  # free reading, then _clean: better than digits only here
        # a digit read as a letter or a Chinese character ("d" for 0, "的" for 9): read again as
        # digits only. Not a mark read as ASCII punctuation (a slide's stroke) or as one of the
        # letters _misread_digit leaves out, which digits only would turn into a 1 or a 7.
        again = [i for i, text in enumerate(results) if not _clean(text) and _misread_digit(text)]
        for i, text in zip(again, _read_digits([crops[i] for i in again]), strict=True):
            results[i] = text
        for (gx0, gx1, gy0, gy1), (left, right), text in zip(boxes, brackets, results, strict=True):
            text = _clean(text)
            if left or right:
                text = text.strip("()")
            if not text:
                continue
            step = (gx1 - gx0) / len(text)
            for j, ch in enumerate(text):  # one character per digit, the box split evenly
                chars.append(Char(ch, (gx0 + j * step) * k, (gx0 + (j + 1) * step) * k, gy0 * k, gy1 * k))
            for bracket, symbol in ((left, "("), (right, ")")):
                if bracket:
                    bx, _, bw, _, _ = bracket
                    chars.append(Char(symbol, bx * k, (bx + bw) * k, gy0 * k, gy1 * k))
    return chars


def _tuning_labels(dark, groups, spacing: float, k: float) -> list[Char]:
    """The note names printed left of a staff, one per string ("E A D G B E", Songsterr's
    "C G D# A# F A#"), as characters left of each line: the tab reader takes them for the tuning
    when every string has one. A staff with nothing there (all but the first, usually) costs no
    reading."""
    cv2, np = _cv()
    out: list[Char] = []
    for group in groups:
        x0 = min(line[3] for line in group)  # the staff's start (see _read_page)
        left = max(0, x0 - round(5 * spacing))
        if x0 - left < spacing:
            continue
        boxes = []
        for line in group:
            y = line[0]
            top, bottom = max(0, round(y - 0.5 * spacing)), round(y + 0.5 * spacing)
            region = dark[top:bottom, left : x0 - 2]
            cols = np.flatnonzero(region.any(axis=0))
            rows = np.flatnonzero(region.any(axis=1))
            if not len(cols) or len(rows) < 0.3 * spacing:
                break
            boxes.append((left + int(cols[0]), left + int(cols[-1]) + 1, top + int(rows[0]), top + int(rows[-1]) + 1))
        if len(boxes) != len(group):
            continue
        crops = []
        for bx0, bx1, by0, by1 in boxes:
            pad = round(spacing * 0.3)
            crop = np.full((by1 - by0 + 2 * pad, bx1 - bx0 + 2 * pad), 255, np.uint8)
            crop[pad : pad + by1 - by0, pad : pad + bx1 - bx0][dark[by0:by1, bx0:bx1]] = 0
            crop = cv2.resize(crop, None, fx=48 / crop.shape[0], fy=48 / crop.shape[0], interpolation=cv2.INTER_AREA)
            crops.append(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR))
        texts = _recognize(crops, "ABCDEFGabcdefg#")
        if not all(texts) or any(t[0].upper() not in "ABCDEFG" for t in texts):
            continue
        for (bx0, bx1, by0, by1), text in zip(boxes, texts, strict=True):
            name = text[0].upper() + text[1:2].replace("B", "b")
            out.append(Char(name, bx0 * k, bx1 * k, by0 * k, by1 * k))
    return out


# SMuFL flags by how many there are on a stem (8th, 16th, 32nd), as music fonts write them.
_FLAGS = {1: "\ue241", 2: "\ue243", 3: "\ue245"}


def _rhythm(dark, groups, spacing: float, k: float) -> tuple[list[Segment], list[Segment], list[Char]]:
    """Rhythm drawn with the tab ("tab with stems"), as the shapes a vector PDF has: stems as
    vertical segments; beams and augmentation dots as filled shapes; flags as their music-font
    glyphs. The reader of printed rhythm (rhythm_marks) then works as for a PDF; a bar its marks
    do not add up for (a tuplet, a rest not recognised) keeps the rhythm estimated from the
    spacing."""
    cv2, np = _cv()
    height = dark.shape[0]
    ink = dark.astype(np.uint8)
    tall = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, round(spacing / 2))))
    stems: list[Segment] = []
    shapes: list[Segment] = []
    flags: list[Char] = []
    tops = sorted(round(group[0][0]) for group in groups)
    bottoms = sorted(round(group[-1][0]) for group in groups)
    for group in groups:
        top, bottom = round(group[0][0]), round(group[-1][0])
        x0, x1 = min(line[3] for line in group), max(line[4] for line in group) + 1
        below_end = min([t for t in tops if t > bottom] + [height])
        above_start = max([b for b in bottoms if b < top] + [0])
        # the rhythm zone under the staff (or over it): up to 4.5 spaces away, short of a neighbour
        for y0, y1, below in (
            (bottom + 2, min(round(bottom + 4.5 * spacing), below_end - round(spacing)), True),
            (max(round(top - 4.5 * spacing), above_start + round(spacing)), top - 1, False),
        ):
            if y1 - y0 < spacing:
                continue
            zone = ink[y0:y1, x0:x1]
            lines = tall[y0:y1, x0:x1]
            count, _, stats, _ = cv2.connectedComponentsWithStats(lines, connectivity=8)
            found = []  # (x, top, bottom) in zone pixels
            for sx, sy, sw, sh, _ in stats[1:count]:
                # a stem starts (under the staff) about 2/3 of a space from it, or 5/3 for a half
                # note's shorter one; letters of lyrics further away have strokes as tall
                # (its width counts the columns as tall as the stem: a flag adds shorter ones)
                near = sy if below else (y1 - y0) - (sy + sh)
                heights = lines[sy : sy + sh, sx : sx + sw].sum(axis=0)
                thick = int((heights >= 0.6 * heights.max()).sum())
                if not (thick <= max(3, 0.35 * spacing) and 0.8 * spacing <= sh <= 4 * spacing and near <= 2 * spacing):
                    continue
                column = sx + int(heights.argmax())
                if _alone(zone, column, sy, sy + sh, below, spacing):
                    found.append((column, sy, sy + sh))
            if not found:
                continue
            rest = zone.copy()
            for column, a, b in found:
                rest[a:b, max(0, column - 2) : column + 3] = 0
            count, labels, stats, _ = cv2.connectedComponentsWithStats(rest, connectivity=8)
            for index, (bx, by, bw, bh, area) in enumerate(stats[1:count], start=1):
                fill = area / (bw * bh)
                # (a partial beam, the stub of a 16th beside an 8th, is shorter but touches a stem)
                touching = any(bx - 4 <= c <= bx + bw + 3 for c, _, _ in found)
                wide = bw >= 0.5 * spacing or (touching and bw >= 0.3 * spacing)
                if wide and 0.12 * spacing <= bh <= 1.2 * spacing and fill >= 0.6:
                    # a beam, or two or three beams run together: one shape per band of full rows
                    rows = (labels[by : by + bh, bx : bx + bw] == index).mean(axis=1) >= 0.5
                    edges = np.flatnonzero(np.diff(np.concatenate(([0], rows.astype(np.int8), [0]))))
                    # back to the stems it was cut from (a partial beam is only that long)
                    left = min([c for c, _, _ in found if bx - 4 <= c <= bx] + [bx])
                    right = max([c + 1 for c, _, _ in found if bx + bw <= c <= bx + bw + 3] + [bx + bw])
                    for a, b in zip(edges[::2], edges[1::2], strict=True):
                        if b - a >= 0.12 * spacing:
                            # as thick as the reader expects: a small print draws it 2 px thick
                            middle, half = y0 + by + (a + b) / 2, min(max(b - a, 0.25 * spacing), 0.4 * spacing) / 2
                            shapes.append(
                                Segment((x0 + left) * k, (x0 + right) * k, (middle - half) * k, (middle + half) * k)
                            )
                elif (
                    0.12 * spacing <= bw <= 0.4 * spacing
                    and 0.12 * spacing <= bh <= 0.4 * spacing
                    and fill >= 0.5
                    and any(c + 3 <= bx <= c + 1.2 * spacing and a <= by + bh / 2 <= b for c, a, b in found)
                ):
                    # an augmentation dot: right of a stem, beside it (not a stray bit of
                    # lyrics punctuation under it)
                    shapes.append(_dot(x0 + bx + bw / 2, y0 + by + bh / 2, spacing, k))
                else:
                    flag = _flag_count(labels[by : by + bh, bx : bx + bw] == index, bx, by, found, below, spacing)
                    if flag:
                        column, end = flag[1], flag[2]
                        flags.append(
                            Char(
                                _FLAGS[flag[0]],
                                (x0 + column) * k,
                                (x0 + column + spacing) * k,
                                (y0 + end - spacing / 2) * k,
                                (y0 + end + spacing / 2) * k,
                            )
                        )
            for c, a, b in found:
                stem = Segment((x0 + c) * k, (x0 + c) * k, (y0 + a) * k, (y0 + b) * k)
                # staves close together: the zone under one and the zone over the next overlap
                if not any(abs(o.x0 - stem.x0) <= k and o.top < stem.bottom and stem.top < o.bottom for o in stems):
                    stems.append(stem)
    return stems, shapes, flags


# Rests drawn on a tab staff, by their size in staff spaces (width, height), as MuseScore draws
# them (and the Ultimate Guitar prints made with it), with their SMuFL glyphs.
_RESTS = (
    ("\ue4e5", (0.5, 0.82), (1.7, 2.3)),  # quarter: a narrow zigzag
    ("\ue4e7", (0.85, 1.1), (1.65, 2.1)),  # 16th: two hooks
    ("\ue4e6", (0.65, 0.95), (1.0, 1.45)),  # 8th: one hook
)


def _rests(dark, glyph, groups, spacing: float, k: float, frets: list[Char]):
    """Rests on the tab staves, as their music-font glyphs (the reader of printed rhythm counts
    them); the dots just right of them as small filled shapes; and the fret numbers that were a
    piece of a rest (an 8th rest's tail read as "1"). The staff lines cut a rest into pieces:
    they are joined again across the lines. A shape of no known size is left out (its bar keeps
    the rhythm estimated from the spacing)."""
    cv2, np = _cv()
    joined = cv2.morphologyEx(
        glyph.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
    )
    count, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    boxes = [(c.x0 / k, c.x1 / k, c.top / k, c.bottom / k) for c in frets]
    out: list[Char] = []
    dots: list[Segment] = []
    misread: list[Char] = []
    small = [
        (bx, by, bw, bh)
        for bx, by, bw, bh, area in stats[1:count]
        if 0.12 * spacing <= bw <= 0.4 * spacing and 0.12 * spacing <= bh <= 0.4 * spacing and area >= 0.5 * bw * bh
    ]
    for group in groups:
        top, bottom = group[0][0], group[-1][0]
        ys = [line[0] for line in group]
        x0, x1 = min(line[3] for line in group), max(line[4] for line in group)
        middle = (top + bottom) / 2
        for bx, by, bw, bh, area in stats[1:count]:
            if not (x0 < bx and bx + bw < x1 and top - spacing < by and by + bh < bottom + spacing):
                continue
            if abs(by + bh / 2 - middle) > 1.2 * spacing:
                continue
            inside = [i for i, box in enumerate(boxes) if _overlap((bx, bx + bw, by, by + bh), box) > 0.3]
            # a fret number, or numbers of a chord joined across the lines; but a "1" far
            # shorter than the shape is the tail of a rest the recogniser read (a rest just
            # touching a number is still a rest; a 3 with a tie's arc on it is still a 3)
            piece = (
                len(inside) == 1
                and frets[inside[0]].text == "1"
                and boxes[inside[0]][3] - boxes[inside[0]][2] <= 0.7 * bh
            )
            if inside and not piece:
                continue
            w, h = bw / spacing, bh / spacing
            text = next((t for t, (w0, w1), (h0, h1) in _RESTS if w0 <= w <= w1 and h0 <= h <= h1), None)
            # (the line it touches went with the staff lines: its fill is measured with them)
            if (
                text is None
                and 0.7 <= w <= 1.15
                and 0.2 <= h <= 0.65  # (the line under it went with the staff lines)
                and dark[by : by + bh, bx : bx + bw].mean() >= 0.8
            ):
                # a filled block: a half rest sits on a line, a whole rest hangs from one
                on = any(abs(by + bh - y) <= 2 for y in ys)
                under = any(abs(by - y) <= 2 for y in ys)
                text = "\ue4e4" if on and not under else "\ue4e3" if under and not on else None
            if text:
                out.append(Char(text, bx * k, (bx + bw) * k, by * k, (by + bh) * k))
                misread.extend(frets[i] for i in inside)
                dots.extend(
                    _dot(dx + dw / 2, dy + dh / 2, spacing, k)
                    for dx, dy, dw, dh in small
                    if bx + bw < dx <= bx + bw + spacing
                    and by - 0.6 * spacing <= dy + dh / 2 <= by + bh + 0.6 * spacing
                )
    return out, dots, misread


def _dot(x: float, y: float, spacing: float, k: float) -> Segment:
    """An augmentation dot centred at (x, y) pixels, a fifth of a space across: anti-aliasing
    makes its blob look bigger than the dot the reader of printed rhythm expects."""
    r = spacing / 10
    return Segment((x - r) * k, (x + r) * k, (y - r) * k, (y + r) * k)


def _overlap(a, b) -> float:
    """Area shared by boxes (x0, x1, top, bottom), as a share of the smaller one."""
    w = min(a[1], b[1]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[2], b[2])
    if w <= 0 or h <= 0:
        return 0.0
    return w * h / max(1e-9, min((a[1] - a[0]) * (a[3] - a[2]), (b[1] - b[0]) * (b[3] - b[2])))


def _alone(zone, column: int, a: int, b: int, below: bool, spacing: float) -> bool:
    """A stem stands alone: beside its half nearer the staff (a flag is on the other half) the
    columns two and three pixels off are nearly empty, unlike a letter's upright stroke with its
    bowl (a "d", a "b"). Rows where a beam leaves the stem (ink running half a space along
    either side) are left out."""
    _, np = _cv()
    margin, reach = round(spacing / 4), round(spacing / 2)
    half = (a + b) // 2
    # the stem's own columns at its middle (a thick one, 3 px in a Songsterr print, included)
    left = right = column
    while left > 0 and zone[half, left - 1] and column - left < 3:
        left -= 1
    while right < zone.shape[1] - 1 and zone[half, right + 1] and right - column < 3:
        right += 1
    sides = [c for c in (left - 3, left - 2, right + 2, right + 3) if 0 <= c < zone.shape[1]]
    if not sides:
        return True
    start, stop = (a + margin, half) if below else (half, b - margin)
    rows = [
        r
        for r in range(start, max(start + 1, stop))
        if not zone[r, max(0, left - reach) : left].all() and not zone[r, right + 1 : right + 1 + reach].all()
    ]
    return not rows or zone[np.ix_(rows, sides)].mean() < 0.15


def _flag_count(mask, bx: int, by: int, stems, below: bool, spacing: float):
    """(flags, stem x, stem end) when the shape ``mask`` (at bx, by in the zone) is the flag of
    a stem: it is joined to the stem near its far end (the bottom of a stem under the staff), and
    reaches right of it. The flags are counted where they cross a column a third of a space
    right of the stem."""
    _, np = _cv()
    h, w = mask.shape
    for column, a, b in stems:
        if not column - 1 <= bx <= column + 3 or w < 0.3 * spacing or not 0.4 * spacing <= h <= 2.5 * spacing:
            continue
        end = b if below else a
        # joined to the stem (the stem's own columns were taken out: its next one), beside the
        # stem's last space, not a letter of the lyrics just past its end
        attach = column + 3 - bx
        if not 0 <= attach < w:
            continue
        joined = by + np.flatnonzero(mask[:, attach])
        if not any(a <= y <= b and abs(y - end) <= spacing for y in joined):
            continue
        if by - spacing <= end <= by + h + spacing:
            probe = min(w - 1, column + round(spacing / 3) - bx)
            crossings = np.flatnonzero(np.diff(np.concatenate(([0], mask[:, probe].astype(np.int8), [0]))) == 1)
            if 1 <= len(crossings) <= 3:
                return len(crossings), column, end
    return None


def _alike(upper, lower, spacing: float) -> bool:
    """The two rows of a time signature: digits of about the same height, each wide enough
    not to be a stem or an arrow."""
    heights = [box[3] - box[2] for box in (upper, lower)]
    widths = [box[1] - box[0] for box in (upper, lower)]
    return max(heights) <= 1.4 * min(heights) and min(widths) >= 0.8 * spacing


def _bar_numbers(gray, dark, groups, bars: list[list[float]], spacing: float, k: float) -> list[Char]:
    """The bar numbers printed just above the staff at the start of a bar (on every bar, or only
    where a line or a multi-bar rest starts). The tab reader counts a multi-bar rest from them,
    as in a PDF — without them the bars after it would come early. A number missing (cut off at
    the picture's edge, misread) is filled from a neighbour and the multi-bar rest's count, the
    big number over the rest: the bar before a "40" with a "4" over it is bar 36."""
    entries = []  # per bar, in reading order: (x, staff top, number box, count box, first of its line)
    for group, staff_bars in zip(groups, bars, strict=True):
        top = group[0][0]
        x0, x1 = min(line[3] for line in group), max(line[4] for line in group)
        bounds: list[float] = []
        for x in sorted([float(x0), *staff_bars, float(x1)]):
            if not bounds or x - bounds[-1] >= 0.6 * spacing:
                bounds.append(x)
        for start, end in itertools.pairwise(bounds):
            reach = 2.0 if start - x0 < spacing else 0.8  # a line's first number can start further left
            number = _small_number(dark, top, start - reach * spacing, start + 1.6 * spacing, spacing)
            entries.append((start, top, number, _rest_count(dark, top, start, end, spacing), start - x0 < spacing))
    boxes = [box for _, _, number, count, _ in entries for box in (number, count) if box]
    votes = iter(_read_boxes(gray, boxes))
    numbers: list[int | None] = []
    counts: list[int | None] = []
    for _, _, number, count, _ in entries:
        text = next(votes) if number else ""
        numbers.append(int(text) if text and len(text) <= 3 else None)
        text = next(votes) if count else ""
        counts.append(int(text) if text and 2 <= int(text) <= 64 else None)
    kept = set(_increasing([(i, n) for i, n in enumerate(numbers) if n is not None]))
    numbers = [n if i in kept else None for i, n in enumerate(numbers)]
    for i in range(len(entries) - 1):
        # a line's first number cut at the picture's edge ("5" for 55) can still go up: a jump
        # there needs the rest's count to back it
        first, jump = entries[i][4], numbers[i + 1] is not None and numbers[i] is not None
        if first and jump and numbers[i + 1] - numbers[i] > 1 and counts[i] != numbers[i + 1] - numbers[i]:
            numbers[i] = None
    for _ in range(2):  # fill gaps from a neighbour and the rest's count, both ways
        for i in range(len(entries) - 1):
            if numbers[i] is not None and numbers[i + 1] is None and counts[i]:
                numbers[i + 1] = numbers[i] + counts[i]
            if numbers[i] is None and numbers[i + 1] is not None and counts[i]:
                numbers[i] = numbers[i + 1] - counts[i]
    chars: list[Char] = []
    for (x, top, box, _, _), number in zip(entries, numbers, strict=True):
        if number is None:
            continue
        # where the number was read, at its place; a filled-in one just after the bar line
        bx0, bx1, by0, by1 = box or (x, x + 0.6 * spacing, top - 1.0 * spacing, top - 0.4 * spacing)
        text = str(number)
        step = (bx1 - bx0) / len(text)
        for j, digit in enumerate(text):
            chars.append(Char(digit, (bx0 + j * step) * k, (bx0 + (j + 1) * step) * k, by0 * k, by1 * k))
    return chars


def _read_boxes(gray, boxes) -> list[str]:
    """Digits in each box: read once with a middle margin, and only those that come back empty
    again with the other margins (most bar numbers read the first time; three readings of
    every one doubled the time of a page)."""
    if not boxes:
        return []
    texts = _read_digits([_margins(gray, *box, margins=(0.6,))[0] for box in boxes])
    retry = [i for i, text in enumerate(texts) if not text]
    if retry:
        again = _read_digits([crop for i in retry for crop in _margins(gray, *boxes[i], margins=(0.3, 1.0))])
        for n, i in enumerate(retry):
            texts[i] = _vote(again[2 * n : 2 * n + 2])
    return texts


def _components(dark, y0: float, y1: float, x0: float, x1: float):
    """Connected blobs (x, y, w, h, area) of the dark pixels in the box, in its coordinates."""
    cv2, np = _cv()
    a, b, c, d = max(0, int(x0)), int(x1), max(0, int(y0)), int(y1)
    if b - a < 3 or d - c < 3:
        return a, c, []
    count, _, stats, _ = cv2.connectedComponentsWithStats(dark[c:d, a:b].astype(np.uint8), connectivity=8)
    return a, c, [tuple(int(v) for v in row) for row in stats[1:count]]


def _small_number(dark, top: float, left: float, right: float, spacing: float):
    """Box (x0, x1, y0, y1) of the first small number between ``left`` and ``right`` in the band
    just above the staff (a bar number), or None."""
    a, c, blobs = _components(dark, top - 1.5 * spacing, top - 0.2 * spacing, left, right)
    digits = sorted(
        (x, y, w, h)
        for x, y, w, h, area in blobs
        if 0.35 * spacing <= h <= 1.0 * spacing and w <= 2.5 * h and area >= 4  # italic digits touch
    )
    if not digits:
        return None
    run = [digits[0]]  # the first number from the bar line: digits side by side
    for d in digits[1:]:
        if d[0] - (run[-1][0] + run[-1][2]) <= 0.3 * d[3] and abs(d[1] - run[-1][1]) <= 0.3 * d[3]:
            run.append(d)
    return (
        a + run[0][0],
        a + max(d[0] + d[2] for d in run),
        c + min(d[1] for d in run),
        c + max(d[1] + d[3] for d in run),
    )


def _rest_count(dark, top: float, start: float, end: float, spacing: float):
    """Box of the big number centred over a bar (how many bars a multi-bar rest stands for), or
    None: digits taller than a bar number, in the middle of the bar, just above the staff."""
    a, c, blobs = _components(
        dark, top - 2.2 * spacing, top - 0.1 * spacing, start + 0.5 * spacing, end - 0.5 * spacing
    )
    middle = (end - start) / 2 - 0.5 * spacing
    digits = sorted(
        (x, y, w, h)
        for x, y, w, h, _ in blobs
        if 0.85 * spacing <= h <= 2.0 * spacing and w <= 1.5 * h and abs(x + w / 2 - middle) <= 1.5 * spacing
    )
    if not digits or len(digits) > 2:
        return None
    return (
        a + digits[0][0],
        a + max(d[0] + d[2] for d in digits),
        c + min(d[1] for d in digits),
        c + max(d[1] + d[3] for d in digits),
    )


def _increasing(read: list[tuple[int, int]]) -> list[int]:
    """Indexes of the longest run of (index, bar number) pairs whose numbers go up in reading
    order (staves top to bottom, bars left to right): a misread number ("63" between 52 and 54)
    would make the tab reader count a multi-bar rest that is not there; dropped, it is filled in
    from its neighbours where it can be."""
    if not read:
        return []
    best = [1] * len(read)
    before = [-1] * len(read)
    for i, (_, number) in enumerate(read):
        for j in range(i):
            if read[j][1] < number and best[j] + 1 > best[i]:
                best[i], before[i] = best[j] + 1, j
    i = max(range(len(read)), key=best.__getitem__)
    kept = []
    while i >= 0:
        kept.append(read[i][0])
        i = before[i]
    return kept[::-1]


def _signature_row(gray, band, origin: tuple[int, int], cx0: int, cx1: int, h0: int, h1: int):
    """One row of a time signature cut to its ink (found on the cleaned ``band``), as a crop of
    the picture itself for the recogniser — it reads these big digits better with their
    anti-aliasing and a wide white margin than as clean black shapes — at each margin, and its
    box."""
    _, np = _cv()
    rows = np.where(band[h0:h1, cx0:cx1].any(axis=1))[0]
    cols = np.where(band[h0:h1, cx0:cx1].any(axis=0))[0]
    if not len(rows) or not len(cols):
        return None
    ry0, ry1 = h0 + int(rows[0]), h0 + int(rows[-1]) + 1
    rx0, rx1 = cx0 + int(cols[0]), cx0 + int(cols[-1]) + 1
    left, top = origin
    return _margins(gray, left + rx0, left + rx1, top + ry0, top + ry1), (rx0, rx1, ry0, ry1)


def _margins(gray, x0: int, x1: int, y0: int, y1: int, margins=None) -> list:
    """The picture's digits in the box, with each white margin (default _SIGNATURE_MARGINS)."""
    cv2, np = _cv()
    digit = np.ascontiguousarray(gray[y0:y1, x0:x1])
    crops = []
    for margin in margins or _SIGNATURE_MARGINS:
        pad = int(margin * (y1 - y0))
        crop = cv2.copyMakeBorder(digit, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
        scale = 48 / crop.shape[0]
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        crops.append(cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR))
    return crops


# A lone digit (of a time signature, a bar number) is read unreliably (with a wide margin it can come back empty, "12" once as
# "42"): each row is read with three white margins, and the reading that wins outright is kept.
_SIGNATURE_MARGINS = (0.3, 0.6, 1.0)


def _read_digits(crops) -> list[str]:
    """Read each crop as digits only. Left free, the model — trained mostly on Chinese — reads
    a lone big digit as a Chinese character ("左" for a 4)."""
    return _recognize(crops, "0123456789")


# Crops read in one run of the model; each run is as wide as its widest crop.
_BATCH = 16


def _recognize(crops, alphabet: str | None = None) -> list[str]:
    """Text of each crop. The library pads every crop to a 320 px wide line before reading;
    a fret number is a few dozen pixels wide, so nearly all of that work went on white space
    (17 s for a page of a strummed song). Here crops of similar width are read together, at
    the width of the widest. With ``alphabet``, the model's scores at each position are kept
    for those characters (and the CTC blank) alone."""
    _, np = _cv()
    recognizer = _recognizer()
    decode = recognizer.postprocess_op
    allowed = [0] + [decode.dict[ch] for ch in alphabet] if alphabet else None  # 0 is the CTC blank
    ratios = [crop.shape[1] / crop.shape[0] for crop in crops]
    order = sorted(range(len(crops)), key=ratios.__getitem__)
    out = [""] * len(crops)
    for start in range(0, len(order), _BATCH):
        batch = order[start : start + _BATCH]
        widest = max(ratios[i] for i in batch)
        if alphabet:
            widest = max(widest, 320 / 48)  # lone digits read best on the library's 320 px line
        images = np.stack([recognizer.resize_norm_img(crops[i], widest) for i in batch])
        scores = recognizer.session(images.astype(np.float32))[0]
        if allowed is None:
            texts = [text for text, _ in decode(scores)]
        else:
            texts = []
            for best in scores[:, :, allowed].argmax(axis=2):
                kept = [i for j, i in enumerate(best) if i and (j == 0 or best[j - 1] != i)]  # CTC
                texts.append("".join(alphabet[i - 1] for i in kept))
        for i, text in zip(batch, texts, strict=True):
            out[i] = text
    if alphabet is None:
        # a lone digit read with little room can come back empty (a "0"): read those again on
        # their own at the library's 320 px line, where it reads them
        for i, text in enumerate(out):
            if not text.strip():
                image = recognizer.resize_norm_img(crops[i], max(ratios[i], 320 / 48))[np.newaxis]
                out[i] = decode(recognizer.session(image.astype(np.float32))[0])[0][0]
    return out


def _vote(texts: list[str]) -> str:
    digits = [text for text in texts if text.isdigit()]
    counts = sorted((digits.count(text) for text in set(digits)), reverse=True)
    if not counts or (len(counts) > 1 and counts[0] == counts[1]):
        return ""  # nothing read, or a tie
    return max(set(digits), key=digits.count)


# Music-font digits, as an engraved PDF writes a time signature (see bar_signs.time_signatures).
_SIGNATURE_DIGITS = {str(d): chr(0xE080 + d) for d in range(10)}
_DENOMINATORS = (2, 4, 8, 16)


def _time_signatures(gray, glyph, groups, bars: list[list[float]], spacing: float, k: float) -> list[Char]:
    """Time signatures on the staves ("4/4" at the start, or a change later): two big digits, or
    rows of them, stacked inside the staff — each over a spacing high, where a fret number is
    about 0.7. They come back as the music-font characters an engraved PDF has, so the tab
    reader puts them in the bars as it does for a PDF. The staff lines run through them: the
    gaps the line removal left are closed first (which also joins the two stacked digits), and
    the pair is then cut in the middle. A time signature stands at the
    start of the staff (after the clef) or just after a bar line, in the middle of the staff."""
    cv2, np = _cv()
    chars: list[Char] = []
    for group, staff_bars in zip(groups, bars, strict=True):
        top, bottom = group[0][0], group[-1][0]
        x0, x1 = min(line[3] for line in group), max(line[4] for line in group)
        y0, y1 = max(0, int(top - 0.3 * spacing)), int(bottom + 0.3 * spacing) + 1
        starts = [x0 + 2.5 * spacing] + [bar for bar in staff_bars]  # clef, then any bar line
        thickness = max(b - a + 1 for _, a, b, _, _ in group)
        joint = cv2.getStructuringElement(cv2.MORPH_RECT, (1, thickness + 3))
        band = cv2.morphologyEx(glyph[y0:y1, x0 : x1 + 1].astype(np.uint8), cv2.MORPH_CLOSE, joint)
        count, _, stats, _ = cv2.connectedComponentsWithStats(band, connectivity=8)
        tall = sorted(
            (int(x), int(y), int(w), int(h))
            for x, y, w, h, _ in stats[1:count]
            if h >= 1.0 * spacing and 0.25 * spacing <= w <= 3.5 * spacing  # a "1" is narrow: rows are checked whole
        )
        clusters: list[list[tuple[int, int, int, int]]] = []  # pieces that overlap across
        for blob in tall:
            if clusters and blob[0] <= max(b[0] + b[2] for b in clusters[-1]) + 0.3 * spacing:
                clusters[-1].append(blob)
            else:
                clusters.append([blob])
        crops, boxes = [], []
        for blobs in clusters:
            cx0, cx1 = min(b[0] for b in blobs), max(b[0] + b[2] for b in blobs)
            cy0, cy1 = min(b[1] for b in blobs), max(b[1] + b[3] for b in blobs)
            if not (2.0 * spacing <= cy1 - cy0 <= bottom - top + 0.6 * spacing and cx1 - cx0 <= 3.5 * spacing):
                continue
            if abs(y0 + (cy0 + cy1) / 2 - (top + bottom) / 2) > 0.6 * spacing:
                continue
            if not any(-0.5 * spacing <= x0 + cx0 - start <= 2.5 * spacing for start in starts):
                continue
            cut = (cy0 + cy1) // 2  # both rows are the same size (the emptiest row can be a digit's thin tip)
            halves = ((cy0, cut), (cut, cy1))
            if any(h1 - h0 < 1.15 * spacing for h0, h1 in halves):  # a fret digit is ~0.7
                continue
            pair = [_signature_row(gray, band, (x0, y0), cx0, cx1, h0, h1) for h0, h1 in halves]
            if all(pair) and _alike(*(box for _, box in pair), spacing):
                for row_crops, (rx0, rx1, ry0, ry1) in pair:
                    crops.extend(row_crops)
                    boxes.append((x0 + rx0, x0 + rx1, y0 + ry0, y0 + ry1))
        if not crops:
            continue
        read = _read_digits(crops)
        n = len(_SIGNATURE_MARGINS)
        texts = [_vote(read[i : i + n]) for i in range(0, len(read), n)]
        # read freely too: digits only makes a digit of anything (a column of parentheses round a
        # chord's notes, in Songsterr, came out as 8/8); a real one is a digit either way
        free = _recognize(crops[::n])
        texts = [
            text if any(ch.isdigit() for ch in _clean(other)) else "" for text, other in zip(texts, free, strict=True)
        ]
        for i in range(0, len(texts) - 1, 2):
            numerator, denominator = texts[i], texts[i + 1]
            if not (numerator.isdigit() and denominator.isdigit()):
                continue
            if not (1 <= int(numerator) <= 32 and int(denominator) in _DENOMINATORS):
                continue
            for text, (bx0, bx1, by0, by1) in ((numerator, boxes[i]), (denominator, boxes[i + 1])):
                size, centre, step = by1 - by0, (by0 + by1) / 2, (bx1 - bx0) / len(text)
                for j, digit in enumerate(text):
                    # an engraved PDF reports a music-font glyph's box about one em below the
                    # glyph (see rhythm_marks.glyph_ys): place it the same way
                    chars.append(
                        Char(
                            _SIGNATURE_DIGITS[digit],
                            (bx0 + j * step) * k,
                            (bx0 + (j + 1) * step) * k,
                            (centre + 0.9 * size) * k,
                            (centre + 1.9 * size) * k,
                        )
                    )
    return chars


# A tempo mark read from a picture: the note glyph is lost or read as a letter, and "=" can come
# out as a (full-width) colon — "♩ = 97" is read as "：97" or "J=97".
_TEMPO_MARK = re.compile(r"^\s*[^\w\s]?[Jjd」]?\s*[=：:＝﹦]\s*(?=\d{2,3}\b)")


def _join_lines(rects: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Join boxes on the same line that almost touch: the detector can cut a tempo mark in two
    ("♩ =" and "97"), and the number alone does not say it is a tempo."""
    out: list[list[int]] = []
    for x0, y0, x1, y1 in sorted(rects):
        for box in out:
            overlap = min(y1, box[3]) - max(y0, box[1])
            height = min(y1 - y0, box[3] - box[1])
            # side by side (touching or a small gap apart) and on the same line
            if overlap > 0.7 * height and -0.3 * height <= x0 - box[2] <= 0.6 * height:
                box[:] = [min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1)]
                break
        else:
            out.append([x0, y0, x1, y1])
    return [(a, b, c, d) for a, b, c, d in out]


def _with_spaces(text: str, info, crop, np) -> str:
    """Put back the spaces between words that the recogniser (trained mostly on Chinese text)
    often leaves out ("VerticalHorizon"): one at each wide blank gap in the picture, between the
    two characters the recogniser placed on either side of it. Between two digits only a wider
    gap counts: the detector can take a tempo mark and the bar count printed after it as one
    line ("= 145" and "3" read "= 1453"), but the digits of a number sit close together."""
    columns = [col for word in info[2] for col in word]
    ink = crop < 160
    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    if len(columns) != len(text) or len(rows) < 2 or len(cols) < 2:
        return text
    height = rows[-1] - rows[0] + 1
    gaps = [((a + b) / 2, b - a - 1) for a, b in itertools.pairwise(cols) if b - a - 1 > 0.25 * height]
    xs = [col / max(info[0], 1) * crop.shape[1] for col in columns]  # each character's x in the crop
    cuts = set()
    for gap, width in gaps:
        cut = next((i for i in range(1, len(text)) if xs[i - 1] < gap < xs[i]), None)
        digits = cut and text[cut - 1].isdigit() and text[cut].isdigit()
        if cut and " " not in text[cut - 1 : cut + 1] and (not digits or width > 0.3 * height):
            cuts.add(cut)
    return "".join(f" {ch}" if i in cuts else ch for i, ch in enumerate(text))


def _read_line(region, rect, np) -> tuple[str, float]:
    """One detected line of text, with its spaces. A number alone ("97") may be a tempo mark whose
    "♩ =" the detector left out: it is read again with the picture widened to the left, and the
    wider reading kept only if an "=" shows up before the number."""
    x0, y0, x1, y1 = rect
    crops = [region[y0:y1, x0:x1]]
    (text, score, info), *_ = _recognizer()(crops, return_word_box=True)[0]
    if re.fullmatch(r"\s*\d{2,3}\s*", text):
        wider = region[y0:y1, max(0, x0 - 2 * (y1 - y0)) : x1]
        (again, again_score, again_info), *_ = _recognizer()([wider], return_word_box=True)[0]
        if _TEMPO_MARK.match(again):
            crops, text, score, info = [wider], again, again_score, again_info
    return _with_spaces(text, info, crops[0][:, :, 0], np).strip(), score


def _heading(gray, groups, spacing: float, k: float, number: int) -> Page:
    """The text above the first staff (title, artist, tempo mark, tuning…) as a page of characters
    in the same units as the tab page, for the metadata reader. Each line the detector finds is
    read whole and split evenly into characters; spaces are left as gaps."""
    cv2, np = _cv()
    bottom = int(min(group[0][0] for group in groups) - 0.6 * spacing)
    chars: list[Char] = []
    if bottom > 4:
        region = cv2.cvtColor(np.ascontiguousarray(gray[:bottom]), cv2.COLOR_GRAY2BGR)
        detector = _detector()
        # the detector enlarges the picture until its short side is 736 px, which small text needs;
        # a thin strip above the staff would be blown up tenfold and take seconds: at most 2600 px
        detector.limit_side_len = int(min(736, min(region.shape[:2]) * 2600 / max(region.shape[:2])))
        boxes, _ = detector(region)
        rects = []
        for box in boxes if boxes is not None else []:
            x0, y0 = np.maximum(box.min(axis=0), 0).astype(int)
            x1, y1 = box.max(axis=0).astype(int) + 1
            if x1 - x0 >= 4 and y1 - y0 >= 4:
                rects.append((int(x0), int(y0), int(x1), int(y1)))
        for x0, y0, x1, y1 in _join_lines(rects):
            text, score = _read_line(region, (x0, y0, x1, y1), np)
            text = _TEMPO_MARK.sub("= ", text)
            # a tempo mark is measured on its number: the note's stem would make it as tall as a title
            left = x0 + (x1 - x0) // 2 if text.startswith("= ") else x0
            ink = np.where((region[y0:y1, left:x1, 0] < 160).any(axis=1))[0]
            if not text or score < 0.5 or not len(ink):
                continue
            # the height of the ink, not of the detector's box (padded): the metadata reader
            # tells the title by its size
            top, bottom = y0 + int(ink[0]), y0 + int(ink[-1]) + 1
            step = (x1 - x0) / len(text)
            for j, ch in enumerate(text):
                if not ch.isspace():
                    chars.append(Char(ch, (x0 + j * step) * k, (x0 + (j + 1) * step) * k, top * k, bottom * k))
    height, width = gray.shape
    return Page(number, width * k, height * k, chars, [])


def _normalized(
    render: Callable[[float], object], width: float, height: float, number: int, heading: bool, frets: bool = True
) -> tuple[Page, Page | None]:
    """Read the picture at the scale where its staff spacing is the tuned one. It is first looked at
    about 1300 px wide (a whole page of tab then has about that spacing), then at other sizes if no
    staff is found there (a crop of one staff, a huge photo): a staff line is at most 3 px thick, so
    the line thresholds only hold near the right size."""
    cv2, np = _cv()
    limit = _MAX_RENDER_SIDE / max(width, height, 1.0)
    tried: list[float] = []
    for target in (_FIRST_WIDTH, width, _FIRST_WIDTH / 2, _FIRST_WIDTH * 2):
        scale = min(target / max(width, 1.0), limit)
        if any(abs(scale / t - 1) < 0.1 for t in tried):
            continue
        tried.append(scale)
        gray = render(scale)
        _, groups, spacing = _find_staves(gray, cv2, np)
        if groups:
            break
    else:
        return Page(number, float(width), float(height), [], []), None  # no staff at any size
    factor = _TARGET_SPACING / spacing
    if not 0.85 <= factor <= 1.2:
        better = min(scale * factor, limit)
        if abs(better / scale - 1) > 0.05:
            gray = render(better)
    return _read_page(gray, number, heading, frets)


def decode_image(data: bytes, max_pixels: int):
    """Grayscale pixels of a PNG/JPEG/WebP upload, upright (EXIF orientation applied)."""
    _cv()
    import numpy as np
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > max_pixels:
            raise PdfReadError(
                tr(
                    f"Imagem demasiado grande ({image.width}×{image.height}); o máximo é "
                    f"{max_pixels // 1_000_000} megapíxeis.",
                    f"Image too large ({image.width}×{image.height}); the maximum is "
                    f"{max_pixels // 1_000_000} megapixels.",
                )
            )
        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
            flat = Image.new("RGB", image.size, "white")  # transparent screenshot background: white
            flat.paste(image, mask=image.convert("RGBA").getchannel("A"))
            image = flat
        return np.asarray(image.convert("L"))
    except PdfReadError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise PdfReadError(
            tr("A imagem não é válida ou está corrompida.", "The image is not valid or is corrupted.")
        ) from exc


def read_image(data: bytes, max_pixels: int, frets: bool = True) -> tuple[Page, Page | None]:
    """The tab page of an image upload, and the text above its first staff (see ``_heading``)."""
    cv2, _ = _cv()
    original = decode_image(data, max_pixels)

    def render(scale: float):
        if abs(scale - 1) < 0.01:
            return original
        method = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        return cv2.resize(original, None, fx=scale, fy=scale, interpolation=method)

    return _normalized(render, original.shape[1], original.shape[0], 1, heading=True, frets=frets)


def read_pdf_page(data: bytes, index: int, heading: bool = False, frets: bool = True) -> tuple[Page, Page | None]:
    """Page ``index`` (0-based) of a PDF, rendered and read as a picture, and with ``heading`` the
    text above its first staff. Coordinates are in the picture's own units (staff spacing 7), not
    the PDF's points."""
    _, np = _cv()
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise PdfReadError(
            tr("O ficheiro não é um PDF válido ou está corrompido.", "The file is not a valid PDF or is corrupted.")
        ) from exc
    try:
        page = document[index]
        width, height = page.get_size()

        def render(scale: float):
            # rendered in colour and then made grey: pdfium's own greyscale output anti-aliases
            # the digits differently and reads worse
            return np.asarray(page.render(scale=scale).to_pil().convert("L"))

        return _normalized(render, width, height, index + 1, heading, frets)
    finally:
        document.close()
