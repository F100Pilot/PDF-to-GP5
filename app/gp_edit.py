"""Correct notes of a Guitar Pro 3/4/5 file: give a note another fret, remove it, or give its
beat another duration.

The page sends where the note is (track, bar, voice, beat, string) and the fret it shows now;
the file is changed only when that note is still there with that fret. A tied note is one sound
with the note it continues, so the whole tied chain gets the new fret (or goes) together.

A new duration keeps the bar whole: a shorter beat leaves a rest at the end of the bar, a longer
one takes the time from the rests at the end of the bar — or is refused, saying how much is
missing, when there are not enough (another beat of the bar is shortened first).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import guitarpro as gp

from .converter import ConversionError
from .i18n import tr

MAX_EDITS = 500
MAX_FRET = 30  # past any real neck; the track's own fret count raises it if it is bigger
_LIMITS = {"track": 63, "bar": 9999, "voice": 1, "beat": 999, "string": 12, "expected": 99}


@dataclass(frozen=True)
class NoteEdit:
    track: int  # 0-based, as in the file
    bar: int  # 0-based
    voice: int  # 0 or 1
    beat: int  # 0-based, within the voice
    string: int  # 1 = highest string (Guitar Pro's numbering)
    expected: int  # the fret the note has now
    fret: int | None  # the new fret; None removes the note


@dataclass(frozen=True)
class Length:
    value: int  # 1 whole, 2 half, 4 quarter, 8 eighth, 16 sixteenth, 32 thirty-second
    dotted: bool = False
    triplet: bool = False

    def duration(self) -> gp.Duration:
        tuplet = gp.Tuplet(3, 2) if self.triplet else gp.Tuplet(1, 1)
        return gp.Duration(value=self.value, isDotted=self.dotted, tuplet=tuplet)

    @staticmethod
    def of(duration: gp.Duration) -> Length | None:
        """The beat's length, or None for one the page cannot set (another tuplet than a triplet)."""
        tuplet = (duration.tuplet.enters, duration.tuplet.times)
        if tuplet not in ((1, 1), (3, 2)) or duration.value not in _VALUES:
            return None
        return Length(duration.value, duration.isDotted, tuplet == (3, 2))


@dataclass(frozen=True)
class LengthEdit:
    track: int
    bar: int
    voice: int
    beat: int
    expected: Length  # the beat's length now
    length: Length  # its new length


_VALUES = (1, 2, 4, 8, 16, 32)
# Rest lengths that fill a bar's end, longest first: plain values, then triplets (for what a
# triplet beat leaves over).
_FILLERS = [Length(v) for v in _VALUES] + [Length(v, triplet=True) for v in _VALUES]


def _invalid() -> ConversionError:
    return ConversionError(tr("Correção de notas inválida.", "Invalid note correction."))


def _whole(value: object, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise _invalid()
    return value


_BEAT_KEYS = ("track", "bar", "voice", "beat")


def _length(raw: object) -> Length:
    if (
        not isinstance(raw, dict)
        or set(raw) != {"value", "dotted", "triplet"}
        or raw["value"] not in _VALUES
        or isinstance(raw["value"], bool)
        or not isinstance(raw["dotted"], bool)
        or not isinstance(raw["triplet"], bool)
    ):
        raise _invalid()
    return Length(raw["value"], raw["dotted"], raw["triplet"])


def parse_edits(raw: object) -> list[NoteEdit | LengthEdit]:
    """The edits as the page sends them (a JSON list of objects), checked; ConversionError otherwise.
    A note edit: track, bar, voice, beat, string, expected (fret), fret (None removes the note).
    A length edit: track, bar, voice, beat, expected_length, length ({value, dotted, triplet})."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_EDITS:
        raise _invalid()
    edits: list[NoteEdit | LengthEdit] = []
    for item in raw:
        if isinstance(item, dict) and set(item) == {*_BEAT_KEYS, "expected_length", "length"}:
            where = {key: _whole(item[key], 0, _LIMITS[key]) for key in _BEAT_KEYS}
            edits.append(LengthEdit(**where, expected=_length(item["expected_length"]), length=_length(item["length"])))
            continue
        if not isinstance(item, dict) or set(item) != {*_LIMITS, "fret"}:
            raise _invalid()
        fields = {key: _whole(item[key], 1 if key == "string" else 0, high) for key, high in _LIMITS.items()}
        fret = None if item["fret"] is None else _whole(item["fret"], 0, 99)
        edits.append(NoteEdit(**fields, fret=fret))
    return edits


def _note_on(beat: gp.Beat, string: int) -> gp.Note | None:
    return next((note for note in beat.notes if note.string == string), None)


def _tied_chain(beats: list[gp.Beat], index: int, string: int) -> list[gp.Note]:
    """The note on `string` in beats[index] with the notes tied to it, before and after."""
    start = index
    while start > 0 and _note_on(beats[start], string).type == gp.NoteType.tie:
        if _note_on(beats[start - 1], string) is None:
            break
        start -= 1
    chain = [_note_on(beats[start], string)]
    for beat in beats[start + 1 :]:
        note = _note_on(beat, string)
        if note is None or note.type != gp.NoteType.tie:
            break
        chain.append(note)
    return chain


def _voice_beats(track: gp.Track, voice: int) -> list[gp.Beat]:
    """The beats of one voice through the whole song, bar after bar."""
    return [beat for measure in track.measures if voice < len(measure.voices) for beat in measure.voices[voice].beats]


def _repair_ties(song: gp.Song) -> None:
    """A tied note has the fret of the note it continues. PyGuitarPro reads a tie on the first beat
    of a bar as fret 0 (it looks for the note it continues only in the same bar): it would show,
    and be written back, as 0."""
    for track in song.tracks:
        for voice in (0, 1):
            last: dict[int, int] = {}  # string -> fret of the note last played on it
            for beat in _voice_beats(track, voice):
                for note in beat.notes:
                    if note.type == gp.NoteType.tie and note.string in last:
                        note.value = last[note.string]
                    last[note.string] = note.value


def _apply(song: gp.Song, edit: NoteEdit) -> None:
    gone = ConversionError(
        tr(
            f"A nota do compasso {edit.bar + 1} já não está no ficheiro como na partitura. Abra a música outra vez.",
            f"The note in bar {edit.bar + 1} is no longer in the file as on the score. Open the song again.",
        )
    )
    if edit.track >= len(song.tracks):
        raise gone
    track = song.tracks[edit.track]
    if track.isPercussionTrack or edit.string > len(track.strings) or edit.bar >= len(track.measures):
        raise gone
    beats = _voice_beats(track, edit.voice)  # through the whole song, for ties across bars
    measure = track.measures[edit.bar]
    voice_beats = measure.voices[edit.voice].beats if edit.voice < len(measure.voices) else []
    index = None
    if edit.beat < len(voice_beats):
        index = next(i for i, beat in enumerate(beats) if beat is voice_beats[edit.beat])
    note = _note_on(beats[index], edit.string) if index is not None else None
    if note is None or note.value != edit.expected:
        raise gone
    if edit.fret is not None and edit.fret > max(MAX_FRET, track.fretCount):
        raise ConversionError(
            tr(
                f"Traste inválido: {edit.fret} (máximo {max(MAX_FRET, track.fretCount)}).",
                f"Invalid fret: {edit.fret} (at most {max(MAX_FRET, track.fretCount)}).",
            )
        )
    for tied in _tied_chain(beats, index, edit.string):
        if edit.fret is not None:
            tied.value = edit.fret
            continue
        beat = tied.beat
        beat.notes.remove(tied)
        if not beat.notes:
            beat.status = gp.BeatStatus.rest


def _split(ticks: int) -> list[Length] | None:
    """Rest lengths adding up to `ticks`, longest first; triplets only for what plain lengths
    cannot make (a triplet beat leaves a triplet's worth). None when nothing adds up."""
    plain_ok = ticks % Length(32).duration().time == 0
    fillers = _FILLERS if plain_ok else _FILLERS[len(_VALUES) :] + _FILLERS[: len(_VALUES)]
    for filler in fillers:
        size = filler.duration().time
        if size <= ticks:
            rest = [] if size == ticks else _split(ticks - size)
            if rest is not None:
                return [filler, *rest]
    return None


def _rests(voice: gp.Voice, ticks: int) -> list[gp.Beat]:
    """Rest beats lasting `ticks`; ConversionError if no rest lengths add up."""
    lengths = _split(ticks) if ticks else []
    if lengths is None:
        raise _invalid()
    return [gp.Beat(voice, duration=length.duration(), status=gp.BeatStatus.rest) for length in lengths]


def _note_length(ticks: int) -> str:
    """A length counted in sixteenth notes, for a message ("2", "0.667" for a triplet's)."""
    return f"{ticks / (gp.Duration.quarterTime / 4):.3g}"


def _apply_length(song: gp.Song, edit: LengthEdit) -> None:
    gone = ConversionError(
        tr(
            f"A nota do compasso {edit.bar + 1} já não está no ficheiro como na partitura. Abra a música outra vez.",
            f"The note in bar {edit.bar + 1} is no longer in the file as on the score. Open the song again.",
        )
    )
    if edit.track >= len(song.tracks) or edit.bar >= len(song.tracks[edit.track].measures):
        raise gone
    measure = song.tracks[edit.track].measures[edit.bar]
    if edit.voice >= len(measure.voices) or edit.beat >= len(measure.voices[edit.voice].beats):
        raise gone
    voice = measure.voices[edit.voice]
    beat = voice.beats[edit.beat]
    if Length.of(beat.duration) != edit.expected:
        raise gone
    beat.duration = edit.length.duration()
    # The rests at the end of the bar (after this beat) are the bar's free time: taken out, then
    # given back as the time left over, in the longest rests that fit.
    while len(voice.beats) > edit.beat + 1 and not voice.beats[-1].notes:
        voice.beats.pop()
    room = measure.header.length - sum(b.duration.time for b in voice.beats)
    if room < 0:
        missing = -room
        raise ConversionError(
            tr(
                f"Não há tempo livre no compasso {edit.bar + 1}: faltam {_note_length(missing)} semicolcheia(s). "
                "Encurte primeiro outra nota deste compasso.",
                f"There is no free time in bar {edit.bar + 1}: {_note_length(missing)} sixteenth(s) missing. "
                "Shorten another note of this bar first.",
            )
        )
    voice.beats.extend(_rests(voice, room))


def apply_edits(data: bytes, edits: list[NoteEdit | LengthEdit]) -> bytes:
    """The Guitar Pro 3/4/5 file `data` with `edits` applied, written in its own version."""
    try:
        song = gp.parse(io.BytesIO(data))
    except Exception as exc:  # any malformed file: PyGuitarPro raises many kinds of errors
        raise ConversionError(
            tr(
                "Só é possível corrigir notas em ficheiros .gp5, .gp4 ou .gp3.",
                "Notes can only be corrected in .gp5, .gp4 or .gp3 files.",
            )
        ) from exc
    _repair_ties(song)
    for edit in edits:
        if isinstance(edit, LengthEdit):
            _apply_length(song, edit)
        else:
            _apply(song, edit)
    out = io.BytesIO()
    gp.write(song, out, version=song.versionTuple)
    return out.getvalue()
