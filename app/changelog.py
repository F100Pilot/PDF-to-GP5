"""Parse CHANGELOG.md (Keep a Changelog format) for the in-app "what's new" banner.

The Portuguese is CHANGELOG.md; every other language the app has is
CHANGELOG.<code>.md with the same releases, sections and items (tests/test_changelog.py
checks it). A language without its own file reads the Portuguese."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

CHANGELOG_PATH = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
_RELEASE = re.compile(r"^## \[(?P<version>\d+\.\d+\.\d+)\](?:\s*-\s*(?P<date>\d{4}-\d{2}-\d{2}))?\s*$")
_ANY_RELEASE = re.compile(r"^## ")
_SECTION = re.compile(r"^### (?P<name>.+?)\s*$")
_ITEM = re.compile(r"^- (?P<text>.+)$")


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def parse_changelog(text: str) -> list[dict]:
    """Released versions, newest first. Unreleased and malformed headings are skipped."""
    releases: list[dict] = []
    current: dict | None = None
    section: dict | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        release = _RELEASE.match(line)
        if release:
            current = {"version": release.group("version"), "date": release.group("date"), "sections": []}
            releases.append(current)
            section = None
            continue
        if _ANY_RELEASE.match(line):  # e.g. "## [Unreleased]"
            current = section = None
            continue
        if current is None:
            continue
        heading = _SECTION.match(line)
        if heading:
            section = {"name": heading.group("name"), "items": []}
            current["sections"].append(section)
            continue
        item = _ITEM.match(line)
        if item and section is not None:
            section["items"].append(item.group("text"))
        elif line.startswith("  ") and section is not None and section["items"]:
            section["items"][-1] += " " + line.strip()  # wrapped item
    return sorted(releases, key=lambda r: version_key(r["version"]), reverse=True)


def changelog_path(lang: str = "pt") -> Path:
    """CHANGELOG.<lang>.md when the language has one, else the Portuguese CHANGELOG.md."""
    translated = CHANGELOG_PATH.with_name(f"CHANGELOG.{lang}.md")
    return translated if lang != "pt" and translated.is_file() else CHANGELOG_PATH


@lru_cache(maxsize=8)
def load_releases(lang: str = "pt") -> tuple[dict, ...]:
    try:
        return tuple(parse_changelog(changelog_path(lang).read_text(encoding="utf-8")))
    except OSError:
        return ()
