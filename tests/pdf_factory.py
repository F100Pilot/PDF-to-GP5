"""Build small PDF fixtures in memory with reportlab."""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def engraved_tab_pdf(
    staves: list,
    strings: int = 6,
    bar_numbers: list[list[int]] | None = None,
    widths: list[float] | None = None,
    measure_number_noise: int = 0,
    ranges: list[tuple[int, str, float, float]] | None = None,
    extra_lines: list[str] | None = None,
) -> bytes:
    """Draw tab staves with vector lines.

    ``staves`` is a list of staves, each a list of measures, each a list of
    (string, fret) or (string, fret, flags). A plain list of measures is treated
    as one staff. Flags: "(" draws parentheses as curved paths, "P"/"H" prints
    the letter above the staff between the previous note and this one.
    ``ranges`` are (staff, text, x_from, x_to): text such as "let ring" under the
    staff followed by a dashed line up to x_to. ``extra_lines`` are text lines
    printed above the first staff (title, artist, tempo…). Staff lines are drawn
    one segment per measure, right to left, as some editors do.
    """
    if staves and staves[0] and isinstance(staves[0][0], tuple):
        staves = [staves]  # type: ignore[list-item]
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    spacing = 7.0
    x0 = 60.0
    # At the fret size: with so few notes, bigger digits (a tempo) would shift which size counts as a fret.
    pdf.setFont("Helvetica", 7)
    for i, line in enumerate(extra_lines or []):
        pdf.drawString(x0, A4[1] - 40 - i * 12, line)
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
            for k, (string, fret, *rest) in enumerate(notes):
                flags = rest[0] if rest else ""
                y = top - (string - 1) * spacing
                x = start + step * (k + 0.5) + 4
                pdf.drawCentredString(x, y - 2.5, str(fret))
                if "(" in flags:
                    half = pdf.stringWidth(str(fret), "Helvetica", 7) / 2 + 0.8
                    for side, bulge in ((x - half, -1.2), (x + half, 1.2)):
                        path = pdf.beginPath()
                        path.moveTo(side, y - 3)
                        path.curveTo(side + bulge, y - 1.5, side + bulge, y + 1.5, side, y + 3)
                        path.close()
                        pdf.drawPath(path, stroke=0, fill=1)
                for letter in "HP":
                    if letter in flags:
                        pdf.drawCentredString(x - step / 2, top + 6, letter)
        pdf.line(x1, top, x1, top - (strings - 1) * spacing)
        for staff_index, text, x_from, x_to in ranges or []:
            if staff_index != index:
                continue
            y = top - (strings - 1) * spacing - 20
            pdf.setFont("Helvetica", 6)
            pdf.drawString(x_from, y, text)
            dash = pdf.stringWidth(text, "Helvetica", 6) + x_from + 3
            while dash < x_to:
                pdf.line(dash, y + 2, min(dash + 3, x_to), y + 2)
                dash += 5
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
