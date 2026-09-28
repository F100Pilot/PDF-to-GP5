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
