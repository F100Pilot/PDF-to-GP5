"""Build small PDF fixtures in memory with reportlab."""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def ascii_tab_pdf(systems: list[list[str]], font_size: int = 10, extra_lines: list[str] | None = None) -> bytes:
    """Render tab systems as monospaced text lines (like a printed .txt tab)."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFont("Courier", font_size)
    y = A4[1] - 60
    for line in extra_lines or []:
        pdf.drawString(40, y, line)
        y -= font_size * 2
    for system in systems:
        for line in system:
            pdf.drawString(40, y, line)
            y -= font_size * 1.15
        y -= font_size * 2
    pdf.save()
    return buffer.getvalue()


def engraved_tab_pdf(measures: list[list[tuple[int, int]]], strings: int = 6) -> bytes:
    """Draw a tab staff with vector lines; each measure is a list of (string, fret)."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    spacing = 7.0
    top = A4[1] - 100
    x0, x1 = 60.0, 540.0
    for s in range(strings):
        pdf.line(x0, top - s * spacing, x1, top - s * spacing)
    width = (x1 - x0) / len(measures)
    pdf.setFont("Helvetica", 7)
    for m, notes in enumerate(measures):
        start = x0 + m * width
        pdf.line(start, top, start, top - (strings - 1) * spacing)
        step = width / (len(notes) + 1)
        for k, (string, fret) in enumerate(notes):
            y = top - (string - 1) * spacing
            pdf.drawCentredString(start + step * (k + 0.5) + 4, y - 2.5, str(fret))
    pdf.line(x1, top, x1, top - (strings - 1) * spacing)
    pdf.save()
    return buffer.getvalue()


def blank_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.rect(100, 100, 200, 200, fill=1)
    pdf.save()
    return buffer.getvalue()
