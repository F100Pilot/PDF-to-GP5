"""The song library in a folder on disk: one sub-folder per song, readable without the app.

    <root>/Eagles - Hotel California/
        musica.json            title, artist, report… and the names of the files below
        Hotel California.gp5   opens in Guitar Pro
        Hotel California.mp3   the audio chosen for the song (optional)
        capa.jpg               the album cover (optional)

It does not depend on the browser or on the server's address (port), unlike the browser's own
storage. Folders and files are only ever reached by listing the root: a song id from a request
is compared with the existing folder names, never joined to a path as given. Every file is
written to a temporary name first and then renamed, so a stopped server leaves no half file.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from .i18n import tr

META = "musica.json"
MAX_GP5_BYTES = 5 * 1024 * 1024
MAX_COVER_BYTES = 5 * 1024 * 1024
MAX_META_BYTES = 4 * 1024 * 1024
GP5_SIGNATURE = b"\x18FICHIER GUITAR PRO"
AUDIO_TYPES = {"audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/wav": ".wav"}
COVER_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}


class LibraryError(Exception):
    """A song or file that cannot be stored (wrong type, too large, bad data)."""


def safe_name(text: str, fallback: str, limit: int = 80) -> str:
    """A file or folder name valid on Windows, macOS and Linux ("AC/DC" -> "AC_DC")."""
    name = re.sub(r"\s+", " ", _UNSAFE.sub("_", text)).strip(" .")[:limit].rstrip(" .")
    if not name or name.split(".", 1)[0].lower() in _RESERVED:
        return fallback
    return name


def audio_type(data: bytes) -> str | None:
    """The media type of an MP3, Ogg or WAV file, from its first bytes."""
    if data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav"
    return None


def image_type(data: bytes) -> str | None:
    """The media type of a JPEG, PNG or WebP image, from its first bytes."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _write(path: Path, data: bytes) -> None:
    """Write `data` to `path` in one step (temporary file in the same folder, then rename)."""
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _text(value: object, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _number(value: object) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else None


class LibraryStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = threading.Lock()

    # --- Reading ----------------------------------------------------------------------------
    def _folders(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return [path for path in self.root.iterdir() if path.is_dir() and (path / META).is_file()]

    @staticmethod
    def _meta(folder: Path) -> dict | None:
        try:
            data = json.loads((folder / META).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None  # damaged or foreign: left alone
        return data if isinstance(data, dict) and isinstance(data.get("key"), str) else None

    def _folder(self, song_id: str) -> Path | None:
        """The song's folder, found among the existing ones (the id is never used as a path)."""
        return next((folder for folder in self._folders() if folder.name == song_id), None)

    def _folder_of_key(self, key: str) -> Path | None:
        return next((folder for folder in self._folders() if (self._meta(folder) or {}).get("key") == key), None)

    @staticmethod
    def _summary(folder: Path, meta: dict) -> dict:
        files = meta.get("files") or {}
        audio = files.get("audio")
        return {
            "id": folder.name,
            "key": meta["key"],
            "title": meta.get("title", ""),
            "artist": meta.get("artist", ""),
            "tempo": meta.get("tempo"),
            "measures": meta.get("measures") or 0,
            "trackNames": meta.get("trackNames") or [],
            "savedAt": meta.get("savedAt") or 0,
            "audioName": audio["name"] if isinstance(audio, dict) else "",
            "cover": bool(files.get("cover")),
            "coverVersion": meta.get("coverVersion") or 0,
        }

    def songs(self) -> list[dict]:
        found = []
        for folder in self._folders():
            meta = self._meta(folder)
            if meta:
                found.append(self._summary(folder, meta))
        return sorted(found, key=lambda song: song["savedAt"], reverse=True)

    def song(self, song_id: str) -> dict | None:
        """Summary, file name and report of a song."""
        folder = self._folder(song_id)
        meta = self._meta(folder) if folder else None
        if not meta:
            return None
        return {**self._summary(folder, meta), "filename": meta.get("filename", ""), "report": meta.get("report")}

    def file(self, song_id: str, kind: str) -> tuple[Path, str, str] | None:
        """(path, media type, download name) of the song's gp5, audio or cover."""
        folder = self._folder(song_id)
        meta = self._meta(folder) if folder else None
        entry = ((meta or {}).get("files") or {}).get(kind)
        if not entry:
            return None
        if kind == "gp5":
            name, media_type = entry, "application/octet-stream"
        elif isinstance(entry, dict):
            name, media_type = entry.get("file"), entry.get("type")
        else:
            return None
        path = next((p for p in folder.iterdir() if p.name == name and p.is_file()), None)
        if path is None or not isinstance(media_type, str):
            return None
        label = entry.get("name", name) if isinstance(entry, dict) else name
        return path, media_type, label

    def export_files(self, song_id: str) -> dict | None:
        """For an export: the song's folder name, its details without the audio, and the bytes
        of its gp5 and cover by file name."""
        folder = self._folder(song_id)
        meta = self._meta(folder) if folder else None
        if not meta:
            return None
        files = dict(meta.get("files") or {})
        files.pop("audio", None)
        on_disk = {p.name: p for p in folder.iterdir() if p.is_file()}
        gp5 = on_disk.get(files.get("gp5") or "")
        if gp5 is None:
            return None
        found = {gp5.name: gp5.read_bytes()}
        cover = files.get("cover")
        cover_path = on_disk.get(cover.get("file") or "") if isinstance(cover, dict) else None
        if cover_path is None:
            files.pop("cover", None)  # listed but gone: exported without it
        else:
            found[cover_path.name] = cover_path.read_bytes()
        exported = {k: v for k, v in meta.items() if k != "coverVersion"}
        exported["files"] = files
        return {"folder": folder.name, "meta": exported, "files": found}

    # --- Writing ----------------------------------------------------------------------------
    def _new_folder(self, artist: str, title: str) -> Path:
        base = safe_name(" - ".join(part for part in (artist, title) if part), "Sem título")
        taken = {path.name.lower() for path in self.root.iterdir()}
        name, number = base, 2
        while name.lower() in taken:
            name, number = f"{base} ({number})", number + 1
        folder = self.root / name
        folder.mkdir()
        return folder

    def save(self, meta: dict, gp5: bytes) -> dict:
        """Store a converted song (a new one, or the same key again: its audio and cover stay)."""
        key = _text(meta.get("key"), 500)
        if not key:
            raise LibraryError(tr("Música sem identificação.", "Song without an identifier."))
        if not gp5.startswith(GP5_SIGNATURE) or len(gp5) > MAX_GP5_BYTES:
            raise LibraryError(tr("O ficheiro não é um GP5 válido.", "The file is not a valid GP5."))
        report = meta.get("report")
        if not isinstance(report, dict) or len(json.dumps(report)) > MAX_META_BYTES:
            raise LibraryError(tr("Relatório da conversão inválido.", "Invalid conversion report."))
        title, artist = _text(meta.get("title"), 200), _text(meta.get("artist"), 200)
        filename = _text(meta.get("filename"), 200)
        names = meta.get("trackNames")
        track_names = [_text(n, 100) for n in names[:64]] if isinstance(names, list) else []
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            folder = self._folder_of_key(key) or self._new_folder(artist, title or filename)
            previous = self._meta(folder) or {}
            files = dict(previous.get("files") or {})
            gp5_name = safe_name(filename.removesuffix(".gp5") or title, "musica") + ".gp5"
            if files.get("gp5") and files["gp5"] != gp5_name:
                (folder / files["gp5"]).unlink(missing_ok=True)
            _write(folder / gp5_name, gp5)
            files["gp5"] = gp5_name
            stored = {
                "key": key,
                "title": title,
                "artist": artist,
                "tempo": _number(meta.get("tempo")),
                "measures": _number(meta.get("measures")) or 0,
                "trackNames": track_names,
                "savedAt": _number(meta.get("savedAt")) or int(time.time() * 1000),
                "filename": filename,
                "report": report,
                "files": files,
                "coverVersion": previous.get("coverVersion") or 0,
            }
            _write(folder / META, json.dumps(stored, ensure_ascii=False, indent=1).encode("utf-8"))
            return self._summary(folder, stored)

    def _update(self, song_id: str, change) -> bool:
        with self._lock:
            folder = self._folder(song_id)
            meta = self._meta(folder) if folder else None
            if not meta:
                return False
            files = dict(meta.get("files") or {})
            change(folder, meta, files)
            meta["files"] = files
            _write(folder / META, json.dumps(meta, ensure_ascii=False, indent=1).encode("utf-8"))
            return True

    @staticmethod
    def _replace(folder: Path, files: dict, kind: str, file_name: str | None, data: bytes | None) -> None:
        old = files.get(kind)
        if isinstance(old, dict) and old.get("file") and old.get("file") != file_name:
            (folder / old["file"]).unlink(missing_ok=True)
        if data is not None and file_name:
            _write(folder / file_name, data)

    def set_audio(self, song_id: str, name: str, data: bytes | None) -> bool:
        """The song's audio file (None: remove it). Returns False when there is no such song."""
        media_type = None
        if data is not None:
            media_type = audio_type(data)
            if media_type is None:
                raise LibraryError(
                    tr("O áudio tem de ser um ficheiro MP3, Ogg ou WAV.", "The audio must be an MP3, Ogg or WAV file.")
                )
        extension = AUDIO_TYPES.get(media_type or "", "")
        stem = safe_name(name.rsplit(".", 1)[0] if "." in name else name, "audio")

        def change(folder: Path, meta: dict, files: dict) -> None:
            file_name = f"{stem}{extension}" if data is not None else None
            if file_name and file_name.lower() in {str(files.get("gp5", "")).lower(), META}:
                file_name = f"audio{extension}"
            self._replace(folder, files, "audio", file_name, data)
            if data is None:
                files.pop("audio", None)
            else:
                files["audio"] = {"file": file_name, "type": media_type, "name": safe_name(name, file_name, 200)}

        return self._update(song_id, change)

    def set_cover(self, song_id: str, data: bytes | None) -> bool:
        media_type = None
        if data is not None:
            media_type = image_type(data)
            if media_type is None or len(data) > MAX_COVER_BYTES:
                raise LibraryError(
                    tr(
                        "A capa tem de ser uma imagem JPEG, PNG ou WebP até 5 MB.",
                        "The cover must be a JPEG, PNG or WebP image up to 5 MB.",
                    )
                )

        def change(folder: Path, meta: dict, files: dict) -> None:
            file_name = f"capa{COVER_TYPES[media_type]}" if media_type else None
            self._replace(folder, files, "cover", file_name, data)
            if data is None:
                files.pop("cover", None)
            else:
                files["cover"] = {"file": file_name, "type": media_type, "name": file_name}
            meta["coverVersion"] = (meta.get("coverVersion") or 0) + 1

        return self._update(song_id, change)

    def delete(self, song_id: str) -> bool:
        with self._lock:
            folder = self._folder(song_id)
            if folder is None:
                return False
            # Only the app's own files: anything the user put in the folder stays (and so does it).
            meta = self._meta(folder) or {}
            files = meta.get("files") or {}
            names = [files.get("gp5")] + [
                e.get("file") for e in (files.get("audio"), files.get("cover")) if isinstance(e, dict)
            ]
            for path in folder.iterdir():
                if path.is_file() and (path.name in names or path.name.startswith(".tmp-")):
                    path.unlink()
            (folder / META).unlink(missing_ok=True)
            if not any(folder.iterdir()):
                folder.rmdir()
            return True
