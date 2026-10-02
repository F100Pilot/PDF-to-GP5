"""Install what is missing from the page (Definições → "Instalar"), as the start scripts do.

Only the app's own Python packages, with the Python the server runs on (its virtual environment):
first requirements.txt, then the OCR package apart (requirements-ocr.txt: it declares Python
<3.13 only, so --no-deps --ignore-requires-python). The commands are fixed here, nothing from the
request reaches them; the server only allows it when the page is open on its own computer. One
installation at a time, in a background thread; the page polls its state.
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
import threading
from pathlib import Path

from .i18n import tr

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT_S = 15 * 60
_PIP = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
STEPS = (
    [*_PIP, "-r", str(ROOT / "requirements.txt")],
    [*_PIP, "--no-deps", "--ignore-requires-python", "-r", str(ROOT / "requirements-ocr.txt")],
)
_OCR_MODULES = ("rapidocr_onnxruntime", "onnxruntime", "cv2", "numpy")


def ocr_ready() -> tuple[bool, str]:
    """(usable, problem) of reading tabs from images."""
    missing = [name for name in _OCR_MODULES if importlib.util.find_spec(name) is None]
    if not missing:
        return True, ""
    return False, tr(
        f"faltam pacotes do OCR ({', '.join(missing)})", f"OCR packages are missing ({', '.join(missing)})"
    )


class Installation:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = "idle"  # idle | running | done | failed
        self.log: list[str] = []

    def status(self) -> dict:
        with self._lock:
            return {"state": self.state, "log": self.log[-15:]}

    def start(self) -> bool:
        """Start installing; False when an installation is already running."""
        with self._lock:
            if self.state == "running":
                return False
            self.state, self.log = "running", []
        threading.Thread(target=self._run, name="install", daemon=True).start()
        return True

    def _note(self, text: str) -> None:
        with self._lock:
            self.log.extend(line for line in text.splitlines() if line.strip())

    def _run(self) -> None:
        ok = True
        for step in STEPS:
            try:
                done = subprocess.run(step, capture_output=True, text=True, timeout=TIMEOUT_S, cwd=ROOT, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                self._note(str(exc))
                ok = False
                break
            self._note(done.stdout)
            self._note(done.stderr)
            if done.returncode != 0:
                ok = False
                break
        importlib.invalidate_caches()  # packages installed now are found without a restart
        with self._lock:
            self.state = "done" if ok else "failed"


installation = Installation()
