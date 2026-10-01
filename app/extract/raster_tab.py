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
    """The text recogniser alone (no text detection or orientation models), loaded once."""
    global _RECOGNIZER
    if _RECOGNIZER is None:
        # ONNX Runtime sends usage telemetry to Microsoft from a background thread unless this is
        # set before it is imported; nothing leaves the computer
        os.environ["ORT_DISABLE_TELEMETRY"] = "1"
        try:
            import rapidocr_onnxruntime
            from rapidocr_onnxruntime.ch_ppocr_rec import TextRecognizer
            from rapidocr_onnxruntime.utils import read_yaml
        except ImportError as exc:
            raise _missing() from exc
        root = Path(rapidocr_onnxruntime.__file__).parent
        config = read_yaml(str(root / "config.yaml"))["Rec"]
        config["model_path"] = str(root / config["model_path"])
        config["intra_op_num_threads"] = config["inter_op_num_threads"] = 1
        _RECOGNIZER = TextRecognizer(config)
    return _RECOGNIZER


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
    for y in np.where(rows >= w * 0.10)[0]:
        xs = np.where(opened[y])[0]
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
    """Add a line missing at the edge of an equally spaced group (covered by many digits),
    testing the expected row with a looser rule."""
    if len(lines) < 4:
        return lines
    spacing = float(np.median(np.diff([line[0] for line in lines])))
    out = list(lines)
    for y0, _, _, x0, x1 in lines:
        for y in (y0 - spacing, y0 + spacing):
            if any(abs(o[0] - y) < spacing * 0.3 for o in out) or not 1 <= y < dark.shape[0] - 2:
                continue
            if not any(abs(o[0] - (2 * y0 - y)) < 2 for o in out):  # a neighbour on the other side
                continue
            if dark[int(y) - 1 : int(y) + 2, x0:x1].any(axis=0).mean() >= 0.55:
                out.append((y, int(y), int(y), x0, x1))
    return sorted(out)


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
                    if abs(ys[m] - want) <= max(1.5, step * 0.08)
                    and abs(lines[m][3] - top[3]) <= step
                    and abs(lines[m][4] - top[4]) <= step
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
            and abs(lines[m][3] - lines[edge][3]) <= step
            and abs(lines[m][4] - lines[edge][4]) <= step
        ]
        if near:
            group.append(min(near, key=lambda m: abs(ys[m] - want)))


def _find_staves(gray, cv2, np):
    dark = gray < _DARK
    groups = _staves(_complete(_staff_lines(dark, cv2, np), dark, np))
    spacing = float(np.median([np.median(np.diff([line[0] for line in g])) for g in groups])) if groups else 0.0
    return dark, groups, spacing


def _clean(text: str) -> str:
    """Fret text only: letters the recogniser confuses with digits are mapped back (the model also
    reads Chinese, and a lone round 0 can come out as the ideographic full stop)."""
    text = text.strip().translate(
        str.maketrans({"O": "0", "o": "0", "。": "0", "〇": "0", "○": "0", "l": "1", "I": "1", "|": "1"})
    )
    return "".join(ch for ch in text if ch.isdigit() or ch in "()xX")


def _read_page(gray, number: int) -> Page:
    cv2, np = _cv()
    dark, groups, spacing = _find_staves(gray, cv2, np)
    height, width = gray.shape
    if not groups:
        return Page(number, float(width), float(height), [], [])
    k = _OUTPUT_SPACING / spacing
    segments: list[Segment] = []
    on_line = np.zeros_like(dark)
    # the line's own pixels are its long horizontal runs, so a digit's short stroke
    # crossing the line (the middle of a 2 or a 5) is kept
    run = cv2.getStructuringElement(cv2.MORPH_RECT, (max(8, int(spacing * 0.9)), 1))
    long_runs = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, run).astype(bool)
    for group in groups:
        x0, x1 = min(line[3] for line in group), max(line[4] for line in group)
        for y, a, b, lx0, lx1 in group:
            segments.append(Segment(lx0 * k, lx1 * k, y * k, y * k))
            on_line[a - 1 : b + 2, lx0 : lx1 + 1] |= long_runs[a - 1 : b + 2, lx0 : lx1 + 1]
        top, bottom = group[0][0], group[-1][0]
        ya, yb = round(top), round(bottom)
        # bar lines: thin columns dark over the whole staff height
        xs = np.where(dark[ya : yb + 1, x0:x1].mean(axis=0) >= 0.92)[0]
        for cols in np.split(xs, np.where(np.diff(xs) > 1)[0] + 1) if len(xs) else []:
            if len(cols) <= max(3, spacing * 0.35):
                xc = x0 + float(cols.mean())
                segments.append(Segment(xc * k, xc * k, top * k, bottom * k))
                on_line[ya : yb + 1, x0 + int(cols[0]) : x0 + int(cols[-1]) + 1] = True

    glyph = dark & ~on_line
    count, _, stats, _ = cv2.connectedComponentsWithStats(glyph.astype(np.uint8), connectivity=8)
    line_ys = [line[0] for group in groups for line in group]
    candidates = []  # digit-sized blobs centred on a staff line: (x, y, w, h, line y)
    for x, y, w, h, area in stats[1:count]:
        if area < 4 or not (0.45 * spacing <= h <= 1.25 * spacing and w <= 1.6 * spacing):
            continue
        line_y = min(line_ys, key=lambda ly, yc=y + h / 2: abs(ly - yc))
        if abs(line_y - (y + h / 2)) <= 0.4 * spacing:
            candidates.append((int(x), int(y), int(w), int(h), line_y))
    candidates.sort(key=lambda c: (c[4], c[0]))
    numbers: list[list[tuple[int, int, int, int, float]]] = []  # neighbouring blobs: one number
    for c in candidates:
        last = numbers[-1][-1] if numbers else None
        if last and last[4] == c[4] and c[0] - (last[0] + last[2]) <= 0.35 * spacing:
            numbers[-1].append(c)
        else:
            numbers.append([c])

    boxes, crops = [], []
    pad = int(spacing * 0.4)
    for blobs in numbers:
        gx0, gx1 = min(c[0] for c in blobs), max(c[0] + c[2] for c in blobs)
        gy0, gy1 = min(c[1] for c in blobs), max(c[1] + c[3] for c in blobs)
        pixels = glyph[gy0:gy1, gx0:gx1].copy()
        # where the gap behind the number is a pixel or two, the end of the staff line stays
        # stuck to it: in the line's rows, keep only what lies under the number's own width
        band = slice(max(0, int(blobs[0][4] - 2.5) - gy0), max(0, int(blobs[0][4] + 2.5) + 1 - gy0))
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
        results, _ = _recognizer()(crops)
        for (gx0, gx1, gy0, gy1), (text, _score) in zip(boxes, results, strict=True):
            text = _clean(text)
            step = (gx1 - gx0) / len(text) if text else 0
            for j, ch in enumerate(text):  # one character per digit, the box split evenly
                chars.append(Char(ch, (gx0 + j * step) * k, (gx0 + (j + 1) * step) * k, gy0 * k, gy1 * k))
    return Page(number, width * k, height * k, chars, segments)


def _normalized(render: Callable[[float], object], width: float, height: float, number: int) -> Page:
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
        return Page(number, float(width), float(height), [], [])  # no staff at any size
    factor = _TARGET_SPACING / spacing
    if not 0.85 <= factor <= 1.2:
        better = min(scale * factor, limit)
        if abs(better / scale - 1) > 0.05:
            gray = render(better)
    return _read_page(gray, number)


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


def read_image(data: bytes, max_pixels: int) -> Page:
    """One page from an image upload."""
    cv2, _ = _cv()
    original = decode_image(data, max_pixels)

    def render(scale: float):
        if abs(scale - 1) < 0.01:
            return original
        method = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        return cv2.resize(original, None, fx=scale, fy=scale, interpolation=method)

    return _normalized(render, original.shape[1], original.shape[0], 1)


def read_pdf_page(data: bytes, index: int) -> Page:
    """Page ``index`` (0-based) of a PDF, rendered and read as a picture. Coordinates are in the
    picture's own units (staff spacing 7), not the PDF's points."""
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

        return _normalized(render, width, height, index + 1)
    finally:
        document.close()
