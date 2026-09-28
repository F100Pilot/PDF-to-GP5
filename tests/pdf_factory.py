"""Build small PDF fixtures in memory with reportlab."""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def ascii_tab_pdf(
    systems: list[list[str]], font_size: int = 10, extra_lines: list[str] | None = None, line_spacing: float = 1.15
) -> bytes:
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
            y -= font_size * line_spacing
        y -= font_size * 2 * line_spacing
    pdf.save()
    return buffer.getvalue()


def engraved_tab_pdf(
    staves: list[list[list[tuple[int, int]]]] | list[list[tuple[int, int]]],
    strings: int = 6,
    bar_numbers: list[list[int]] | None = None,
    widths: list[float] | None = None,
    measure_number_noise: int = 0,
) -> bytes:
    """Draw tab staves with vector lines.

    ``staves`` is a list of staves, each a list of measures, each a list of
    (string, fret). A plain list of measures is treated as one staff. Staff
    lines are drawn one segment per measure, right to left, as some editors do.
    """
    if staves and staves[0] and isinstance(staves[0][0], tuple):
        staves = [staves]  # type: ignore[list-item]
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    spacing = 7.0
    x0 = 60.0
    for index, measures in enumerate(staves):
        top = A4[1] - 100 - index * 90
        x1 = x0 + (widths[index] if widths else 480.0)
        width = (x1 - x0) / max(len(measures), 1)
        for m in reversed(range(len(measures))):
            for s in range(strings):
                pdf.line(x0 + m * width, top - s * spacing, x0 + (m + 1) * width, top - s * spacing)
        for m, notes in enumerate(measures):
            start = x0 + m * width
            pdf.line(start, top, start, top - (strings - 1) * spacing)
            if bar_numbers:
                pdf.setFont("Helvetica-Oblique", 5)
                pdf.drawString(start - 2, top + 4, str(bar_numbers[index][m]))
            pdf.setFont("Helvetica", 7)
            step = width / (len(notes) + 1)
            for k, (string, fret) in enumerate(notes):
                y = top - (string - 1) * spacing
                pdf.drawCentredString(start + step * (k + 0.5) + 4, y - 2.5, str(fret))
        pdf.line(x1, top, x1, top - (strings - 1) * spacing)
    # Many small digits elsewhere on the page (e.g. lyrics or bar numbers) must not
    # influence which digits are accepted as frets.
    pdf.setFont("Helvetica", 4)
    for i in range(measure_number_noise):
        pdf.drawString(60 + (i % 40) * 12, 60 + (i // 40) * 10, str(i % 10))
    pdf.save()
    return buffer.getvalue()


def blank_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.rect(100, 100, 200, 200, fill=1)
    pdf.save()
    return buffer.getvalue()
