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
            # Three points: readers such as alphaTab infer the shape from the points.
            points = [gp.BendPoint(0, peak), gp.BendPoint(6, peak), gp.BendPoint(12, 0)]
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
        staccato=note.staccato,
    )
    velocity = note.velocity or gp.Velocities.default
    if note.grace_fret is not None and not note.dead:
        transition = gp.GraceEffectTransition.hammer if note.grace_hammer else gp.GraceEffectTransition.none
        effect.grace = gp.GraceEffect(fret=note.grace_fret, transition=transition, velocity=velocity)
    return gp.Note(beat, value=note.fret, string=note.string, type=note_type, effect=effect, velocity=velocity)


def _make_beat(voice: gp.Voice, beat: ScoreBeat) -> gp.Beat:
    value, dotted = _UNITS_TO_DURATION[beat.units]
    duration = gp.Duration(value=value, isDotted=dotted)
    if beat.tuplet:
        duration.tuplet = gp.Tuplet(3, 2)
    gp_beat = gp.Beat(
        voice,
        duration=duration,
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
MAX_REPEAT_TIMES = 32  # a repeat played more often is most likely a misread count
# Navigation marks as Guitar Pro names them: targets (at the start of a bar; "Fine" ends the song
# after its bar) and jumps (after their bar; "Da Coda" is "To Coda").
DIRECTION_SIGNS = ("Segno", "Coda", "Fine")
DIRECTION_JUMPS = (
    "Da Capo",
    "Da Capo al Coda",
    "Da Capo al Fine",
    "Da Segno",
    "Da Segno al Coda",
    "Da Segno al Fine",
    "Da Coda",
)
MIN_TEMPO, MAX_TEMPO = 20, 400
# One colour per track position, shared with the web page (/api/options). Dark enough
# for white text on top.
TRACK_COLORS = (
    (29, 78, 216),  # blue
    (194, 65, 12),  # orange
    (21, 128, 61),  # green
    (126, 34, 206),  # purple
    (190, 24, 93),  # pink
    (15, 118, 110),  # teal
    (161, 98, 7),  # ochre
)


def _build_track(song: gp.Song, number: int, score: Score) -> gp.Track:
    track = gp.Track(song, number=number)
    track.name = sanitize_text(score.name, 40) or f"Track {number}"
    track.color = gp.Color(*TRACK_COLORS[(number - 1) % len(TRACK_COLORS)])
    track.strings = [gp.GuitarString(n, value) for n, value in enumerate(score.tuning, start=1)]
    track.channel.channel = _MELODIC_CHANNELS[2 * (number - 1)]
    track.channel.effectChannel = _MELODIC_CHANNELS[2 * (number - 1) + 1]
    track.channel.instrument = score.instrument
    if score.muted:
        track.isMute = True
        track.channel.volume = 0
    max_fret = max((n.fret for m in score.measures for b in m.beats for n in b.notes), default=0)
    track.fretCount = max(24, max_fret)
    track.measures = []
    for header, measure in zip(song.measureHeaders, score.measures, strict=True):
        gp_measure = gp.Measure(track, header)
        voice = gp_measure.voices[0]
        voice.beats.extend(_make_beat(voice, b) for b in measure.beats)
        if number == 1 and measure.tempo and MIN_TEMPO <= measure.tempo <= MAX_TEMPO and voice.beats:
            # A tempo change is stored once, on the first beat of the bar in the first track.
            voice.beats[0].effect.mixTableChange = gp.MixTableChange(
                tempo=gp.MixTableItem(value=measure.tempo), hideTempo=False
            )
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
    for number, measure in enumerate(first.measures, start=1):
        # Time signature and repeats are stored once per bar for all tracks (the converter makes
        # the tracks agree); bars without their own time signature use the song's.
        numerator, denominator = measure.time_signature or (first.numerator, first.denominator)
        header = gp.MeasureHeader(
            number=number,
            start=start,
            timeSignature=gp.TimeSignature(numerator=numerator, denominator=gp.Duration(value=denominator)),
            isRepeatOpen=measure.repeat_open,
            # PyGuitarPro counts the extra passes (the file stores the total).
            repeatClose=min(measure.repeat_times, MAX_REPEAT_TIMES) - 1 if measure.repeat_times >= 2 else -1,
            repeatAlternative=sum(1 << (n - 1) for n in set(measure.endings) if 1 <= n <= 8),
            direction=gp.DirectionSign(measure.sign) if measure.sign in DIRECTION_SIGNS else None,
            fromDirection=gp.DirectionSign(measure.jump) if measure.jump in DIRECTION_JUMPS else None,
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
