"""The Windows build: the app made into a program (PyInstaller) that carries its own Python, packages
and the programs it calls. There FFmpeg and Deno are files in the bundle, not packages of a Python
environment, the program folder may be read-only (Program Files) and nothing can be installed with
pip. Running from the source (start.bat), none of this applies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "PDF-to-GP5"
FROZEN = bool(getattr(sys, "frozen", False))


def _bundle() -> Path | None:
    """The folder PyInstaller unpacks the app's files to (``_internal`` beside the .exe)."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if FROZEN and base else None


def program(name: str) -> str | None:
    """A program shipped in the bundle (``<bundle>/<name>/<name>.exe``), or None outside it."""
    bundle = _bundle()
    if bundle is None:
        return None
    path = bundle / name / (name + (".exe" if os.name == "nt" else ""))
    return str(path) if path.is_file() else None


def user_data_dir() -> Path:
    """Where the installed app keeps what it writes (the YouTube key): the program folder may be
    read-only. %LOCALAPPDATA%\\PDF-to-GP5 on Windows, ~/.local/share/PDF-to-GP5 elsewhere."""
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if sys.platform == "win32" and local else Path.home() / ".local" / "share"
    return base / APP_NAME
