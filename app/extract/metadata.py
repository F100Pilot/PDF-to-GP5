"""Detect song title, artist, tempo and time signature from the first page."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from .pdf_reader import Char, Page, TextLine, group_lines

# SMuFL metronome note glyphs -> tempo factor relative to a quarter note.
_METRONOME_NOTES = {
    "": 2.0,  # half note up
    "": 2.0,
    "": 1.0,  # quarter note up
    "": 1.0,
    "": 0.5,  # eighth note up
    "": 0.5,
    "": 1.0,  # noteQuarterUp
    "♩": 1.0,  # ♩
}
_METRONOME_DOT = ""
TIME_SIGNATURE_DIGITS = {chr(0xE080 + d): d for d in range(10)}
COMMON_TIME, CUT_TIME = "", ""

_TEMPO_PATTERNS = [
    re.compile(r"(?P<note>[-♩])\s*(?P<dot>[.]?)\s*=\s*(?P<bpm>\d{2,3})\b"),
    re.compile(r"^\W*=\s*(?P<bpm>\d{2,3})\b"),
    re.compile(r"\b(?:tempo|bpm)\s*[:=]?\s*(?P<bpm>\d{2,3})\b", re.IGNORECASE),
    re.compile(r"\b(?P<bpm>\d{2,3})\s*bpm\b", re.IGNORECASE),
]
_LABELLED = {
    "title": re.compile(r"^\s*(?:title|song|t[ií]tulo|m[uú]sica)\s*[:\-]\s*(?P<v>.+)$", re.IGNORECASE),
    "artist": re.compile(r"^\s*(?:artist|artista|band|banda|performed by)\s*[:\-]\s*(?P<v>.+)$", re.IGNORECASE),
}
_CREDIT = re.compile(r"^\s*(?:words\s*(?:and|&)\s*music\s+by|music\s+by|by|por)\s+(?P<v>.+)$", re.IGNORECASE)
_NOT_ARTIST = re.compile(r"tuning|afina|tempo|capo|words\s+by|arranged|transcri|page|p[aá]gina|=|:", re.IGNORECASE)
MIN_BPM, MAX_BPM = 20, 400


@dataclass(frozen=True)
class SongMetadata:
    title: str | None = None
    artist: str | None = None
    tempo: int | None = None
    numerator: int | None = None
    denominator: int | None = None
    tuning_labels: tuple[str, ...] = ()  # string 1 (highest) first


def line_text(line: TextLine) -> str:
    """Line text with spaces restored from horizontal gaps (PDFs rarely store them)."""
    out: list[str] = []
    prev: Char | None = None
    for char in line.chars:
        if prev is not None and char.x0 - prev.x1 > 0.2 * (char.bottom - char.top):
            out.append(" ")
        out.append(char.text)
        prev = char
    return "".join(out).strip()


def _is_music_glyph(text: str) -> bool:
    return any("" <= ch <= "" or ch == "♩" for ch in text)


def tempo_from_text(text: str) -> int | None:
    """BPM of a tempo mark ("♩ = 90", "= 90", "Tempo 90", "90 bpm"), or None."""
    return _detect_tempo([text])


def _detect_tempo(texts: list[str]) -> int | None:
    for text in texts:
        for pattern in _TEMPO_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            bpm = float(match.group("bpm"))
            groups = match.groupdict()
            if groups.get("note"):
                bpm *= _METRONOME_NOTES[groups["note"]] * (1.5 if groups.get("dot") else 1.0)
            if MIN_BPM <= bpm <= MAX_BPM:
                return round(bpm)
    return None


def _detect_time_signature(page: Page) -> tuple[int, int] | None:
    """First stacked pair of SMuFL time-signature glyphs (or common/cut time)."""
    glyphs = sorted((c for c in page.chars if c.text in TIME_SIGNATURE_DIGITS), key=lambda c: (c.x0, c.top))
    for special in page.chars:
        if special.text == COMMON_TIME and (not glyphs or special.x0 < glyphs[0].x0):
            return 4, 4
        if special.text == CUT_TIME and (not glyphs or special.x0 < glyphs[0].x0):
            return 2, 2
    if not glyphs:
        return None
    first = glyphs[0]
    width = first.x1 - first.x0
    cluster = [c for c in glyphs if first.x0 - width <= c.x0 <= first.x1 + width]
    tops = sorted({round(c.top) for c in cluster})
    if len(tops) != 2:
        return None
    rows = [sorted((c for c in cluster if round(c.top) == t), key=lambda c: c.x0) for t in tops]
    numerator, denominator = (int("".join(str(TIME_SIGNATURE_DIGITS[c.text]) for c in row)) for row in rows)
    if 1 <= numerator <= 16 and denominator in (2, 4, 8, 16):
        return numerator, denominator
    return None


_TUNING_LINE = re.compile(r"^\s*(?:tuning|afina[cç][aã]o)\s*[:\-]?\s*(?P<v>.+)$", re.IGNORECASE)
_NOTE_TOKEN = re.compile(r"^[A-Ga-g](?:#|b|♯|♭)?$")


def _detect_tuning(texts: list[str]) -> tuple[str, ...]:
    """Labels (string 1 first) from a line like "Tuning: E A D G B E" (written low to high)
    or a named tuning ("Tuning: Drop D")."""
    from ..tunings import TUNING_NAMES, TUNINGS

    names = {k: _NOTE_NAMES_OF(TUNINGS[v]) for k, v in TUNING_NAMES.items()}
    for text in texts:
        match = _TUNING_LINE.match(text)
        if not match:
            continue
        value = match.group("v").strip().lower().rstrip(".")
        if value in names:
            return names[value]
        tokens = [t.replace("♯", "#").replace("♭", "b") for t in re.split(r"[\s,\-–]+", match.group("v").strip()) if t]
        if 4 <= len(tokens) <= 7 and all(_NOTE_TOKEN.match(t) for t in tokens):
            return tuple(t[0].upper() + t[1:] for t in reversed(tokens))
    return ()


def _NOTE_NAMES_OF(midi: tuple[int, ...]) -> tuple[str, ...]:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return tuple(names[m % 12] for m in midi)


def _visual_title_artist(page: Page, lines: list[TextLine]) -> tuple[str | None, str | None]:
    """Largest text near the top is the title; the next credit-like line is the artist."""
    top_area = [line for line in lines if line.top < 0.3 * page.height]
    candidates = [
        line for line in top_area if re.search(r"[A-Za-zÀ-ÿ]{2,}", line_text(line)) and not _is_music_glyph(line.text)
    ]
    if not candidates:
        return None, None
    heights = [line.bottom - line.top for line in lines]
    title_line = max(candidates, key=lambda line: line.bottom - line.top)
    if (title_line.bottom - title_line.top) < 1.3 * median(heights):
        return None, None  # uniform font: no visual hierarchy to rely on
    artist = None
    for line in candidates:
        if line.top <= title_line.top:
            continue
        text = line_text(line)
        credit = _CREDIT.match(text)
        if credit:
            artist = credit.group("v").strip()
            break
        if artist is None and not _NOT_ARTIST.search(text):
            artist = text
    return line_text(title_line), artist


def detect_metadata(pages: list[Page], info: dict[str, str] | None = None) -> SongMetadata:
    if not pages:
        return SongMetadata()
    page = pages[0]
    lines = group_lines(page.chars)
    texts = [line_text(line) for line in lines]

    labelled: dict[str, str] = {}
    for text in texts:
        for key, pattern in _LABELLED.items():
            match = pattern.match(text)
            if match and key not in labelled:
                labelled[key] = match.group("v").strip()

    visual_title, visual_artist = _visual_title_artist(page, lines)
    info = info or {}
    title = labelled.get("title") or visual_title or info.get("Title")
    artist = labelled.get("artist") or visual_artist or info.get("Author")
    signature = _detect_time_signature(page)
    return SongMetadata(
        tuning_labels=_detect_tuning(texts),
        title=title[:100] if title else None,
        artist=artist[:100] if artist else None,
        tempo=_detect_tempo(texts),
        numerator=signature[0] if signature else None,
        denominator=signature[1] if signature else None,
    )


_PART_NAME = re.compile(
    r"\b(?:(?:electric|acoustic|classical|lead|rhythm|solo|clean|distortion)\s+)?"
    r"(?:guitar|bass|guitarra|baixo|viol[aã]o|ukulele|banjo)(?:\s*\d+)?\b",
    re.IGNORECASE,
)


def detect_part_name(pages: list[Page], metadata: SongMetadata) -> str | None:
    """Instrument/part label printed near the top of page 1 (e.g. "Electric Guitar", "Bass")."""
    if not pages:
        return None
    page = pages[0]
    for line in group_lines(page.chars):
        if line.top > 0.3 * page.height:
            break
        text = line_text(line)
        if text in (metadata.title, metadata.artist) or len(text) > 40:
            continue
        match = _PART_NAME.search(text)
        if match:
            return match.group(0).strip().title()
    return None


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def track_name_from_filename(filename: str, title: str | None, artist: str | None) -> str | None:
    """Part name from a file like "Artist - Song - Bass.pdf": what remains after removing song/artist."""
    stem = re.sub(r"\.pdf$", "", filename.replace("\\", "/").rsplit("/", 1)[-1], flags=re.IGNORECASE)
    stem = stem.replace("_", " ")
    known = {_normalize(value) for value in (title, artist) if value}
    parts = [p.strip() for p in re.split(r"\s+-\s+|\s*[–—]\s*", stem) if p.strip()]
    remaining = [p for p in parts if _normalize(p) not in known]
    return " - ".join(remaining)[:40] or None
