# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe of the Windows program: ``python packaging/build_exe.py`` runs it.

A one-folder build (dist/PDF-to-GP5/): PDF-to-GP5.exe and _internal/ with Python, every package
(the OCR included), the page (app/static), the changelogs, and the programs the app calls:
  ffmpeg/ffmpeg.exe  an LGPL build, put in packaging/ffmpeg/ before building (the release
                     workflow downloads it; imageio-ffmpeg's own binary is a GPL build and is left
                     out)
  deno/deno.exe      the JavaScript runtime yt-dlp needs for YouTube, from the "deno" package
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 - SPECPATH is given by PyInstaller
PACKAGING = ROOT / "packaging"

datas = []
# Every file of the app that is not code (the page, its fonts, alphaTab, three.js…), at its
# package path, where the app reads it. Walked, not listed: a file added later is bundled too.
for path in sorted((ROOT / "app").rglob("*")):
    if path.is_file() and path.suffix not in (".py", ".pyc") and "__pycache__" not in path.parts:
        datas.append((str(path), str(path.parent.relative_to(ROOT))))
for name in ("CHANGELOG.md", "CHANGELOG.en.md"):  # What's new (app/changelog.py reads them there)
    datas.append((str(ROOT / name), "."))
# Data inside packages: the OCR's models and settings, PDF character maps, yt-dlp's YouTube scripts.
for package in ("rapidocr_onnxruntime", "pdfminer", "yt_dlp_ejs"):
    datas += collect_data_files(package)

# The programs the app calls (app/bundled.py finds them there).
ffmpeg = PACKAGING / "ffmpeg"
if not (ffmpeg / "ffmpeg.exe").is_file() and not (ffmpeg / "ffmpeg").is_file():
    raise SystemExit("packaging/ffmpeg/ffmpeg(.exe) is missing: see packaging/build_exe.py")
for path in ffmpeg.iterdir():  # the program, its licence and where its source is
    datas.append((str(path), "ffmpeg"))
from deno import find_deno_bin  # noqa: E402

datas.append((find_deno_bin(), "deno"))

# The Microsoft C++ runtime the OCR (onnxruntime, OpenCV) needs: shipped beside the program, as
# Microsoft allows, so it runs on a Windows without the "Visual C++ Redistributable".
binaries = []
if os.name == "nt":
    system32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    for name in ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll"):
        if (system32 / name).is_file():
            binaries.append((str(system32 / name), "."))

hiddenimports = [
    *collect_submodules("app"),
    *collect_submodules("rapidocr_onnxruntime"),
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
]

a = Analysis(
    [str(ROOT / "pdf_to_gp5_exe.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # imageio_ffmpeg: its binary is a GPL build (the LGPL one above is used). mutagen (GPL): an
    # optional part of yt-dlp, for tagging files, which the app does not use. The rest is not used.
    excludes=["imageio_ffmpeg", "mutagen", "tkinter", "matplotlib", "pytest", "IPython"],
    # PyGuitarPro is LGPL: shipped as its .py files (_internal/guitarpro/), which anyone can replace
    # with another version, not inside the program's archive.
    module_collection_mode={"guitarpro": "py"},
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PDF-to-GP5",
    console=True,  # the window shows the server's messages; closing the page stops it
    icon=str(PACKAGING / "pdf-to-gp5.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PDF-to-GP5", upx=False)
