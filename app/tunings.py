"""Tuning presets (MIDI note numbers, string 1 = highest) and label matching."""

from __future__ import annotations

from .i18n import tr

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
    "bass_4": (43, 38, 33, 28),
    "bass_5": (43, 38, 33, 28, 23),
}

# Guitar Pro 5 stores at most 7 strings per track.
DEFAULT_BY_STRING_COUNT: dict[int, str] = {4: "bass_4", 5: "bass_5", 6: "standard", 7: "standard_7"}

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


# Names printed instead of note letters ("Tuning: Drop D", "Afinação: meio tom abaixo").
TUNING_NAMES: dict[str, str] = {
    "standard": "standard",
    "e standard": "standard",
    "padrão": "standard",
    "normal": "standard",
    "drop d": "drop_d",
    "eb standard": "eb_standard",
    "e flat standard": "eb_standard",
    "half step down": "eb_standard",
    "1/2 step down": "eb_standard",
    "½ step down": "eb_standard",
    "meio tom abaixo": "eb_standard",
    "d standard": "d_standard",
    "whole step down": "d_standard",
    "1 step down": "d_standard",
    "um tom abaixo": "d_standard",
    "drop c": "drop_c",
    "open g": "open_g",
    "open d": "open_d",
    "dadgad": "dadgad",
}


def labels_to_midi(labels: list[str]) -> list[int] | None:
    """MIDI tuning for arbitrary note labels (string 1 first), octaves taken from the
    standard tuning with the same number of strings."""
    reference = DEFAULT_BY_STRING_COUNT.get(len(labels))
    classes = [label_pitch_class(label) for label in labels]
    if reference is None or any(c is None for c in classes):
        return None
    tuning: list[int] = []
    for base, pitch_class in zip(TUNINGS[reference], classes, strict=True):
        candidates = [base + delta for delta in range(-6, 7) if (base + delta) % 12 == pitch_class]
        tuning.append(min(candidates, key=lambda m: (abs(m - base), m)))
    return tuning


def resolve_tuning(requested: str, string_count: int, labels: list[str]) -> tuple[list[int], list[str]]:
    """Pick the tuning to use. Returns (midi values, warnings)."""
    warnings: list[str] = []
    if requested != "auto":
        midi = TUNINGS[requested]
        if len(midi) == string_count:
            return list(midi), warnings
        warnings.append(
            tr(
                f"Afinação '{requested}' tem {len(midi)} cordas mas a tablatura tem {string_count}; "
                "usada a afinação padrão para esse número de cordas.",
                f"Tuning '{requested}' has {len(midi)} strings but the tablature has {string_count}; "
                "using the standard tuning for that number of strings.",
            )
        )
    elif labels and len(labels) == string_count:
        matched = match_labels(labels)
        if matched:
            return list(TUNINGS[matched]), warnings
        custom = labels_to_midi(labels)
        if custom is not None:
            return custom, warnings
        warnings.append(
            tr(
                f"Afinação indicada no PDF ({' '.join(labels)}) não reconhecida; usada a padrão.",
                f"Tuning given in the PDF ({' '.join(labels)}) not recognized; using the standard one.",
            )
        )
    elif labels:
        warnings.append(
            tr(
                f"A afinação indicada no PDF tem {len(labels)} notas mas a tablatura tem {string_count} cordas; "
                "usada a padrão.",
                f"The tuning given in the PDF has {len(labels)} notes but the tablature has {string_count} strings; "
                "using the standard one.",
            )
        )
    default = DEFAULT_BY_STRING_COUNT.get(string_count)
    if default is None:
        raise ValueError(
            tr(f"Número de cordas não suportado: {string_count}", f"Unsupported number of strings: {string_count}")
        )
    return list(TUNINGS[default]), warnings
