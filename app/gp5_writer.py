"""Serialise a Score into a Guitar Pro 5 (.gp5) file using PyGuitarPro."""

from __future__ import annotations

import io
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

import guitarpro as gp

from .model import Score, ScoreBeat, ScoreNote

_UNITS_TO_DURATION = {
    48: (1, True),
    32: (1, False),
    24: (2, True),
    16: (2, False),
    12: (4, True),
    8: (4, False),
    6: (8, True),
    4: (8, False),
    3: (16, True),
    2: (16, False),
    1: (32, False),
}
GP5_VERSION = (5, 1, 0)
_BEND_UNITS_PER_SEMITONE = 50  # Guitar Pro: 100 = one whole tone


@dataclass(frozen=True)
class LyricsInfo:
    """Song lyrics for one track: up to 5 lines, each starting at a bar (1-based)."""

    track: int  # 1-based track number the syllables follow
    lines: tuple[tuple[int, str], ...]


@dataclass(frozen=True)
class SongInfo:
    title: str = ""
    artist: str = ""
    tempo: int = 120
    lyrics: LyricsInfo | None = None


def sanitize_text(value: str, max_length: int = 100) -> str:
    """Drop control characters and anything the cp1252 GP5 encoding cannot hold."""
    cleaned = "".join(ch for ch in value if unicodedata.category(ch)[0] != "C")
    cleaned = cleaned.encode("cp1252", errors="ignore").decode("cp1252")
    return cleaned.strip()[:max_length]


def _bend(note: ScoreNote) -> gp.BendEffect:
    # BendPoint values are quarter tones (PyGuitarPro scales them on write).
    peak = note.bend_semitones * 2
    if note.bend_pre:
        if note.bend_release:
            points = [gp.BendPoint(0, peak), gp.BendPoint(4, peak), gp.BendPoint(8, 0), gp.BendPoint(12, 0)]
            bend_type = gp.BendType.prebendRelease
        else:
            points = [gp.BendPoint(0, peak), gp.BendPoint(12, peak)]
            bend_type = gp.BendType.prebend
    elif note.bend_release:
        points = [
            gp.BendPoint(0, 0),
            gp.BendPoint(3, peak),
            gp.BendPoint(6, peak),
            gp.BendPoint(9, 0),
            gp.BendPoint(12, 0),
        ]
        bend_type = gp.BendType.bendRelease
    else:
        points = [gp.BendPoint(0, 0), gp.BendPoint(6, peak), gp.BendPoint(12, peak)]
        bend_type = gp.BendType.bend
    return gp.BendEffect(type=bend_type, value=note.bend_semitones * _BEND_UNITS_PER_SEMITONE, points=points)


_SLIDE_IN = {"below": gp.SlideType.intoFromBelow, "above": gp.SlideType.intoFromAbove}
_SLIDE_OUT = {"down": gp.SlideType.outDownwards, "up": gp.SlideType.outUpwards}


def _slides(note: ScoreNote) -> list[gp.SlideType]:
    slides: list[gp.SlideType] = []
    if note.slide:
        slides.append(gp.SlideType.legatoSlideTo)
    elif note.slide_shift:
        slides.append(gp.SlideType.shiftSlideTo)
    if note.slide_in in _SLIDE_IN:
        slides.append(_SLIDE_IN[note.slide_in])
    if note.slide_out in _SLIDE_OUT:
        slides.append(_SLIDE_OUT[note.slide_out])
    return slides


def _make_note(beat: gp.Beat, note: ScoreNote) -> gp.Note:
    if note.dead:
        note_type = gp.NoteType.dead
    elif note.tie:
        note_type = gp.NoteType.tie
    else:
        note_type = gp.NoteType.normal
    effect = gp.NoteEffect(
        ghostNote=note.ghost,
        vibrato=note.vibrato,
        letRing=note.let_ring,
        palmMute=note.palm_mute,
        hammer=note.hammer,
        slides=_slides(note),
        bend=_bend(note) if note.bend_semitones and not note.dead else None,
        harmonic=gp.NaturalHarmonic() if note.harmonic == "natural" else None,
    )
    velocity = note.velocity or gp.Velocities.default
    return gp.Note(beat, value=note.fret, string=note.string, type=note_type, effect=effect, velocity=velocity)


def _make_beat(voice: gp.Voice, beat: ScoreBeat) -> gp.Beat:
    value, dotted = _UNITS_TO_DURATION[beat.units]
    gp_beat = gp.Beat(
        voice,
        duration=gp.Duration(value=value, isDotted=dotted),
        status=gp.BeatStatus.rest if beat.is_rest else gp.BeatStatus.normal,
    )
    gp_beat.notes.extend(_make_note(gp_beat, n) for n in beat.notes)
    stroke = next((n.stroke for n in beat.notes if n.stroke), None)
    if stroke:
        direction = gp.BeatStrokeDirection.down if stroke == "down" else gp.BeatStrokeDirection.up
        gp_beat.effect.stroke = gp.BeatStroke(direction, gp.Duration.thirtySecond)
    if any(n.tapped for n in beat.notes):
        gp_beat.effect.slapEffect = gp.SlapEffect.tapping
    return gp_beat


# MIDI channels on port 1 without the percussion channel (index 9): two per track
# (normal + effects), so at most 7 tracks.
_MELODIC_CHANNELS = [c for c in range(16) if c != 9]
MAX_TRACKS = len(_MELODIC_CHANNELS) // 2
MAX_STRINGS = 7  # the GP5 track header has room for 7 string tunings


def _build_track(song: gp.Song, number: int, score: Score) -> gp.Track:
    track = gp.Track(song, number=number)
    track.name = sanitize_text(score.name, 40) or f"Track {number}"
    track.strings = [gp.GuitarString(n, value) for n, value in enumerate(score.tuning, start=1)]
    track.channel.channel = _MELODIC_CHANNELS[2 * (number - 1)]
    track.channel.effectChannel = _MELODIC_CHANNELS[2 * (number - 1) + 1]
    track.channel.instrument = score.instrument
    max_fret = max((n.fret for m in score.measures for b in m.beats for n in b.notes), default=0)
    track.fretCount = max(24, max_fret)
    track.measures = []
    for header, measure in zip(song.measureHeaders, score.measures, strict=True):
        gp_measure = gp.Measure(track, header)
        voice = gp_measure.voices[0]
        voice.beats.extend(_make_beat(voice, b) for b in measure.beats)
        # Guitar Pro itself stores one empty beat in the unused second voice.
        second = gp_measure.voices[1]
        second.beats.append(gp.Beat(second, status=gp.BeatStatus.empty))
        track.measures.append(gp_measure)
    return track


def build_song(scores: Sequence[Score], info: SongInfo) -> gp.Song:
    """Build a song with one track per score; all scores must have the same number of measures."""
    if not scores or not scores[0].measures:
        raise ValueError("A partitura não tem compassos.")
    if len(scores) > MAX_TRACKS:
        raise ValueError(f"Máximo de {MAX_TRACKS} tracks.")
    if any(s.string_count > MAX_STRINGS for s in scores):
        raise ValueError(f"O formato GP5 suporta no máximo {MAX_STRINGS} cordas.")
    if len({len(s.measures) for s in scores}) != 1:
        raise ValueError("As tracks têm números de compassos diferentes.")
    song = gp.Song()
    song.title = sanitize_text(info.title)
    song.artist = sanitize_text(info.artist)
    song.tempo = info.tempo
    song.measureHeaders = []
    first = scores[0]
    start = gp.Duration.quarterTime
    for number in range(1, len(first.measures) + 1):
        header = gp.MeasureHeader(
            number=number,
            start=start,
            timeSignature=gp.TimeSignature(numerator=first.numerator, denominator=gp.Duration(value=first.denominator)),
        )
        marker = next((s.measures[number - 1].marker for s in scores if s.measures[number - 1].marker), None)
        if marker:
            header.marker = gp.Marker(title=sanitize_text(marker, 40), color=gp.Color(255, 0, 0))
        song.addMeasureHeader(header)
        start += header.length
    song.tracks = [_build_track(song, number, score) for number, score in enumerate(scores, start=1)]
    if info.lyrics and info.lyrics.lines:
        lines = [gp.LyricLine(bar, sanitize_text(text, 10_000)) for bar, text in info.lyrics.lines[:5]]
        lines += [gp.LyricLine() for _ in range(5 - len(lines))]
        song.lyrics = gp.Lyrics(trackChoice=info.lyrics.track, lines=lines)
    return song


def write_gp5(scores: Score | Sequence[Score], info: SongInfo) -> bytes:
    if isinstance(scores, Score):
        scores = [scores]
    buffer = io.BytesIO()
    gp.write(build_song(scores, info), buffer, version=GP5_VERSION)
    return buffer.getvalue()
