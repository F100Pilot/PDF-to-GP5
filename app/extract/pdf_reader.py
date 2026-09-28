"""Low-level PDF access: positioned characters and line segments per page."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pdfplumber

# Typographic dashes some PDF generators substitute for ASCII hyphens.
_DASHES = {"‐", "‑", "‒", "–", "—", "―", "−", "─"}


@dataclass(frozen=True)
class Char:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    font: str = ""  # font name without the subset prefix, e.g. "Edwin-Bold"

    @property
    def bold(self) -> bool:
        return "bold" in self.font.lower()

    @property
    def italic(self) -> bool:
        name = self.font.lower()
        return "italic" in name or "oblique" in name

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(frozen=True)
class Segment:
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def is_horizontal(self) -> bool:
        return (self.bottom - self.top) <= 1.5 and (self.x1 - self.x0) > 3 * (self.bottom - self.top + 0.1)

    @property
    def is_vertical(self) -> bool:
        return (self.x1 - self.x0) <= 1.5 and (self.bottom - self.top) > 3 * (self.x1 - self.x0 + 0.1)


@dataclass
class TextLine:
    chars: list[Char]

    @property
    def text(self) -> str:
        return "".join(c.text for c in self.chars)

    @property
    def top(self) -> float:
        return min(c.top for c in self.chars)

    @property
    def bottom(self) -> float:
        return max(c.bottom for c in self.chars)

    @property
    def yc(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass
class Page:
    number: int
    width: float
    height: float
    chars: list[Char]
    segments: list[Segment]
    curves: list[Segment] = field(default_factory=list)  # bounding boxes of curved paths


class PdfReadError(Exception):
    """Raised when the PDF cannot be opened or exceeds processing limits."""


def _normalize(text: str) -> str:
    return "-" if text in _DASHES else text


def read_pages(data: bytes, max_pages: int) -> list[Page]:
    """Load positioned characters and line segments from every page."""
    return read_document(data, max_pages)[0]


# Values PDF producers write when the author left the field empty.
_PLACEHOLDERS = {"untitled", "anonymous", "unknown", "author", "title", "user", "admin", "none"}
_GENERATOR_PREFIX = re.compile(r"^\s*microsoft\s+(?:word|excel|powerpoint)\s*-\s*", re.IGNORECASE)


def _document_info(metadata: dict) -> dict[str, str]:
    """Keep only short plain-text Title/Author entries from the PDF info dictionary."""
    info: dict[str, str] = {}
    for key in ("Title", "Author"):
        value = metadata.get(key)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="ignore")
        if not isinstance(value, str):
            continue
        value = _GENERATOR_PREFIX.sub("", value).strip()
        if value and value.lower() not in _PLACEHOLDERS:
            info[key] = value[:200]
    return info


def read_document(data: bytes, max_pages: int) -> tuple[list[Page], dict[str, str]]:
    """Pages plus the document's Title/Author metadata (if any)."""
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # pdfminer raises many unrelated exception types
        raise PdfReadError("O ficheiro não é um PDF válido ou está corrompido.") from exc
    pages: list[Page] = []
    with pdf:
        info = _document_info(pdf.metadata or {})
        if len(pdf.pages) > max_pages:
            raise PdfReadError(f"O PDF tem {len(pdf.pages)} páginas; o máximo é {max_pages}.")
        for index, page in enumerate(pdf.pages, start=1):
            chars = [
                Char(
                    _normalize(c["text"]),
                    float(c["x0"]),
                    float(c["x1"]),
                    float(c["top"]),
                    float(c["bottom"]),
                    str(c.get("fontname", "")).split("+")[-1],
                )
                for c in page.chars
                if c.get("text") and not c["text"].isspace()
            ]
            segments = [
                Segment(float(o["x0"]), float(o["x1"]), float(o["top"]), float(o["bottom"]))
                for o in (*page.lines, *page.rects)
            ]
            curves = [Segment(float(o["x0"]), float(o["x1"]), float(o["top"]), float(o["bottom"])) for o in page.curves]
            pages.append(Page(index, float(page.width), float(page.height), chars, segments, curves))
    return pages, info


def group_lines(chars: list[Char]) -> list[TextLine]:
    """Group characters into text lines by vertical overlap, ordered top to bottom."""
    lines: list[list[Char]] = []
    for char in sorted(chars, key=lambda c: (c.yc, c.x0)):
        if lines:
            last = lines[-1]
            ref = last[0]
            tolerance = max(0.35 * (ref.bottom - ref.top), 1.0)
            if abs(char.yc - ref.yc) <= tolerance:
                last.append(char)
                continue
        lines.append([char])
    return [TextLine(sorted(line, key=lambda c: c.x0)) for line in lines]
