"""End-to-end pipeline: PDF bytes -> tab systems -> score -> GP5 bytes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .extract.ascii_tab import extract_ascii_systems
from .extract.engraved_tab import extract_engraved_systems
from .extract.metadata import SongMetadata, detect_metadata
from .extract.pdf_reader import PdfReadError, read_document
from .gp5_writer import SongInfo, write_gp5
from .model import Score, TabSystem
from .preview import render_preview
from .rhythm import RhythmMode, RhythmOptions, RhythmStats, build_measures
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
    """User choices; empty/None values mean "detect from the PDF"."""

    title: str = ""
    artist: str = ""
    tempo: int | None = None
    numerator: int | None = None
    denominator: int | None = None
    tuning: str = "auto"
    instrument: str = "auto"
    rhythm_mode: RhythmMode = "auto"
    fixed_value: int = 8
    max_pages: int = 40
    max_events: int = 50_000


@dataclass
class ConversionResult:
    gp5: bytes
    report: dict


DEFAULT_TEMPO = 120
DEFAULT_TIME_SIGNATURE = (4, 4)


def _find_systems(pdf: bytes, options: ConversionOptions, warnings: list[str]) -> tuple[list[TabSystem], SongMetadata]:
    try:
        pages, info = read_document(pdf, options.max_pages)
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
    return systems, detect_metadata(pages, info)


def convert(pdf: bytes, options: ConversionOptions) -> ConversionResult:
    warnings: list[str] = []
    systems, detected = _find_systems(pdf, options, warnings)
    title = options.title.strip() or detected.title or ""
    artist = options.artist.strip() or detected.artist or ""
    tempo = options.tempo or detected.tempo or DEFAULT_TEMPO
    if options.numerator and options.denominator:
        numerator, denominator = options.numerator, options.denominator
    elif detected.numerator and detected.denominator:
        numerator, denominator = detected.numerator, detected.denominator
    else:
        numerator, denominator = DEFAULT_TIME_SIGNATURE
    rhythm = RhythmOptions(
        mode=options.rhythm_mode, fixed_value=options.fixed_value, numerator=numerator, denominator=denominator
    )

    event_count = sum(len(s.events) for s in systems)
    if event_count > options.max_events:
        raise ConversionError(f"Tablatura demasiado grande ({event_count} notas; máximo {options.max_events}).")

    # Only staves with notes vote: empty engraved staves may be standard-notation staves.
    with_notes = [s for s in systems if s.events]
    if not with_notes:
        raise ConversionError("A tablatura foi encontrada mas não contém notas.")
    string_count, _ = Counter(s.string_count for s in with_notes).most_common(1)[0]
    kept = [s for s in systems if s.string_count == string_count]
    dropped = sum(1 for s in with_notes if s.string_count != string_count)
    if dropped:
        warnings.append(f"{dropped} linha(s) de tab com número de cordas diferente de {string_count} foram ignoradas.")

    labels = next((s.labels for s in kept if s.labels), [])
    try:
        tuning, tuning_warnings = resolve_tuning(options.tuning, string_count, labels)
    except (KeyError, ValueError) as exc:
        raise ConversionError("Afinação inválida.") from exc
    warnings.extend(tuning_warnings)

    system_measures: list[int] = []
    rhythm_stats = RhythmStats()
    measures = build_measures(kept, rhythm, warnings, system_measures, rhythm_stats)
    if rhythm_stats.notated and rhythm_stats.estimated:
        warnings.append(
            f"Ritmo lido da partitura em {rhythm_stats.notated} compasso(s); "
            f"{rhythm_stats.estimated} compasso(s) estimados pelo espaçamento."
        )
    note_count = sum(len(b.notes) for m in measures for b in m.beats if not all(n.tie for n in b.notes))
    if note_count == 0:
        raise ConversionError("A tablatura foi encontrada mas não contém notas.")

    score = Score(
        string_count=string_count,
        tuning=tuning,
        measures=measures,
        numerator=numerator,
        denominator=denominator,
        warnings=warnings,
    )
    if options.instrument == "auto":
        program = INSTRUMENTS["bass"] if string_count <= 5 else INSTRUMENTS["steel"]
    else:
        program = INSTRUMENTS[options.instrument]
    info = SongInfo(
        title=title,
        artist=artist,
        tempo=tempo,
        instrument=program,
        track_name="Bass" if program == INSTRUMENTS["bass"] else "Guitar",
    )
    gp5 = write_gp5(score, info)
    tuning_name = next((name for name, midi in TUNINGS.items() if list(midi) == tuning), "custom")
    report = {
        "title": title,
        "artist": artist,
        "tempo": tempo,
        "time_signature": f"{numerator}/{denominator}",
        "auto": {
            "title": not options.title.strip() and bool(detected.title),
            "artist": not options.artist.strip() and bool(detected.artist),
            "tempo": not options.tempo and detected.tempo is not None,
            "time_signature": not (options.numerator and options.denominator) and detected.numerator is not None,
        },
        "rhythm_from_notation": rhythm_stats.notated,
        "rhythm_estimated": rhythm_stats.estimated,
        "systems": len(kept),
        "sources": sorted({s.source for s in kept}),
        "pages": sorted({s.page for s in kept}),
        "strings": string_count,
        "tuning": tuning_name,
        "measures": len(measures),
        "notes": note_count,
        "warnings": warnings,
        "preview": render_preview(score),
        "systems_detail": [
            {
                "page": s.page,
                "source": s.source,
                "notes": len(s.events),
                "measures": system_measures[i] if i < len(system_measures) else None,
            }
            for i, s in enumerate(kept)
        ],
    }
    return ConversionResult(gp5=gp5, report=report)


def inspect(pdf: bytes, options: ConversionOptions) -> dict:
    """Detect song metadata only, so the user can review it before converting."""
    try:
        pages, info = read_document(pdf, options.max_pages)
    except PdfReadError as exc:
        raise ConversionError(str(exc)) from exc
    if not any(page.chars for page in pages):
        raise ConversionError(
            "O PDF não contém texto extraível (provavelmente é uma digitalização/imagem). "
            "PDFs digitalizados exigem OCR, que não é suportado."
        )
    meta = detect_metadata(pages, info)
    return {
        "title": meta.title,
        "artist": meta.artist,
        "tempo": meta.tempo,
        "time_signature": f"{meta.numerator}/{meta.denominator}" if meta.numerator and meta.denominator else None,
        "pages": len(pages),
    }
