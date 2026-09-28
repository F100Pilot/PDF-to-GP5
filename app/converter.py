"""End-to-end pipeline: PDF bytes -> tab systems -> score -> GP5 bytes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .extract.ascii_tab import extract_ascii_systems
from .extract.engraved_tab import extract_engraved_systems
from .extract.pdf_reader import PdfReadError, read_pages
from .gp5_writer import SongInfo, write_gp5
from .model import Score, TabSystem
from .preview import render_preview
from .rhythm import RhythmOptions, build_measures
from .tunings import TUNINGS, resolve_tuning

INSTRUMENTS: dict[str, int] = {
    "nylon": 24,
    "steel": 25,
    "clean": 27,
    "overdrive": 29,
    "distortion": 30,
    "bass": 33,
}


class ConversionError(Exception):
    """A user-facing error: the message is safe to return to the client."""


@dataclass(frozen=True)
class ConversionOptions:
    title: str = ""
    artist: str = ""
    tempo: int = 120
    tuning: str = "auto"
    instrument: str = "auto"
    rhythm: RhythmOptions = field(default_factory=RhythmOptions)
    max_pages: int = 40
    max_events: int = 50_000


@dataclass
class ConversionResult:
    gp5: bytes
    report: dict


def _find_systems(pdf: bytes, options: ConversionOptions, warnings: list[str]) -> list[TabSystem]:
    try:
        pages = read_pages(pdf, options.max_pages)
    except PdfReadError as exc:
        raise ConversionError(str(exc)) from exc
    if not any(page.chars for page in pages):
        raise ConversionError(
            "O PDF não contém texto extraível (provavelmente é uma digitalização/imagem). "
            "PDFs digitalizados exigem OCR, que não é suportado."
        )
    systems: list[TabSystem] = []
    for page in pages:
        ascii_systems, page_warnings = extract_ascii_systems(page)
        warnings.extend(page_warnings)
        systems.extend(ascii_systems or extract_engraved_systems(page))
    if not systems:
        raise ConversionError(
            "Não foi encontrada tablatura no PDF. São suportadas tablaturas em texto (ex.: e|--0--2--|) "
            "e tablaturas gravadas por editores (Guitar Pro, MuseScore, TuxGuitar)."
        )
    return systems


def convert(pdf: bytes, options: ConversionOptions) -> ConversionResult:
    warnings: list[str] = []
    systems = _find_systems(pdf, options, warnings)

    event_count = sum(len(s.events) for s in systems)
    if event_count > options.max_events:
        raise ConversionError(f"Tablatura demasiado grande ({event_count} notas; máximo {options.max_events}).")

    string_count, _ = Counter(s.string_count for s in systems).most_common(1)[0]
    kept = [s for s in systems if s.string_count == string_count]
    if len(kept) < len(systems):
        warnings.append(
            f"{len(systems) - len(kept)} linha(s) de tab com número de cordas diferente de {string_count} foram ignoradas."
        )

    labels = next((s.labels for s in kept if s.labels), [])
    try:
        tuning, tuning_warnings = resolve_tuning(options.tuning, string_count, labels)
    except (KeyError, ValueError) as exc:
        raise ConversionError("Afinação inválida.") from exc
    warnings.extend(tuning_warnings)

    measures = build_measures(kept, options.rhythm, warnings)
    note_count = sum(len(b.notes) for m in measures for b in m.beats if not all(n.tie for n in b.notes))
    if note_count == 0:
        raise ConversionError("A tablatura foi encontrada mas não contém notas.")

    score = Score(
        string_count=string_count,
        tuning=tuning,
        measures=measures,
        numerator=options.rhythm.numerator,
        denominator=options.rhythm.denominator,
        warnings=warnings,
    )
    if options.instrument == "auto":
        program = INSTRUMENTS["bass"] if string_count <= 5 else INSTRUMENTS["steel"]
    else:
        program = INSTRUMENTS[options.instrument]
    info = SongInfo(
        title=options.title,
        artist=options.artist,
        tempo=options.tempo,
        instrument=program,
        track_name="Bass" if program == INSTRUMENTS["bass"] else "Guitar",
    )
    gp5 = write_gp5(score, info)
    tuning_name = next((name for name, midi in TUNINGS.items() if list(midi) == tuning), "custom")
    report = {
        "systems": len(kept),
        "sources": sorted({s.source for s in kept}),
        "pages": sorted({s.page for s in kept}),
        "strings": string_count,
        "tuning": tuning_name,
        "measures": len(measures),
        "notes": note_count,
        "warnings": warnings,
        "preview": render_preview(score),
    }
    return ConversionResult(gp5=gp5, report=report)
