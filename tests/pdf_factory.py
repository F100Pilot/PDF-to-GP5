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
    staves: list,
    strings: int = 6,
    bar_numbers: list[list[int]] | None = None,
    widths: list[float] | None = None,
    measure_number_noise: int = 0,
    ranges: list[tuple[int, str, float, float]] | None = None,
    knockout: bool = False,
) -> bytes:
    """Draw tab staves with vector lines.

    ``staves`` is a list of staves, each a list of measures, each a list of
    (string, fret) or (string, fret, flags). A plain list of measures is treated
    as one staff. Flags: "(" draws parentheses as curved paths, "P"/"H" prints
    the letter above the staff between the previous note and this one.
    ``ranges`` are (staff, text, x_from, x_to): text such as "let ring" under the
    staff followed by a dashed line up to x_to. Staff lines are drawn one
    segment per measure, right to left, as some editors do. ``knockout`` blanks
    the line behind each number, as editors do on screen and in print.
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
            for k, (string, fret, *rest) in enumerate(notes):
                flags = rest[0] if rest else ""
                y = top - (string - 1) * spacing
                x = start + step * (k + 0.5) + 4
                if knockout:
                    half = pdf.stringWidth(str(fret), "Helvetica", 7) / 2 + 0.6
                    pdf.setFillColorRGB(1, 1, 1)
                    pdf.rect(x - half, y - 3, 2 * half, 6, stroke=0, fill=1)
                    pdf.setFillColorRGB(0, 0, 0)
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


def tab_png(pdf: bytes, width: int = 1300, image_format: str = "PNG") -> bytes:
    """Page 1 of ``pdf`` as a picture, like a screenshot of the tab."""
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf)
    page = document[0]
    image = page.render(scale=width / page.get_size()[0]).to_pil().convert("RGB")
    document.close()
    buffer = io.BytesIO()
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def image_pdf(pictures: list[bytes]) -> bytes:
    """A PDF whose pages are only pictures (no text): a scan, or a web page printed to PDF."""
    from reportlab.lib.utils import ImageReader

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for picture in pictures:
        pdf.drawImage(ImageReader(io.BytesIO(picture)), 0, 0, *A4)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()
