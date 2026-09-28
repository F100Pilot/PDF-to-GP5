"""End-to-end pipeline: PDF bytes -> tab systems -> scores (one per track) -> GP5 bytes."""

from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import dataclass, field

from .extract.ascii_tab import extract_ascii_systems
from .extract.engraved_tab import extract_engraved_systems
from .extract.metadata import SongMetadata, detect_metadata, detect_part_name, track_name_from_filename
from .extract.pdf_reader import PdfReadError, read_document
from .gp5_writer import MAX_STRINGS, MAX_TRACKS, LyricsInfo, SongInfo, write_gp5
from .model import Score, ScoreBeat, ScoreMeasure, TabSystem
from .preview import render_preview
from .rhythm import RhythmMode, RhythmOptions, RhythmStats, build_measures, split_units
from .tunings import TUNINGS, resolve_tuning

INSTRUMENTS: dict[str, int] = {
    "nylon": 24,
    "steel": 25,
    "clean": 27,
    "overdrive": 29,
    "distortion": 30,
    "bass": 33,
}
DEFAULT_TEMPO = 120
DEFAULT_TIME_SIGNATURE = (4, 4)


class ConversionError(Exception):
    """A user-facing error: the message is safe to return to the client."""


@dataclass(frozen=True)
class TrackOptions:
    """Per-PDF choices; empty/"auto" values mean "detect"."""

    name: str = ""
    filename: str = ""
    tuning: str = "auto"
    instrument: str = "auto"


@dataclass(frozen=True)
class ConversionOptions:
    """Song-level choices; empty/None values mean "detect from the PDFs"."""

    title: str = ""
    artist: str = ""
    tempo: int | None = None
    numerator: int | None = None
    denominator: int | None = None
    tracks: tuple[TrackOptions, ...] = ()
    rhythm_mode: RhythmMode = "auto"
    fixed_value: int = 8
    max_pages: int = 40
    max_events: int = 50_000
    max_measures: int = 2000

    def track(self, index: int) -> TrackOptions:
        return self.tracks[index] if index < len(self.tracks) else TrackOptions()


@dataclass
class ConversionResult:
    gp5: bytes
    report: dict


@dataclass
class _ParsedPdf:
    systems: list[TabSystem]
    metadata: SongMetadata
    part_name: str | None
    warnings: list[str] = field(default_factory=list)


def _read(pdf: bytes, options: ConversionOptions):
    try:
        pages, info = read_document(pdf, options.max_pages)
    except PdfReadError as exc:
        raise ConversionError(str(exc)) from exc
    if not any(page.chars for page in pages):
        raise ConversionError(
            "O PDF não contém texto extraível (provavelmente é uma digitalização/imagem). "
            "PDFs digitalizados exigem OCR, que não é suportado."
        )
    return pages, info


def _parse_pdf(pdf: bytes, options: ConversionOptions) -> _ParsedPdf:
    pages, info = _read(pdf, options)
    warnings: list[str] = []
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
    metadata = detect_metadata(pages, info)
    return _ParsedPdf(systems, metadata, detect_part_name(pages, metadata), warnings)


def _merge_metadata(items: list[SongMetadata]) -> SongMetadata:
    """First detected value for each field across the PDFs."""

    def first(attr: str):
        return next((getattr(m, attr) for m in items if getattr(m, attr) is not None), None)

    signature = next(((m.numerator, m.denominator) for m in items if m.numerator and m.denominator), (None, None))
    return SongMetadata(first("title"), first("artist"), first("tempo"), *signature)


def _main_staves(systems: list[TabSystem], warnings: list[str]) -> tuple[int, list[TabSystem]]:
    # Only staves with notes vote: empty engraved staves may be standard-notation staves.
    with_notes = [s for s in systems if s.events]
    if not with_notes:
        raise ConversionError("A tablatura foi encontrada mas não contém notas.")
    string_count, _ = Counter(s.string_count for s in with_notes).most_common(1)[0]
    dropped = sum(1 for s in with_notes if s.string_count != string_count)
    if dropped:
        warnings.append(f"{dropped} linha(s) de tab com número de cordas diferente de {string_count} foram ignoradas.")
    return string_count, [s for s in systems if s.string_count == string_count]


def _apply_dynamics(systems: list[TabSystem]) -> None:
    """Each dynamic mark sets the velocity of the notes from its position on, across lines."""
    current: int | None = None
    for system in systems:
        marks = sorted(system.dynamics)
        index = 0
        for event in sorted(system.events, key=lambda e: e.x):
            while index < len(marks) and marks[index][0] <= event.x + system.char_width:
                current = marks[index][1]
                index += 1
            event.velocity = current
        if index < len(marks):
            current = marks[-1][1]


def _bar_of(system: TabSystem, x: float, previous: int) -> int:
    """Printed bar number of the bar containing ``x`` (counting on from ``previous`` when unknown)."""
    bounds = sorted(system.bars)
    numbers = system.bar_numbers if len(system.bar_numbers) == len(bounds) - 1 else []
    number = previous
    for index, (start, end) in enumerate(itertools.pairwise(bounds)):
        known = numbers[index] if index < len(numbers) else None
        number = known if known is not None else number + 1
        if x < end:
            return number
    return max(number, previous)


def _lyric_lines(systems: list[TabSystem], max_lines: int = 5) -> list[tuple[int, str]]:
    """Lyrics as at most ``max_lines`` (starting bar, text) blocks.

    Guitar Pro gives one syllable to each note of the chosen track, so the text is
    cut into blocks that restart at the bar where they were printed.
    """
    words: list[tuple[int, str, bool]] = []
    last_bar = 0
    for system in systems:
        for x, syllable, joins in sorted(system.lyrics):
            last_bar = _bar_of(system, x, last_bar)
            words.append((last_bar, syllable, joins))
        if system.bars:
            last_bar = _bar_of(system, max(system.bars), last_bar)
    if not words:
        return []
    blocks: list[list[tuple[int, str, bool]]] = [[words[0]]]
    for word in words[1:]:
        if word[0] - blocks[-1][-1][0] > 1:
            blocks.append([word])
        else:
            blocks[-1].append(word)
    while len(blocks) > max_lines:  # merge across the smallest gaps
        gaps = [blocks[i + 1][0][0] - blocks[i][-1][0] for i in range(len(blocks) - 1)]
        i = gaps.index(min(gaps))
        blocks[i : i + 2] = [blocks[i] + blocks[i + 1]]
    return [(block[0][0], "".join(s + ("-" if joins else " ") for _, s, joins in block).strip()) for block in blocks]


def _tuning_name(tuning: list[int]) -> str:
    return next((name for name, midi in TUNINGS.items() if list(midi) == tuning), "custom")


def _build_track(parsed: _ParsedPdf, track: TrackOptions, rhythm: RhythmOptions, name: str) -> tuple[Score, dict]:
    warnings = list(parsed.warnings)
    string_count, kept = _main_staves(parsed.systems, warnings)
    if string_count > MAX_STRINGS:
        raise ConversionError(f"A tablatura tem {string_count} cordas; o formato GP5 suporta no máximo {MAX_STRINGS}.")
    labels = next((s.labels for s in kept if s.labels), []) or list(parsed.metadata.tuning_labels)
    try:
        tuning, tuning_warnings = resolve_tuning(track.tuning, string_count, labels)
    except (KeyError, ValueError) as exc:
        raise ConversionError("Afinação inválida.") from exc
    warnings.extend(tuning_warnings)

    _apply_dynamics(kept)
    system_measures: list[int] = []
    stats = RhythmStats()
    measures = build_measures(kept, rhythm, warnings, system_measures, stats)
    if stats.notated and stats.estimated:
        warnings.append(
            f"Ritmo lido da partitura em {stats.notated} compasso(s); "
            f"{stats.estimated} compasso(s) estimados pelo espaçamento."
        )
    note_count = sum(len(b.notes) for m in measures for b in m.beats if not all(n.tie for n in b.notes))
    if note_count == 0:
        raise ConversionError("A tablatura foi encontrada mas não contém notas.")
    instrument = track.instrument
    if instrument == "auto":
        instrument = "bass" if string_count <= 5 else "steel"
    score = Score(
        string_count=string_count,
        tuning=tuning,
        measures=measures,
        numerator=rhythm.numerator,
        denominator=rhythm.denominator,
        warnings=warnings,
        name=name,
        instrument=INSTRUMENTS[instrument],
    )
    report = {
        "name": name,
        "dynamics": sum(len(s.dynamics) for s in kept),
        "filename": track.filename,
        "instrument": instrument,
        "strings": string_count,
        "tuning": _tuning_name(tuning),
        "measures": len(measures),
        "notes": note_count,
        "systems": len(kept),
        "sources": sorted({s.source for s in kept}),
        "pages": sorted({s.page for s in kept}),
        "rhythm_from_notation": stats.notated,
        "rhythm_estimated": stats.estimated,
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
    report["_lyrics"] = _lyric_lines(kept)
    return score, report


def _track_name(index: int, track: TrackOptions, parsed: _ParsedPdf, song: SongMetadata) -> str:
    return (
        track.name.strip()
        or parsed.part_name
        or track_name_from_filename(track.filename, song.title, song.artist)
        or f"Track {index + 1}"
    )


def _rest_bar(score: Score) -> ScoreMeasure:
    units = score.numerator * 32 // score.denominator
    return ScoreMeasure([ScoreBeat(part) for part in split_units(units)])


def _ranges(numbers: list[int]) -> str:
    """[3, 4, 5, 9] -> "3–5, 9"."""
    parts: list[str] = []
    for _, group in itertools.groupby(enumerate(numbers), key=lambda item: item[1] - item[0]):
        values = [n for _, n in group]
        parts.append(f"{values[0]}–{values[-1]}" if len(values) > 1 else str(values[0]))
    return ", ".join(parts)


def _align_by_numbers(score: Score) -> list[int] | None:
    """Put each bar at its printed bar number, filling gaps with rests.

    Returns the missing bar numbers, or None when the numbering is absent or not
    strictly increasing (the measures are then left untouched).
    """
    measures = score.measures
    if not measures or sum(m.number is not None for m in measures) < 0.8 * len(measures):
        return None
    # A misread (or hostile) bar number far beyond the bars actually read would
    # create that many rest bars; distrust the numbering instead.
    if max(m.number or 0 for m in measures) > 2 * len(measures) + 64:
        return None
    slots: dict[int, ScoreMeasure] = {}
    position = 0
    for measure in measures:
        target = measure.number if measure.number is not None else position + 1
        if target <= position:
            return None
        slots[target] = measure
        position = target
    missing = [n for n in range(1, position + 1) if n not in slots]
    score.measures = [slots.get(n) or _rest_bar(score) for n in range(1, position + 1)]
    for number, measure in enumerate(score.measures, start=1):
        measure.number = number
    return missing


def _pad(score: Score, measures: int) -> int:
    """Append full-bar rests so every track has the same number of bars; returns bars added."""
    missing = measures - len(score.measures)
    score.measures.extend(_rest_bar(score) for _ in range(missing))
    return missing


def convert(pdf: bytes, options: ConversionOptions) -> ConversionResult:
    return convert_many([pdf], options)


def convert_many(pdfs: list[bytes], options: ConversionOptions) -> ConversionResult:
    """Convert one PDF per track into a single GP5 file."""
    if not pdfs:
        raise ConversionError("Nenhum PDF enviado.")
    if len(pdfs) > MAX_TRACKS:
        raise ConversionError(f"Máximo de {MAX_TRACKS} PDFs (tracks) por música.")
    multi = len(pdfs) > 1

    def labelled(index: int, message: str) -> str:
        filename = options.track(index).filename
        return f"Track {index + 1}{f' ({filename})' if filename else ''}: {message}" if multi else message

    parsed: list[_ParsedPdf] = []
    for index, pdf in enumerate(pdfs):
        try:
            parsed.append(_parse_pdf(pdf, options))
        except ConversionError as exc:
            raise ConversionError(labelled(index, str(exc))) from exc

    event_count = sum(len(s.events) for p in parsed for s in p.systems)
    if event_count > options.max_events:
        raise ConversionError(f"Tablatura demasiado grande ({event_count} notas; máximo {options.max_events}).")

    detected = _merge_metadata([p.metadata for p in parsed])
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
        mode=options.rhythm_mode,
        fixed_value=options.fixed_value,
        numerator=numerator,
        denominator=denominator,
    )

    scores: list[Score] = []
    track_reports: list[dict] = []
    for index, item in enumerate(parsed):
        track = options.track(index)
        try:
            score, report = _build_track(item, track, rhythm, _track_name(index, track, item, detected))
        except ConversionError as exc:
            raise ConversionError(labelled(index, str(exc))) from exc
        scores.append(score)
        track_reports.append(report)

    aligned: list[bool] = []
    for score, report in zip(scores, track_reports, strict=True):
        missing = _align_by_numbers(score)
        aligned.append(missing is not None)
        report["missing_bars"] = missing or []
        if missing:
            report["warnings"].append(f"Compassos não encontrados no PDF, preenchidos com pausa: {_ranges(missing)}.")
    total_measures = max(len(s.measures) for s in scores)
    if total_measures > options.max_measures:
        raise ConversionError(f"A música tem {total_measures} compassos; o máximo é {options.max_measures}.")
    for score, report, by_number in zip(scores, track_reports, aligned, strict=True):
        first_added = len(score.measures) + 1
        added = _pad(score, total_measures)
        if added:
            report["missing_bars"].extend(range(first_added, total_measures + 1))
            where = "" if by_number else " (sem numeração de compassos no PDF: pode estar desalinhada)"
            report["warnings"].append(
                f"Tem {first_added - 1} compassos e a música tem {total_measures}: "
                f"acrescentados {added} compasso(s) de pausa no fim{where}."
            )

    lyric_candidates = [i for i, r in enumerate(track_reports) if r["_lyrics"]]
    lyrics = None
    if lyric_candidates:
        chosen = max(lyric_candidates, key=lambda i: track_reports[i]["notes"])
        lyrics = LyricsInfo(track=chosen + 1, lines=tuple(track_reports[chosen]["_lyrics"]))
    for report in track_reports:
        del report["_lyrics"]
    sections = []
    for index in range(total_measures):
        name = next((s.measures[index].marker for s in scores if s.measures[index].marker), None)
        if name:
            sections.append({"bar": index + 1, "name": name})

    gp5 = write_gp5(scores, SongInfo(title=title, artist=artist, tempo=tempo, lyrics=lyrics))
    warnings = [f"{r['name']}: {w}" if multi else w for r in track_reports for w in r["warnings"]]
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
        "measures": total_measures,
        "notes": sum(r["notes"] for r in track_reports),
        "sections": sections,
        "lyrics": {"track": track_reports[lyrics.track - 1]["name"], "lines": len(lyrics.lines)} if lyrics else None,
        "warnings": warnings,
        "tracks": track_reports,
    }
    return ConversionResult(gp5=gp5, report=report)


def inspect(pdf: bytes, options: ConversionOptions) -> dict:
    """Detect song metadata and the track's part, so the user can review them before converting."""
    parsed = _parse_pdf(pdf, options)
    meta = parsed.metadata
    string_count, kept = _main_staves(parsed.systems, [])
    labels = next((s.labels for s in kept if s.labels), []) or list(meta.tuning_labels)
    tuning, _ = resolve_tuning("auto", string_count, labels)
    return {
        "title": meta.title,
        "artist": meta.artist,
        "tempo": meta.tempo,
        "time_signature": f"{meta.numerator}/{meta.denominator}" if meta.numerator and meta.denominator else None,
        # Part label printed in the PDF; the client falls back to the file name once it
        # knows the song title/artist from all PDFs (same rule as track_name_from_filename).
        "part_name": parsed.part_name,
        "strings": string_count,
        "tuning": _tuning_name(tuning),
    }
