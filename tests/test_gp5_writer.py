import io

import guitarpro as gp
import pytest

from app.gp5_writer import SongInfo, sanitize_text, write_gp5
from app.model import Score, ScoreBeat, ScoreMeasure, ScoreNote
from app.tunings import TUNINGS


def _score(measures, numerator=4, denominator=4, tuning="drop_d"):
    return Score(6, list(TUNINGS[tuning]), measures, numerator, denominator)


INFO = SongInfo(title="Song", artist="Me", tempo=97)


def _roundtrip(score, info=INFO):
    return gp.parse(io.BytesIO(write_gp5(score, info)))


def test_roundtrip_metadata_tuning_and_notes():
    measure = ScoreMeasure(
        [
            ScoreBeat(8, [ScoreNote(1, 0, hammer=True), ScoreNote(6, 0)]),
            ScoreBeat(8, [ScoreNote(1, 2)]),
            ScoreBeat(8, [ScoreNote(3, 7, bend_semitones=2), ScoreNote(4, 0, dead=True)]),
            ScoreBeat(8),
        ]
    )
    song = _roundtrip(_score([measure]))
    assert song.versionTuple == (5, 1, 0)
    assert (song.title, song.artist, song.tempo) == ("Song", "Me", 97)
    track = song.tracks[0]
    assert [s.value for s in track.strings] == list(TUNINGS["drop_d"])
    beats = track.measures[0].voices[0].beats
    assert [b.duration.value for b in beats] == [4, 4, 4, 4]
    assert beats[3].status == gp.BeatStatus.rest
    first = {n.string: n for n in beats[0].notes}
    assert first[1].effect.hammer and first[6].value == 0
    third = {n.string: n for n in beats[2].notes}
    assert third[3].effect.bend.value == 100
    assert third[4].type == gp.NoteType.dead


def test_roundtrip_odd_time_signature_and_dotted():
    measure = ScoreMeasure([ScoreBeat(12, [ScoreNote(2, 1)]), ScoreBeat(12, [ScoreNote(2, 3)])])
    song = _roundtrip(_score([measure], numerator=6, denominator=8))
    header = song.measureHeaders[0]
    assert (header.timeSignature.numerator, header.timeSignature.denominator.value) == (6, 8)
    assert all(b.duration.isDotted and b.duration.value == 4 for b in song.tracks[0].measures[0].voices[0].beats)


def test_empty_score_rejected():
    with pytest.raises(ValueError):
        write_gp5(_score([]), SongInfo())


def test_sanitize_text_strips_control_and_unencodable():
    assert sanitize_text("Ol\u00e1\x00\x1b[31m \u6f22 Song") == "Ol\u00e1[31m  Song"
    assert len(sanitize_text("a" * 500)) == 100


def test_roundtrip_let_ring_palm_mute_and_tie():
    measure = ScoreMeasure(
        [
            ScoreBeat(16, [ScoreNote(4, 0, let_ring=True, palm_mute=True)]),
            ScoreBeat(16, [ScoreNote(4, 0, tie=True, let_ring=True)]),
        ]
    )
    beats = _roundtrip(_score([measure])).tracks[0].measures[0].voices[0].beats
    first, second = beats[0].notes[0], beats[1].notes[0]
    assert first.effect.letRing and first.effect.palmMute
    assert second.type == gp.NoteType.tie and second.effect.letRing


def test_multi_track_song_structure():
    guitar = _score([ScoreMeasure([ScoreBeat(32, [ScoreNote(1, 0)])])])
    bass = Score(
        4, list(TUNINGS["bass_4"]), [ScoreMeasure([ScoreBeat(32, [ScoreNote(4, 3)])])], 4, 4, name="Bass", instrument=33
    )
    song = _roundtrip([guitar, bass])
    assert [t.name for t in song.tracks] == ["Guitar", "Bass"]
    assert [len(t.strings) for t in song.tracks] == [6, 4]
    assert song.tracks[1].measures[0].voices[0].beats[0].notes[0].value == 3


def test_tracks_must_have_equal_measure_counts_and_limit():
    one = _score([ScoreMeasure([ScoreBeat(32)])])
    two = _score([ScoreMeasure([ScoreBeat(32)]), ScoreMeasure([ScoreBeat(32)])])
    with pytest.raises(ValueError):
        write_gp5([one, two], SongInfo())
    with pytest.raises(ValueError):
        write_gp5([one] * 8, SongInfo())


def test_roundtrip_stroke():
    measure = ScoreMeasure([ScoreBeat(32, [ScoreNote(1, 0, stroke="down"), ScoreNote(2, 1, stroke="down")])])
    beat = _roundtrip(_score([measure])).tracks[0].measures[0].voices[0].beats[0]
    assert beat.effect.stroke.direction == gp.BeatStrokeDirection.down


@pytest.mark.parametrize(
    ("pre", "release", "expected"),
    [
        (False, False, gp.BendType.bend),
        (False, True, gp.BendType.bendRelease),
        (True, False, gp.BendType.prebend),
        (True, True, gp.BendType.prebendRelease),
    ],
)
def test_bend_types(pre, release, expected):
    note = ScoreNote(2, 10, bend_semitones=2, bend_pre=pre, bend_release=release)
    bend = (
        _roundtrip(_score([ScoreMeasure([ScoreBeat(32, [note])])]))
        .tracks[0]
        .measures[0]
        .voices[0]
        .beats[0]
        .notes[0]
        .effect.bend
    )
    assert bend.type == expected and bend.value == 100


def test_more_than_seven_strings_rejected():
    score = Score(8, [64, 59, 55, 50, 45, 40, 35, 30], [ScoreMeasure([ScoreBeat(32)])], 4, 4)
    with pytest.raises(ValueError):
        write_gp5(score, SongInfo())
