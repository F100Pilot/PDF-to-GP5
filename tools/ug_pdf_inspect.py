"""Inspect the internal structure of a PDF (built for Ultimate Guitar app exports).

Reports the PDF version, page boxes, document info, fonts (type, embedding, subset, glyph
count), content-stream operators, line widths, font sizes, the characters drawn with each
font (SMuFL code points listed separately), colours and save/restore balance.

Not part of the app. Needs: pip install pikepdf pymupdf fonttools
Usage: python tools/ug_pdf_inspect.py file.pdf
"""

from __future__ import annotations

import collections
import io
import sys


def main(path: str) -> None:
    import pikepdf
    import pymupdf
    from fontTools.cffLib import CFFFontSet
    from fontTools.ttLib import TTFont

    pdf = pikepdf.open(path)
    print(f"== {path}\nPDF {pdf.pdf_version}, {len(pdf.pages)} pages, encrypted {pdf.is_encrypted}")
    print("Info:", {str(k): str(v) for k, v in pdf.docinfo.items()}, "| Catalog keys:", list(pdf.Root.keys()))
    fonts = {}
    for number, page in enumerate(pdf.pages, start=1):
        box = [float(v) for v in page.MediaBox]
        names = {str(k): str(f.BaseFont).split("+")[-1] for k, f in page.Resources.get("/Font", {}).items()}
        print(
            f"page {number}: MediaBox {box} = {box[2] / 72 * 25.4:.1f} x {box[3] / 72 * 25.4:.1f} mm; "
            f"XObjects {len(page.Resources.get('/XObject', {}))}; fonts {names}"
        )
        for f in page.Resources.get("/Font", {}).values():
            fonts.setdefault(f.objgen, f)
    print("\n== fonts")
    for f in fonts.values():
        info = {
            "subtype": str(f.Subtype),
            "encoding": "custom" if isinstance(f.get("/Encoding"), pikepdf.Dictionary) else str(f.get("/Encoding", "")),
            "ToUnicode": "/ToUnicode" in f,
        }
        descriptor = f.get("/FontDescriptor")
        for key in ("/FontFile", "/FontFile2", "/FontFile3"):
            if descriptor is not None and key in descriptor:
                stream = descriptor[key]
                info["embedded"] = f"{key} {stream.get('/Subtype', '')}".strip()
                data = stream.read_bytes()
                info["bytes"] = len(data)
                if key == "/FontFile2":
                    info["glyphs"] = TTFont(io.BytesIO(data))["maxp"].numGlyphs
                elif key == "/FontFile3":  # bare CFF (Type1C)
                    cff = CFFFontSet()
                    cff.decompile(io.BytesIO(data), None)
                    info["cff_name"] = cff.fontNames[0]
                    info["glyphs"] = len(cff[cff.fontNames[0]].CharStrings)
        print(f"  {f.BaseFont}: {info}")
    print("\n== content streams")
    ops_total, widths, sizes, colours = (
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
        collections.Counter(),
    )
    for number, page in enumerate(pdf.pages, start=1):
        names = {str(k): str(f.BaseFont).split("+")[-1] for k, f in page.Resources.get("/Font", {}).items()}
        ops = pikepdf.parse_content_stream(page)
        depth = 0
        for operands, op in ops:
            name = str(op)
            ops_total[name] += 1
            depth += {"q": 1, "Q": -1}.get(name, 0)
            if name == "w":
                widths[round(float(operands[0]), 2)] += 1
            elif name == "Tf":
                sizes[(names.get(str(operands[0])), round(float(operands[1]), 2))] += 1
            elif name == "rg":
                colours[tuple(round(float(v), 2) for v in operands)] += 1
        print(f"page {number}: {len(ops)} operators, q/Q depth left open at the end: {depth}")
    print("operators:", dict(ops_total.most_common()))
    print("line widths:", dict(widths.most_common()))
    print("fills (rg):", dict(colours.most_common()))
    print("fonts x sizes (Tf):", dict(sizes.most_common()))
    print("\n== characters drawn per font")
    usage = collections.defaultdict(collections.Counter)
    for page in pymupdf.open(path):
        for block in page.get_text("rawdict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    for char in span["chars"]:
                        usage[span["font"].split("+")[-1]][char["c"]] += 1
    for font, counts in usage.items():
        smufl = sorted((c, n) for c, n in counts.items() if "" <= c <= "")
        text = "".join(sorted(c for c in counts if not "" <= c <= ""))
        print(f"  {font}: {sum(counts.values())} glyphs; text {text!r}")
        if smufl:
            print("     SMuFL:", ", ".join(f"U+{ord(c):04X} x{n}" for c, n in smufl))


if __name__ == "__main__":
    main(sys.argv[1])
