"""Text around an engraved tab staff: section names, lyrics and dynamics."""

from __future__ import annotations

import re

from .pdf_reader import Char, Page, TextLine, group_lines
from .rhythm_marks import glyph_ys

_LETTERS = re.compile(r"[A-Za-zÀ-ÿ]{2,}")
_NOT_LYRICS = re.compile(r"^\s*(?:let\s*ring|p\.?\s*m\.?|palm\s*mute)\b", re.IGNORECASE)
_HYPHENS = {"-", "–", "—", "‐"}

# SMuFL dynamics (U+E520 block) and their plain-text spelling.
_DYNAMIC_GLYPHS = {
    "": "ppp",
    "": "ppp",  # pppp
    "": "pp",
    "": "p",
    "": "mp",
    "": "mf",
    "": "f",
    "": "f",  # fp
    "": "ff",
    "": "fff",
    "": "fff",  # ffff
}
# Guitar Pro velocities (PyGuitarPro Velocities: 15 + 16 * step).
VELOCITIES = {"ppp": 15, "pp": 31, "p": 47, "mp": 63, "mf": 79, "f": 95, "ff": 111, "fff": 127}


def _is_music_glyph(char: Char) -> bool:
    return "" <= char.text <= ""


def _phrases(line: TextLine) -> list[list[Char]]:
    """Split a text line where the gap is wider than about one character height."""
    phrases: list[list[Char]] = []
    for char in line.chars:
        height = char.bottom - char.top
        if phrases and char.x0 - phrases[-1][-1].x1 <= height:
            phrases[-1].append(char)
        else:
            phrases.append([char])
    return phrases


def _words(chars: list[Char]) -> list[list[Char]]:
    words: list[list[Char]] = []
    for char in chars:
        if words and char.x0 - words[-1][-1].x1 <= 0.2 * (char.bottom - char.top):
            words[-1].append(char)
        else:
            words.append([char])
    return words


def section_labels(page: Page, top: float, x0: float, x1: float, spacing: float) -> list[tuple[float, str]]:
    """Bold text above the staff ("Intro", "Chorus", "Verse 2")."""
    candidates = [
        c
        for c in page.chars
        if c.bold
        and not _is_music_glyph(c)
        and x0 - spacing <= c.x0 <= x1
        and top - 6 * spacing <= c.yc <= top - 0.3 * spacing
    ]
    labels: list[tuple[float, str]] = []
    for line in group_lines(candidates):
        for phrase in _phrases(line):
            text = " ".join("".join(c.text for c in word) for word in _words(phrase)).strip()
            if _LETTERS.search(text):
                labels.append((phrase[0].x0, text))
    return labels


def lyrics(page: Page, bottom: float, x0: float, x1: float, spacing: float) -> list[tuple[float, str, bool]]:
    """Lyric syllables under the staff as (x, syllable, joins_next).

    ``joins_next`` is True when a hyphen (a character or a short drawn line) links
    the syllable to the next one ("hap-pened").
    """
    chars = [
        c
        for c in page.chars
        if not c.bold
        and not c.italic
        and not _is_music_glyph(c)
        and x0 - spacing <= c.x0 <= x1
        and bottom + 0.5 * spacing <= c.yc <= bottom + 8 * spacing
    ]
    dashes = [s for s in page.segments if s.is_horizontal and (s.x1 - s.x0) <= 1.5 * spacing]
    syllables: list[tuple[float, str, bool]] = []
    for line in group_lines(chars):
        text = "".join(c.text for c in line.chars)
        if _NOT_LYRICS.match(text) or not _LETTERS.search(text):
            continue
        words = [w for w in _words(line.chars) if "".join(c.text for c in w) not in _HYPHENS]
        hyphen_chars = [c for c in line.chars if c.text in _HYPHENS]
        for current, following in zip(words, [*words[1:], None], strict=True):
            joins = False
            if following is not None:
                gap_low, gap_high = current[-1].x1, following[0].x0
                joins = any(gap_low - 1 <= h.x0 and h.x1 <= gap_high + 1 for h in hyphen_chars) or any(
                    gap_low - 1 <= d.x0 and d.x1 <= gap_high + 1 and line.top <= d.top <= line.bottom for d in dashes
                )
            word = "".join(c.text for c in current).strip("-–—‐")
            if word:
                syllables.append((current[0].x0, word, joins))
    return syllables


def dynamics(page: Page, top: float, bottom: float, x0: float, x1: float, spacing: float) -> list[tuple[float, int]]:
    """Dynamic marks (SMuFL glyphs or italic/bold letters) near the staff as (x, velocity)."""
    marks: list[tuple[float, int]] = []
    for char in page.chars:
        name = _DYNAMIC_GLYPHS.get(char.text)
        # Music-font box sits about one em below the glyph: use the corrected position only,
        # so a mark between two staves is not claimed by both.
        drawn_y = glyph_ys(char)[1]
        if name and x0 - spacing <= char.xc <= x1 and top - 3 * spacing <= drawn_y <= bottom + 5 * spacing:
            marks.append((char.x0, VELOCITIES[name]))
    text_chars = [
        c
        for c in page.chars
        if (c.italic or c.bold)
        and c.text in "pmf"
        and x0 - spacing <= c.x0 <= x1
        and top - 3 * spacing <= c.yc <= bottom + 6 * spacing
    ]
    for line in group_lines(text_chars):
        for word in _words(line.chars):
            token = "".join(c.text for c in word)
            if token in VELOCITIES and _standalone(page, word):
                marks.append((word[0].x0, VELOCITIES[token]))
    return sorted(marks)


def _standalone(page: Page, word: list[Char]) -> bool:
    """No other letters touching the word on the same line (so "f" in "of" does not count)."""
    height = word[0].bottom - word[0].top
    return not any(
        c not in word
        and c.text.isalpha()
        and abs(c.yc - word[0].yc) < 0.3 * height
        and (0 <= word[0].x0 - c.x1 < 0.3 * height or 0 <= c.x0 - word[-1].x1 < 0.3 * height)
        for c in page.chars
    )
