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
    heading: tuple[str, str, int] | None = None,
    signatures: list[tuple[int, int, int, int]] | None = None,
    gap: float = 0.6,
) -> bytes:
    """Draw tab staves with vector lines.

    ``staves`` is a list of staves, each a list of measures, each a list of
    (string, fret) or (string, fret, flags). A plain list of measures is treated
    as one staff. Flags: "(" draws parentheses as curved paths, "P"/"H" prints
    the letter above the staff between the previous note and this one.
    ``ranges`` are (staff, text, x_from, x_to): text such as "let ring" under the
    staff followed by a dashed line up to x_to. Staff lines are drawn one
    segment per measure, right to left, as some editors do. ``knockout`` blanks
    the line behind each number, as editors do on screen and in print, ``gap`` points
    beyond the digits on each side.
    ``heading`` is (title, artist, BPM): title and artist centred at the top and
    a tempo mark (a drawn quarter note, "= BPM") above the first staff.
    ``signatures`` are (staff, measure, numerator, denominator): a time signature
    in big bold digits at the start of that measure, the staff lines through them.
    """
    if staves and staves[0] and isinstance(staves[0][0], tuple):
        staves = [staves]  # type: ignore[list-item]
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    spacing = 7.0
    x0 = 60.0
    if heading:
        title, artist, bpm = heading
        pdf.setFont("Helvetica", 22)
        pdf.drawCentredString(A4[0] / 2, A4[1] - 45, title)
        pdf.setFont("Helvetica", 12)
        pdf.drawCentredString(A4[0] / 2, A4[1] - 63, artist)
        pdf.ellipse(x0, A4[1] - 88, x0 + 4.5, A4[1] - 84.5, stroke=0, fill=1)  # quarter note head
        pdf.line(x0 + 4.2, A4[1] - 86, x0 + 4.2, A4[1] - 76)  # and stem
        pdf.setFont("Helvetica", 9)
        pdf.drawString(x0 + 8, A4[1] - 88, f"= {bpm}")
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
                if knockout:  # the gap also takes the parentheses, as editors draw them
                    half = pdf.stringWidth(str(fret), "Helvetica", 7) / 2 + (2.4 if "(" in flags else gap)
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
        middle = top - (strings - 1) * spacing / 2
        for staff_index, measure, numerator, denominator in signatures or []:
            if staff_index == index:
                pdf.setFont("Helvetica-Bold", 19)
                x = x0 + measure * width + 10
                pdf.drawCentredString(x, middle + 0.5, str(numerator))
                pdf.drawCentredString(x, middle - 14.5, str(denominator))
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


def rhythm_tab_pdf(measures: list[list[tuple]], strings: int = 6) -> bytes:
    """One tab staff with rhythm drawn under it, as MuseScore prints "tab with stems".

    Each measure is a list of ("4" | "8" | "8." | "16", string, fret) notes and ("r2",) half
    rests, one slot each. Stems start 2/3 of a space under the staff and end 2.54 spaces under
    it; 8ths and 16ths next to each other are beamed (a lone 16th gets a partial beam towards
    the note before it); a dotted note has its dot right of the stem; a half rest is a block
    sitting on the middle line.
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    spacing, x0, x1, top = 7.0, 60.0, 540.0, A4[1] - 120
    bottom = top - (strings - 1) * spacing
    stem_top, stem_end = bottom - 0.67 * spacing, bottom - 2.54 * spacing
    beam = 0.35 * spacing
    width = (x1 - x0) / len(measures)
    for s in range(strings):
        pdf.line(x0, top - s * spacing, x1, top - s * spacing)
    for m in range(len(measures) + 1):
        pdf.line(x0 + m * width, top, x0 + m * width, bottom)
    for m, items in enumerate(measures):
        step = width / (len(items) + 1)
        xs = [x0 + m * width + step * (k + 0.5) + 4 for k in range(len(items))]
        group: list[int] = []  # beamed notes in a row
        for k, item in enumerate(items + [("end",)]):
            beamed = item[0] in ("8", "8.", "16")
            if not beamed and len(group) >= 2:
                pdf.rect(xs[group[0]], stem_end, xs[group[-1]] - xs[group[0]], beam, stroke=0, fill=1)
                for i, j in enumerate(group):
                    if items[j][0] != "16":
                        continue
                    nxt = i + 1 < len(group) and items[group[i + 1]][0] == "16"
                    prev = i > 0 and items[group[i - 1]][0] == "16"
                    if nxt:
                        pdf.rect(xs[j], stem_end + 2 * beam, xs[group[i + 1]] - xs[j], beam, stroke=0, fill=1)
                    elif not prev:
                        pdf.rect(xs[j] - 1.2 * spacing, stem_end + 2 * beam, 1.2 * spacing, beam, stroke=0, fill=1)
            group = group + [k] if beamed else []
            if item[0] == "end":
                break
            if item[0] == "r2":
                middle = top - (strings // 2 - 1) * spacing
                pdf.rect(xs[k] - 0.45 * spacing, middle, 0.9 * spacing, 0.42 * spacing, stroke=0, fill=1)
                continue
            duration, string, fret = item
            y = top - (string - 1) * spacing
            pdf.setFillColorRGB(1, 1, 1)
            half = pdf.stringWidth(str(fret), "Helvetica", 7) / 2 + 0.6
            pdf.rect(xs[k] - half, y - 3, 2 * half, 6, stroke=0, fill=1)
            pdf.setFillColorRGB(0, 0, 0)
            pdf.setFont("Helvetica", 7)
            pdf.drawCentredString(xs[k], y - 2.5, str(fret))
            pdf.setLineWidth(0.6)
            pdf.line(xs[k], stem_top, xs[k], stem_end)
            pdf.setLineWidth(1)
            if duration.endswith("."):
                pdf.circle(xs[k] + 0.5 * spacing, (stem_top + stem_end) / 2, 0.15 * spacing, stroke=0, fill=1)
    pdf.save()
    return buffer.getvalue()


def labelled_tab_pdf(labels: list[str]) -> bytes:
    """One tab staff with the strings' notes written left of it (as Songsterr prints the tuning),
    the lines starting just after them, and a few frets."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    spacing, x0, x1, top = 7.0, 70.0, 540.0, A4[1] - 120
    for index, label in enumerate(labels):
        y = top - index * spacing
        pdf.line(x0, y, x1, y)
        pdf.setFont("Helvetica", 6)
        pdf.drawRightString(x0 - 4, y - 2.1, label)
    pdf.line(x1, top, x1, top - (len(labels) - 1) * spacing)
    pdf.setFont("Helvetica", 7)
    for k, (string, fret) in enumerate([(1, 0), (3, 2), (5, 3), (6, 5)]):
        x, y = x0 + 40 + 60 * k, top - (string - 1) * spacing
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(x - 3, y - 3, 6, 6, stroke=0, fill=1)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.drawCentredString(x, y - 2.5, str(fret))
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


def image_pdf(pictures: list[bytes], text: tuple[str, str] | None = None) -> bytes:
    """A PDF whose pages are only pictures: a scan, or a web page printed to PDF. ``text`` is a
    title and artist written as text over page 1, as a printed web page has them."""
    from reportlab.lib.utils import ImageReader

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for number, picture in enumerate(pictures):
        pdf.drawImage(ImageReader(io.BytesIO(picture)), 0, 0, *A4)
        if text and number == 0:
            pdf.setFont("Helvetica", 22)
            pdf.drawCentredString(A4[0] / 2, A4[1] - 45, text[0])
            pdf.setFont("Helvetica", 12)
            pdf.drawCentredString(A4[0] / 2, A4[1] - 63, text[1])
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()
