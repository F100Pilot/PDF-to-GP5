import pytest

from app.tunings import TUNINGS, match_labels, resolve_tuning


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (["e", "B", "G", "D", "A", "E"], "standard"),
        (["E", "B", "G", "D", "A", "D"], "drop_d"),
        (["Eb", "Bb", "Gb", "Db", "Ab", "Eb"], "eb_standard"),
        (["D", "A", "G", "D", "A", "D"], "dadgad"),
        (["G", "D", "A", "E"], "bass_4"),
        (["e", "B", "G", "D", "A", "E", "B"], "standard_7"),
        (["X", "B", "G", "D", "A", "E"], None),
    ],
)
def test_match_labels(labels, expected):
    assert match_labels(labels) == expected


def test_resolve_uses_labels_then_default():
    assert resolve_tuning("auto", 6, ["e", "B", "G", "D", "A", "D"]) == (list(TUNINGS["drop_d"]), [])
    tuning, warnings = resolve_tuning("auto", 6, ["q"] * 6)
    assert tuning == list(TUNINGS["standard"]) and warnings


def test_resolve_mismatched_string_count_falls_back():
    tuning, warnings = resolve_tuning("standard", 4, [])
    assert tuning == list(TUNINGS["bass_4"]) and warnings
