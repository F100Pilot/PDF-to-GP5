"""Serialise a Score into a Guitar Pro 5 (.gp5) file using PyGuitarPro."""

from __future__ import annotations

import io
import unicodedata
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
class SongInfo:
    title: str = ""
    artist: str = ""
    tempo: int = 120
    instrument: int = 25  # General MIDI program
    track_name: str = "Guitar"


def sanitize_text(value: str, max_length: int = 100) -> str:
    """Drop control characters and anything the cp1252 GP5 encoding cannot hold."""
    cleaned = "".join(ch for ch in value if unicodedata.category(ch)[0] != "C")
    cleaned = cleaned.encode("cp1252", errors="ignore").decode("cp1252")
    return cleaned.strip()[:max_length]


def _bend(note: ScoreNote) -> gp.BendEffect:
    # BendPoint values are quarter tones (PyGuitarPro scales them on write).
    peak = note.bend_semitones * 2
    if note.bend_release:
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
        slides=[gp.SlideType.legatoSlideTo] if note.slide else [],
        bend=_bend(note) if note.bend_semitones and not note.dead else None,
    )
    return gp.Note(beat, value=note.fret, string=note.string, type=note_type, effect=effect)


def _make_beat(voice: gp.Voice, beat: ScoreBeat) -> gp.Beat:
    value, dotted = _UNITS_TO_DURATION[beat.units]
    gp_beat = gp.Beat(
        voice,
        duration=gp.Duration(value=value, isDotted=dotted),
        status=gp.BeatStatus.rest if beat.is_rest else gp.BeatStatus.normal,
    )
    gp_beat.notes.extend(_make_note(gp_beat, n) for n in beat.notes)
    return gp_beat


def build_song(score: Score, info: SongInfo) -> gp.Song:
    song = gp.Song()
    song.title = sanitize_text(info.title)
    song.artist = sanitize_text(info.artist)
    song.tempo = info.tempo
    song.measureHeaders = []

    track = song.tracks[0]
    track.name = sanitize_text(info.track_name, 40) or "Guitar"
    track.strings = [gp.GuitarString(number, value) for number, value in enumerate(score.tuning, start=1)]
    track.channel.instrument = info.instrument
    max_fret = max((n.fret for m in score.measures for b in m.beats for n in b.notes), default=0)
    track.fretCount = max(24, max_fret)
    track.measures = []

    start = gp.Duration.quarterTime
    for number, measure in enumerate(score.measures, start=1):
        header = gp.MeasureHeader(
            number=number,
            start=start,
            timeSignature=gp.TimeSignature(numerator=score.numerator, denominator=gp.Duration(value=score.denominator)),
        )
        song.addMeasureHeader(header)
        start += header.length
        gp_measure = gp.Measure(track, header)
        voice = gp_measure.voices[0]
        voice.beats.extend(_make_beat(voice, b) for b in measure.beats)
        # Guitar Pro itself stores one empty beat in the unused second voice.
        second = gp_measure.voices[1]
        second.beats.append(gp.Beat(second, status=gp.BeatStatus.empty))
        track.measures.append(gp_measure)
    return song


def write_gp5(score: Score, info: SongInfo) -> bytes:
    if not score.measures:
        raise ValueError("A partitura não tem compassos.")
    buffer = io.BytesIO()
    gp.write(build_song(score, info), buffer, version=GP5_VERSION)
    return buffer.getvalue()
