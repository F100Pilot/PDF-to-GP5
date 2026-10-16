"""Build the Windows program: PDF-to-GP5.exe (a folder), a portable .zip and the installer.

    py -3.11 packaging\\build_exe.py [--zip] [--installer]

Needs, in the same Python: requirements.txt, requirements-ocr.txt (with --no-deps, as start.bat
installs it) and requirements-build.txt; packaging\\ffmpeg\\ffmpeg.exe with its LICENSE.txt and
SOURCE.txt (an LGPL build: the release workflow downloads one); Inno Setup 6 for --installer.

Output:
    dist/PDF-to-GP5/PDF-to-GP5.exe   the program (with _internal/ beside it)
    dist/PDF-to-GP5-portable.zip     with --zip
    dist/PDF-to-GP5-Setup.exe        with --installer
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "PDF-to-GP5"
# Travel with every copy: the app's licence, what it bundles and under which licences.
LEGAL_FILES = ("LICENSE", "THIRD_PARTY_NOTICES.md")


def build() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            str(DIST),
            str(ROOT / "packaging" / "pdf-to-gp5.spec"),
        ],
        check=True,
        cwd=ROOT,
    )
    for name in LEGAL_FILES:
        shutil.copy2(ROOT / name, APP / name)
    # The licence of every Python package inside, with its full text (MIT, BSD, Apache… require it).
    licences = subprocess.run(
        [
            sys.executable,
            "-m",
            "piplicenses",
            "--from=mixed",
            "--with-urls",
            "--with-license-file",
            "--no-license-path",
            "--format=plain-vertical",
            "--ignore-packages",
            "pip-licenses",
            "prettytable",
            "wcwidth",
            "pyinstaller-hooks-contrib",
            "imageio-ffmpeg",
            "mutagen",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    (APP / "THIRD_PARTY_LICENSES.txt").write_text(licences, encoding="utf-8")


def make_zip() -> Path:
    archive = shutil.make_archive(str(DIST / "PDF-to-GP5-portable"), "zip", DIST, APP.name)
    return Path(archive)


def make_installer() -> None:
    iscc = shutil.which("ISCC") or next(
        (
            str(p)
            for p in (
                Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
                Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
            )
            if p.is_file()
        ),
        None,
    )
    if not iscc:
        raise SystemExit("Inno Setup 6 (ISCC.exe) not found: https://jrsoftware.org/isinfo.php")
    version = re.search(r'__version__ = "([^"]+)"', (ROOT / "app" / "__init__.py").read_text(encoding="utf-8"))[1]
    subprocess.run([iscc, f"/DMyAppVersion={version}", str(ROOT / "packaging" / "installer.iss")], check=True, cwd=ROOT)


if __name__ == "__main__":
    build()
    if "--zip" in sys.argv:
        print("ZIP:", make_zip())
    if "--installer" in sys.argv:
        make_installer()
