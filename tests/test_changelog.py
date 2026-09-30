from app.changelog import load_releases, parse_changelog

SAMPLE = """# Changelog

Intro text.

## [Unreleased]
### Adicionado
- work in progress

## [0.2.0] - 2026-02-01
### Adicionado
- feature `x`
  continued line
### Corrigido
- bug

## [0.10.0] - 2026-03-01
### Alterado
- later

## [not-a-version]
- ignored
"""


def test_parse_skips_unreleased_and_sorts_semantically():
    releases = parse_changelog(SAMPLE)
    assert [r["version"] for r in releases] == ["0.10.0", "0.2.0"]
    assert releases[1] == {
        "version": "0.2.0",
        "date": "2026-02-01",
        "sections": [
            {"name": "Adicionado", "items": ["feature `x` continued line"]},
            {"name": "Corrigido", "items": ["bug"]},
        ],
    }


def test_repository_changelog_is_parseable_and_matches_version():
    from app import __version__

    releases = load_releases()
    assert releases and releases[0]["version"] == __version__
    assert all(section["items"] for release in releases for section in release["sections"])


_EN_SECTIONS = {
    "Adicionado": "Added",
    "Alterado": "Changed",
    "Corrigido": "Fixed",
    "Removido": "Removed",
    "Segurança": "Security",
    "Descontinuado": "Deprecated",
}


def _shape(text: str) -> list[tuple[str, list[tuple[str, int]]]]:
    """Every release (Unreleased included) → its sections with their item counts."""
    out: list[tuple[str, list[tuple[str, int]]]] = []
    for line in text.splitlines():
        if line.startswith("## "):
            out.append((line.split("]")[0] + "]", []))
        elif line.startswith("### ") and out:
            out[-1][1].append((line[4:].strip(), 0))
        elif line.startswith("- ") and out and out[-1][1]:
            name, n = out[-1][1][-1]
            out[-1][1][-1] = (name, n + 1)
    return out


def test_every_translated_changelog_has_the_same_entries():
    """What's new is shown in the app's language: each CHANGELOG.<code>.md must carry
    the same releases, sections and number of entries as CHANGELOG.md, so an entry
    added in Portuguese and not translated fails here."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    pt = _shape((root / "CHANGELOG.md").read_text(encoding="utf-8"))
    translations = sorted(root.glob("CHANGELOG.*.md"))
    assert translations, "CHANGELOG.en.md is missing"
    for path in translations:
        other = _shape(path.read_text(encoding="utf-8"))
        assert [r for r, _ in other] == [r for r, _ in pt], f"{path.name}: releases differ"
        for (release, secs_pt), (_, secs_other) in zip(pt, other, strict=True):
            assert [n for _, n in secs_other] == [n for _, n in secs_pt], f"{path.name} {release}: entries differ"
            if path.name == "CHANGELOG.en.md":
                expected = [_EN_SECTIONS.get(name, name) for name, _ in secs_pt]
                assert [name for name, _ in secs_other] == expected, f"{path.name} {release}: section names"


def test_the_banner_reads_the_changelog_of_the_request_language():
    from fastapi.testclient import TestClient

    from app import __version__, main

    with TestClient(main.app) as client:
        pt = client.get("/api/changelog").json()
        en = client.get("/api/changelog", headers={"X-App-Lang": "en"}).json()
    assert pt["releases"][0]["version"] == en["releases"][0]["version"] == __version__
    assert pt["releases"][0]["sections"][0]["name"] == "Adicionado"
    assert en["releases"][0]["sections"][0]["name"] == "Added"
    assert len(en["releases"]) == len(pt["releases"])
