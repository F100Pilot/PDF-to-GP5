"""Library songs to another computer: export some songs to a ZIP, import them from it there.

The ZIP holds one folder per song, as in the library itself (musica.json, the .gp5, the cover),
without the audio, plus definicoes.json: the song's settings kept by the browser that exported
it (where bar 1 starts in the audio, the tempo, the YouTube video and its offset), which the
importing page puts back in its own browser. A manifest at the root marks the file as ours.

Reading an uploaded ZIP: entries are only looked up by name inside the archive, never written
to disk as named; their declared sizes are checked before reading, and reading stops there.
"""

from __future__ import annotations

import io
import json
import math
import time
import zipfile
from dataclasses import dataclass

from .i18n import tr
from .library_store import (
    MAX_COVER_BYTES,
    MAX_GP5_BYTES,
    MAX_META_BYTES,
    META,
    LibraryError,
    LibraryStore,
    image_type,
)

MANIFEST = "pdf-to-gp5-biblioteca.json"
SETTINGS = "definicoes.json"
FORMAT = 1
MAX_SONGS = 1000
MAX_SETTINGS_BYTES = 64 * 1024
MAX_UNPACKED_BYTES = 512 * 1024 * 1024  # the whole export, uncompressed: read into memory
_SETTING_GROUPS = ("audio", "video")


def _not_ours() -> LibraryError:
    return LibraryError(
        tr(
            "O ficheiro não é uma exportação da biblioteca do PDF → GP5.",
            "The file is not a PDF → GP5 library export.",
        )
    )


def clean_settings(value: object) -> dict:
    """The song settings kept: {"audio": {...}, "video": {...}}, each a flat object of short texts,
    numbers and true/false. Anything else is dropped."""
    if not isinstance(value, dict):
        return {}
    out: dict = {}
    for group in _SETTING_GROUPS:
        entries = value.get(group)
        if not isinstance(entries, dict):
            continue
        kept = {
            str(name)[:40]: item[:2000] if isinstance(item, str) else item
            for name, item in list(entries.items())[:20]
            if isinstance(item, (str, bool, int)) or (isinstance(item, float) and math.isfinite(item))
        }
        if kept:
            out[group] = kept
    return out if len(json.dumps(out)) <= MAX_SETTINGS_BYTES else {}


def export_songs(store: LibraryStore, items: list[tuple[str, object]]) -> bytes:
    """A ZIP of the songs `items` = [(song id, settings)], in that order. Unknown ids are skipped;
    none found raises LibraryError."""
    buffer = io.BytesIO()
    listed = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for song_id, settings in items[:MAX_SONGS]:
            found = store.export_files(song_id)
            if found is None or any(entry["folder"] == found["folder"] for entry in listed):
                continue
            folder, meta = found["folder"], found["meta"]
            archive.writestr(f"{folder}/{META}", json.dumps(meta, ensure_ascii=False, indent=1))
            for name, data in found["files"].items():
                archive.writestr(f"{folder}/{name}", data)
            archive.writestr(f"{folder}/{SETTINGS}", json.dumps(clean_settings(settings), ensure_ascii=False, indent=1))
            listed.append({"folder": folder, "key": meta["key"]})
        if not listed:
            raise LibraryError(
                tr("Nenhuma música escolhida está na biblioteca.", "None of the chosen songs is in the library.")
            )
        manifest = {"format": FORMAT, "app": "pdf-to-gp5", "exportedAt": int(time.time() * 1000), "songs": listed}
        archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
    return buffer.getvalue()


@dataclass
class ImportedSong:
    meta: dict
    gp5: bytes
    cover: bytes | None
    settings: dict


def _read(archive: zipfile.ZipFile, entries: dict, name: str, limit: int) -> bytes | None:
    info = entries.get(name)
    if info is None or info.is_dir():
        return None
    if info.file_size > limit:
        raise _not_ours()
    with archive.open(info) as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise _not_ours()
    return data


def read_export(data: bytes) -> list[ImportedSong]:
    """The songs in an exported ZIP. Raises LibraryError for anything else or a damaged file."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError):
        raise _not_ours() from None
    try:
        with archive:
            infos = archive.infolist()
            if len(infos) > 4 * MAX_SONGS + 1 or sum(info.file_size for info in infos) > MAX_UNPACKED_BYTES:
                raise _not_ours()
            entries = {info.filename: info for info in infos}
            manifest = json.loads(_read(archive, entries, MANIFEST, MAX_META_BYTES) or b"null")
            if (
                not isinstance(manifest, dict)
                or manifest.get("app") != "pdf-to-gp5"
                or manifest.get("format") != FORMAT
            ):
                raise _not_ours()
            listed = manifest.get("songs")
            if not isinstance(listed, list) or len(listed) > MAX_SONGS:
                raise _not_ours()
            songs = []
            for entry in listed:
                folder = entry.get("folder") if isinstance(entry, dict) else None
                if not isinstance(folder, str) or not folder or "/" in folder:
                    raise _not_ours()
                meta = json.loads(_read(archive, entries, f"{folder}/{META}", MAX_META_BYTES) or b"null")
                if not isinstance(meta, dict) or not isinstance(meta.get("key"), str):
                    raise _not_ours()
                files = meta.get("files") if isinstance(meta.get("files"), dict) else {}
                gp5_name = files.get("gp5")
                gp5 = (
                    _read(archive, entries, f"{folder}/{gp5_name}", MAX_GP5_BYTES)
                    if isinstance(gp5_name, str)
                    else None
                )
                if gp5 is None:
                    raise _not_ours()
                cover_entry = files.get("cover")
                cover = None
                if isinstance(cover_entry, dict) and isinstance(cover_entry.get("file"), str):
                    cover = _read(archive, entries, f"{folder}/{cover_entry['file']}", MAX_COVER_BYTES)
                    if cover is not None and image_type(cover) is None:
                        cover = None
                settings = json.loads(_read(archive, entries, f"{folder}/{SETTINGS}", MAX_SETTINGS_BYTES) or b"{}")
                songs.append(ImportedSong(meta, gp5, cover, clean_settings(settings)))
            return songs
    except (zipfile.BadZipFile, ValueError, OSError, KeyError, EOFError, NotImplementedError):
        raise _not_ours() from None


def preview(store: LibraryStore, songs: list[ImportedSong]) -> list[dict]:
    """What importing would do, per song: its details and the library's song with the same key."""
    existing = {song["key"]: song for song in store.songs()}
    out = []
    for song in songs:
        meta = song.meta
        here = existing.get(meta["key"])
        out.append(
            {
                "key": meta["key"],
                "title": meta.get("title", "") if isinstance(meta.get("title"), str) else "",
                "artist": meta.get("artist", "") if isinstance(meta.get("artist"), str) else "",
                "savedAt": meta.get("savedAt") if isinstance(meta.get("savedAt"), (int, float)) else 0,
                "trackNames": [n for n in meta.get("trackNames") or [] if isinstance(n, str)][:64],
                "measures": meta.get("measures") if isinstance(meta.get("measures"), int) else 0,
                "cover": song.cover is not None,
                "existing": {"id": here["id"], "savedAt": here["savedAt"]} if here else None,
            }
        )
    return out


def import_songs(store: LibraryStore, songs: list[ImportedSong], chosen: set[str], replace: set[str]) -> dict:
    """Store the songs whose key is in `chosen`; one already in the library only when its key is
    in `replace` too (its audio, which the export does not carry, stays). Returns what was done
    and each imported song's settings, for the page to keep in its browser."""
    existing = {song["key"] for song in store.songs()}
    imported, skipped = [], []
    for song in songs:
        key = song.meta["key"]
        if key not in chosen:
            continue
        if key in existing and key not in replace:
            skipped.append(key)
            continue
        saved = store.save(song.meta, song.gp5)
        if song.cover is not None:
            store.set_cover(saved["id"], song.cover)
        imported.append(
            {
                "key": key,
                "id": saved["id"],
                "title": saved["title"],
                "artist": saved["artist"],
                "replaced": key in existing,
                "settings": song.settings,
            }
        )
    return {"imported": imported, "skipped": skipped}
