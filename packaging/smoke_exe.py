"""Start the built program and use it, before it is published: ``python packaging/smoke_exe.py
dist/PDF-to-GP5/PDF-to-GP5.exe``. Fails (exit 1) if the server does not start, if something it
reports as missing (OCR, FFmpeg, YouTube's JavaScript runtime) is missing, if a PDF and a picture of
a tab are not converted (the conversion runs in a child process: the frozen .exe again), or if the
bundled FFmpeg cannot write MP3.

Only the standard library: it runs with any Python, outside the program.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

SMOKE = Path(__file__).resolve().parent / "smoke"
PORT = 8021
GP5_HEADER = b"\x18FICHIER GUITAR PRO v5"


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as response:
        return json.loads(response.read())


def _convert(name: str, data: bytes, content_type: str) -> bytes:
    boundary = uuid.uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/convert/gp5",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def main(exe: Path) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows' console code page
    log = Path(tempfile.gettempdir()) / "pdf-to-gp5-smoke.log"
    env = {**os.environ, "PDF_TO_GP5_NO_BROWSER": "1"}
    with log.open("w", encoding="utf-8") as out:
        process = subprocess.Popen([str(exe)], stdout=out, stderr=subprocess.STDOUT, env=env)
    try:
        health = None
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and process.poll() is None:
            try:
                health = _get("/api/health")
                break
            except OSError:
                time.sleep(1)
        if not health:
            raise AssertionError("the server did not start")
        print("health:", health)
        for key in ("ocr", "audio_download", "audio_youtube"):
            if not health.get(key):
                raise AssertionError(f"{key}: {health.get(key + '_problem')}")
        for name, kind in (("tab.pdf", "application/pdf"), ("tab.png", "image/png")):
            gp5 = _convert(name, (SMOKE / name).read_bytes(), kind)
            if not gp5.startswith(GP5_HEADER):
                raise AssertionError(f"{name}: not a GP5 file")
            print(f"{name}: converted, {len(gp5)} bytes")
        ffmpeg = exe.parent / "_internal" / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "tone.mp3"
            subprocess.run(
                [
                    str(ffmpeg),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=duration=1",
                    "-codec:a",
                    "libmp3lame",
                    "-b:a",
                    "128k",
                    str(target),
                ],
                check=True,
            )
            if target.stat().st_size < 1000:
                raise AssertionError("FFmpeg wrote no MP3")
        print("FFmpeg: MP3 written")
        return 0
    except (AssertionError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print("SMOKE TEST FAILED:", error)
        return 1
    finally:
        process.kill()
        process.wait()
        print("--- server log ---")
        print(log.read_text(encoding="utf-8", errors="replace")[-6000:])


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
