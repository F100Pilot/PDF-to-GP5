"""Read rhythm notation drawn with engraved tablature ("tab with stems").

Editors such as MuseScore and Guitar Pro can print rhythm under (or over)
the tab staff: one stem per beat, beams/flags for 8ths and shorter, dots,
shorter stems for half notes, and rest symbols. Rests, flags and dots use
SMuFL music-font glyphs.
"""

from __future__ import annotations

from collections import Counter
from statistics import median

from ..model import RhythmMark
from .pdf_reader import Char, Page, Segment

# SMuFL code points (https://w3c.github.io/smufl/latest/) mapped to 32nd-note units.
REST_UNITS = {"": 32, "": 16, "": 8, "": 4, "": 2, "": 1}
FLAG_UNITS = {"": 4, "": 4, "": 2, "": 2, "": 1, "": 1}
AUGMENTATION_DOT = ""
BEAM_UNITS = {1: 4, 2: 2, 3: 1}
_DOTTED = {1: None, 2: 3, 4: 6, 8: 12, 16: 24, 32: 48}


def glyph_ys(char: Char) -> tuple[float, float]:
    """Plausible vertical centres of a music-font glyph.

    Text extraction reports the font's full em box, and music fonts draw far
    above their baseline, so the box can sit about one em below the symbol.
    Both the box centre and the corrected position are tried.
    """
    size = char.bottom - char.top
    return char.yc, char.top - 0.9 * size


def _near(char: Char, y: float, tolerance: float) -> bool:
    return any(abs(candidate - y) <= tolerance for candidate in glyph_ys(char))


def _stems(page: Page, top: float, bottom: float, x0: float, x1: float, spacing: float) -> list[Segment]:
    """Stems below the staff (or above it, if that side has more), all ending on one line.

    Half-note stems are shorter but share the far end with the others; requiring
    that common end keeps out unrelated ticks (e.g. the end of a "P.M." line).
    """

    def candidates(below: bool) -> list[Segment]:
        found = []
        for seg in page.segments:
            length = seg.bottom - seg.top
            if not seg.is_vertical or not (x0 < seg.x0 < x1) or not (0.5 * spacing <= length <= 4 * spacing):
                continue
            near = seg.top - bottom if below else top - seg.bottom
            if 0.1 * spacing <= near <= 3 * spacing:
                found.append(seg)
        if not found:
            return []
        ends = Counter(round((s.bottom if below else s.top) / (0.25 * spacing)) for s in found)
        common = ends.most_common(1)[0][0] * 0.25 * spacing
        return [s for s in found if abs((s.bottom if below else s.top) - common) <= 0.3 * spacing]

    below, above = candidates(True), candidates(False)
    return below if len(below) >= len(above) else above


def _beam_shapes(page: Page, spacing: float) -> list[Segment]:
    shapes = [*page.curves, *page.segments]
    return [
        s for s in shapes if 0.15 * spacing <= (s.bottom - s.top) <= 0.45 * spacing and (s.x1 - s.x0) >= 0.5 * spacing
    ]


TRIPLET_DIGITS = ("3", "6")  # 3 in the time of 2, 6 in the time of 4: both 2/3


def _overlaps(char: Char, low: float, high: float) -> bool:
    return char.bottom >= low and char.top <= high


def _tuplet_span(page: Page, digit: Char, spacing: float) -> tuple[float, float] | None:
    """The x span of a triplet / sextuplet bracket: a "3" or "6" between two horizontal strokes
    (the bracket's arms); None for other numbers or an unbracketed digit."""
    if digit.text not in TRIPLET_DIGITS:
        return None
    arms = [s for s in page.segments if s.is_horizontal and abs((s.top + s.bottom) / 2 - digit.yc) <= 0.6 * spacing]
    left = [s for s in arms if digit.x0 - spacing <= s.x1 <= digit.x0 + 1 and s.x1 - s.x0 <= 8 * spacing]
    right = [s for s in arms if digit.x1 - 1 <= s.x0 <= digit.x1 + spacing and s.x1 - s.x0 <= 8 * spacing]
    if not left or not right:
        return None
    return min(s.x0 for s in left), max(s.x1 for s in right)


def _dot_candidates(page: Page, spacing: float) -> tuple[list[Char], list[Segment]]:
    """Dot glyphs and small filled shapes, filtered once per staff (not once per stem)."""
    glyphs = [c for c in page.chars if c.text == AUGMENTATION_DOT]
    shapes = [
        s
        for s in page.curves
        if 0.1 * spacing <= s.x1 - s.x0 <= 0.35 * spacing and 0.1 * spacing <= s.bottom - s.top <= 0.35 * spacing
    ]
    return glyphs, shapes


def _has_dot(x: float, low: float, high: float, dots: tuple[list[Char], list[Segment]], spacing: float) -> bool:
    """Augmentation dot just right of a stem or rest (glyph or small filled shape)."""
    glyphs, shapes = dots
    for char in glyphs:
        beside = x < char.x0 <= x + 1.5 * spacing
        if beside and any(low - spacing <= y <= high + spacing for y in glyph_ys(char)):
            return True
    for shape in shapes:
        beside = (
            x < shape.x0 <= x + 1.2 * spacing
            and low - 0.6 * spacing <= (shape.top + shape.bottom) / 2 <= high + 0.6 * spacing
        )
        if beside:
            return True
    return False


def _apply_dot(units: int | None, dotted: bool) -> int | None:
    if not dotted or units is None:
        return units
    return _DOTTED.get(units)


def read_rhythm(page: Page, top: float, bottom: float, x0: float, x1: float, spacing: float) -> list[RhythmMark]:
    """Rhythm marks for one tab staff, or [] when the staff has no stems."""
    stems = _stems(page, top, bottom, x0, x1, spacing)
    if not stems:
        return []
    below = stems[0].top > bottom
    typical = median(s.bottom - s.top for s in stems)
    beams = _beam_shapes(page, spacing)
    flag_chars = [c for c in page.chars if c.text in FLAG_UNITS]
    dots = _dot_candidates(page, spacing)
    zone_low = min(s.top for s in stems)
    zone_high = max(s.bottom for s in stems)
    # Tuplet numbers sit just beyond the beams. A bracketed "3" / "6" spans a triplet / sextuplet
    # (2/3 of the written lengths); any other digit there makes durations unreliable.
    tuplet_digits = [
        c
        for c in page.chars
        if c.text.isdigit()
        and x0 < c.xc < x1
        and (
            _overlaps(c, zone_high, zone_high + 1.2 * spacing)
            if below
            else _overlaps(c, zone_low - 1.2 * spacing, zone_low)
        )
    ]
    spans = [span for c in tuplet_digits if (span := _tuplet_span(page, c, spacing)) is not None]
    tuplet_xs = [c.xc for c in tuplet_digits if _tuplet_span(page, c, spacing) is None]

    def in_triplet(x: float) -> bool:
        return any(a - 0.3 * spacing <= x <= b + 0.3 * spacing for a, b in spans)

    marks: list[RhythmMark] = []
    for stem in stems:
        x = (stem.x0 + stem.x1) / 2
        end = stem.bottom if below else stem.top
        covering = {
            round(b.top)
            for b in beams
            if b.x0 - 2 <= x <= b.x1 + 2
            and b.bottom >= stem.top - 0.2 * spacing
            and b.top <= stem.bottom + 0.2 * spacing
        }
        if covering:
            units: int | None = BEAM_UNITS.get(len(covering))
        else:
            flags = [
                FLAG_UNITS[c.text]
                for c in flag_chars
                if -0.5 * spacing <= c.x0 - x <= 1.0 * spacing and _near(c, end, 1.5 * spacing)
            ]
            if flags:
                units = min(flags)
            else:
                units = 16 if (stem.bottom - stem.top) <= 0.7 * typical else 8
        units = _apply_dot(units, _has_dot(x, stem.top, stem.bottom, dots, spacing))
        if any(abs(t - x) <= 1.5 * spacing for t in tuplet_xs):
            units = None
        marks.append(RhythmMark(x=x, units=units, tuplet=in_triplet(x)))

    staff_center = (top + bottom) / 2
    for char in page.chars:
        if char.text not in REST_UNITS or not (x0 < char.xc < x1):
            continue
        if not _near(char, staff_center, 4 * spacing):
            continue
        rest_ys = glyph_ys(char)
        dotted = _has_dot(char.x1, min(rest_ys) - spacing, max(rest_ys) + spacing, dots, spacing)
        units = _apply_dot(REST_UNITS[char.text], dotted)
        marks.append(RhythmMark(x=char.xc, units=units, is_rest=True, tuplet=in_triplet(char.xc)))
    return sorted(marks, key=lambda m: m.x)
