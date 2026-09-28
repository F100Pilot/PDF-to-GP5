"""Tuning presets (MIDI note numbers, string 1 = highest) and label matching."""

from __future__ import annotations

TUNINGS: dict[str, tuple[int, ...]] = {
    "standard": (64, 59, 55, 50, 45, 40),
    "drop_d": (64, 59, 55, 50, 45, 38),
    "eb_standard": (63, 58, 54, 49, 44, 39),
    "d_standard": (62, 57, 53, 48, 43, 38),
    "drop_c": (62, 57, 53, 48, 43, 36),
    "open_g": (62, 59, 55, 50, 43, 38),
    "open_d": (62, 57, 54, 50, 45, 38),
    "dadgad": (62, 57, 55, 50, 45, 38),
    "standard_7": (64, 59, 55, 50, 45, 40, 35),
    "standard_8": (64, 59, 55, 50, 45, 40, 35, 30),
    "bass_4": (43, 38, 33, 28),
    "bass_5": (43, 38, 33, 28, 23),
}

DEFAULT_BY_STRING_COUNT: dict[int, str] = {4: "bass_4", 5: "bass_5", 6: "standard", 7: "standard_7", 8: "standard_8"}

_PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def label_pitch_class(label: str) -> int | None:
    """Return the pitch class of a tab label such as ``e``, ``Bb`` or ``F#``."""
    if not label or label[0].upper() not in _PITCH_CLASS:
        return None
    pc = _PITCH_CLASS[label[0].upper()]
    for accidental in label[1:]:
        if accidental == "#":
            pc += 1
        elif accidental == "b":
            pc -= 1
        else:
            return None
    return pc % 12


def match_labels(labels: list[str]) -> str | None:
    """Find a preset whose pitch classes match the given labels (string 1 first)."""
    classes = [label_pitch_class(label) for label in labels]
    if not classes or any(c is None for c in classes):
        return None
    for name, midi in TUNINGS.items():
        if len(midi) == len(classes) and all(m % 12 == c for m, c in zip(midi, classes)):
            return name
    return None


def resolve_tuning(requested: str, string_count: int, labels: list[str]) -> tuple[list[int], list[str]]:
    """Pick the tuning to use. Returns (midi values, warnings)."""
    warnings: list[str] = []
    if requested != "auto":
        midi = TUNINGS[requested]
        if len(midi) == string_count:
            return list(midi), warnings
        warnings.append(
            f"Afinação '{requested}' tem {len(midi)} cordas mas a tablatura tem {string_count}; "
            "usada a afinação padrão para esse número de cordas."
        )
    elif labels:
        matched = match_labels(labels)
        if matched:
            return list(TUNINGS[matched]), warnings
        warnings.append(f"Afinação indicada no PDF ({' '.join(labels)}) não reconhecida; usada a padrão.")
    default = DEFAULT_BY_STRING_COUNT.get(string_count)
    if default is None:
        raise ValueError(f"Número de cordas não suportado: {string_count}")
    return list(TUNINGS[default]), warnings
