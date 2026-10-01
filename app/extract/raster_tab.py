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


def _read_page(gray, number: int, heading: bool = False) -> tuple[Page, Page | None]:
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
    page = Page(number, width * k, height * k, chars, segments)
    return page, (_heading(gray, groups, spacing, k, number) if heading else None)


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
    two characters the recogniser placed on either side of it — never inside a number."""
    columns = [col for word in info[2] for col in word]
    ink = crop < 160
    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    if len(columns) != len(text) or len(rows) < 2 or len(cols) < 2:
        return text
    height = rows[-1] - rows[0] + 1
    gaps = [(a + b) / 2 for a, b in itertools.pairwise(cols) if b - a - 1 > 0.25 * height]
    xs = [col / max(info[0], 1) * crop.shape[1] for col in columns]  # each character's x in the crop
    cuts = set()
    for gap in gaps:
        cut = next((i for i in range(1, len(text)) if xs[i - 1] < gap < xs[i]), None)
        if cut and " " not in text[cut - 1 : cut + 1] and not (text[cut - 1].isdigit() and text[cut].isdigit()):
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
    render: Callable[[float], object], width: float, height: float, number: int, heading: bool
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
    return _read_page(gray, number, heading)


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


def read_image(data: bytes, max_pixels: int) -> tuple[Page, Page | None]:
    """The tab page of an image upload, and the text above its first staff (see ``_heading``)."""
    cv2, _ = _cv()
    original = decode_image(data, max_pixels)

    def render(scale: float):
        if abs(scale - 1) < 0.01:
            return original
        method = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        return cv2.resize(original, None, fx=scale, fy=scale, interpolation=method)

    return _normalized(render, original.shape[1], original.shape[0], 1, heading=True)


def read_pdf_page(data: bytes, index: int, heading: bool = False) -> tuple[Page, Page | None]:
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

        return _normalized(render, width, height, index + 1, heading)
    finally:
        document.close()
