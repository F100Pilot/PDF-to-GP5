import io

import guitarpro as gp
import pytest

from app.gp5_writer import TRACK_COLORS, SongInfo, sanitize_text, write_gp5
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


def test_roundtrip_grace_note_and_staccato():
    measure = ScoreMeasure(
        [
            ScoreBeat(8, [ScoreNote(3, 16, grace_fret=14, grace_hammer=True)]),
            ScoreBeat(8, [ScoreNote(3, 9, staccato=True)]),
            ScoreBeat(16, [ScoreNote(2, 5, grace_fret=3)]),
        ]
    )
    beats = _roundtrip(_score([measure])).tracks[0].measures[0].voices[0].beats
    grace = beats[0].notes[0].effect.grace
    assert (grace.fret, grace.transition) == (14, gp.GraceEffectTransition.hammer)
    assert beats[1].notes[0].effect.staccato and beats[1].notes[0].effect.grace is None
    assert beats[2].notes[0].effect.grace.transition == gp.GraceEffectTransition.none


def test_roundtrip_triplet():
    triplet = [ScoreBeat(4, [ScoreNote(3, fret)], tuplet=True) for fret in (9, 11, 9)]
    measure = ScoreMeasure([*triplet, ScoreBeat(8, [ScoreNote(3, 7)]), ScoreBeat(16)])
    beats = _roundtrip(_score([measure])).tracks[0].measures[0].voices[0].beats
    assert [(b.duration.value, b.duration.tuplet.enters, b.duration.tuplet.times) for b in beats] == [
        (8, 3, 2),
        (8, 3, 2),
        (8, 3, 2),
        (4, 1, 1),
        (2, 1, 1),
    ]


def test_roundtrip_pinch_and_artificial_harmonics():
    measure = ScoreMeasure(
        [ScoreBeat(16, [ScoreNote(3, 9, harmonic="pinch")]), ScoreBeat(16, [ScoreNote(1, 12, harmonic="artificial")])]
    )
    beats = _roundtrip(_score([measure], tuning="standard")).tracks[0].measures[0].voices[0].beats
    assert isinstance(beats[0].notes[0].effect.harmonic, gp.PinchHarmonic)
    artificial = beats[1].notes[0].effect.harmonic
    assert isinstance(artificial, gp.ArtificialHarmonic) and artificial.octave == gp.Octave.ottava


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
    colors = [(t.color.r, t.color.g, t.color.b) for t in song.tracks]
    assert colors == list(TRACK_COLORS[:2]) and colors[0] != colors[1]


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
    ("pre", "release", "expected", "points"),
    [
        (False, False, gp.BendType.bend, [(0, 0), (12, 4)]),
        (False, True, gp.BendType.bendRelease, [(0, 0), (3, 4), (6, 4), (9, 0)]),
        (True, False, gp.BendType.prebend, [(0, 4), (12, 4)]),
        (True, True, gp.BendType.prebendRelease, [(0, 4), (12, 0)]),
    ],
)
def test_bend_types(pre, release, expected, points):
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
    # The curve alphaTab plays (a three-point bend loses its middle point), and at most 4 points:
    # Guitar Pro 7/8 (.gp) keeps no more, and alphaTab's .gp export drops longer bends.
    assert [(p.position, p.value) for p in bend.points] == points


def test_more_than_seven_strings_rejected():
    score = Score(8, [64, 59, 55, 50, 45, 40, 35, 30], [ScoreMeasure([ScoreBeat(32)])], 4, 4)
    with pytest.raises(ValueError):
        write_gp5(score, SongInfo())


def test_roundtrip_markers_lyrics_and_velocity():
    from app.gp5_writer import LyricsInfo

    first = ScoreMeasure([ScoreBeat(32, [ScoreNote(1, 0, velocity=47)])], marker="Chorus")
    second = ScoreMeasure([ScoreBeat(32, [ScoreNote(1, 2)])])
    info = SongInfo(title="S", lyrics=LyricsInfo(track=1, lines=((1, "hap-pen to me"),)))
    song = gp.parse(io.BytesIO(write_gp5(_score([first, second]), info)))
    assert song.measureHeaders[0].marker.title == "Chorus" and song.measureHeaders[1].marker is None
    assert (song.lyrics.trackChoice, song.lyrics.lines[0].startingMeasure, song.lyrics.lines[0].lyrics) == (
        1,
        1,
        "hap-pen to me",
    )
    notes = [m.voices[0].beats[0].notes[0].velocity for m in song.tracks[0].measures]
    assert notes == [47, gp.Velocities.default]


def test_roundtrip_slides():
    measure = ScoreMeasure(
        [
            ScoreBeat(8, [ScoreNote(3, 7, slide_shift=True, slide_in="below")]),
            ScoreBeat(8, [ScoreNote(3, 9, slide=True)]),
            ScoreBeat(16, [ScoreNote(3, 12, slide_out="down")]),
        ]
    )
    beats = _roundtrip(_score([measure])).tracks[0].measures[0].voices[0].beats
    assert set(beats[0].notes[0].effect.slides) == {gp.SlideType.shiftSlideTo, gp.SlideType.intoFromBelow}
    assert beats[1].notes[0].effect.slides == [gp.SlideType.legatoSlideTo]
    assert beats[2].notes[0].effect.slides == [gp.SlideType.outDownwards]


def test_roundtrip_natural_harmonic_and_tapping():
    measure = ScoreMeasure(
        [ScoreBeat(16, [ScoreNote(3, 12, harmonic="natural")]), ScoreBeat(16, [ScoreNote(3, 12, tapped=True)])]
    )
    beats = _roundtrip(_score([measure])).tracks[0].measures[0].voices[0].beats
    assert isinstance(beats[0].notes[0].effect.harmonic, gp.NaturalHarmonic)
    assert beats[0].effect.slapEffect == gp.SlapEffect.none
    assert beats[1].effect.slapEffect == gp.SlapEffect.tapping


def test_roundtrip_repeats_voltas_and_time_signature_changes():
    def bar(units, signature, **marks):
        return ScoreMeasure([ScoreBeat(units, [ScoreNote(1, 3)])], time_signature=signature, **marks)

    measures = [
        bar(32, (4, 4), repeat_open=True),
        bar(32, (4, 4), repeat_times=3, endings=(1, 2)),
        bar(32, (4, 4), endings=(3,)),
        bar(24, (3, 4)),
        bar(12, (6, 16)),
    ]
    data = write_gp5(Score(6, list(TUNINGS["standard"]), measures, 4, 4), SongInfo(title="T", artist="A", tempo=100))
    headers = gp.parse(io.BytesIO(data)).measureHeaders
    assert [(h.timeSignature.numerator, h.timeSignature.denominator.value) for h in headers] == [
        (4, 4),
        (4, 4),
        (4, 4),
        (3, 4),
        (6, 16),
    ]
    assert [h.isRepeatOpen for h in headers] == [True, False, False, False, False]
    assert [h.repeatClose for h in headers] == [-1, 2, -1, -1, -1]  # PyGuitarPro counts the extra passes
    assert [h.repeatAlternative for h in headers] == [0, 0b011, 0b100, 0, 0]


def test_roundtrip_navigation_marks_and_tempo_changes():
    def bar(**marks):
        measure = ScoreMeasure([ScoreBeat(32, [ScoreNote(1, 3)])], time_signature=(4, 4))
        for name, value in marks.items():
            setattr(measure, name, value)
        return measure

    measures = [
        bar(),
        bar(sign="Segno", tempo=90),
        bar(jump="Da Coda"),
        bar(jump="Da Segno al Coda", tempo=140),
        bar(sign="Coda"),
    ]
    data = write_gp5(Score(6, list(TUNINGS["standard"]), measures, 4, 4), SongInfo(title="T", artist="A", tempo=120))
    song = gp.parse(io.BytesIO(data))
    headers = song.measureHeaders
    assert [h.direction.name if h.direction else None for h in headers] == [None, "Segno", None, None, "Coda"]
    assert [h.fromDirection.name if h.fromDirection else None for h in headers] == [
        None,
        None,
        "Da Coda",
        "Da Segno al Coda",
        None,
    ]
    tempos = [
        m.voices[0].beats[0].effect.mixTableChange.tempo.value if m.voices[0].beats[0].effect.mixTableChange else None
        for m in song.tracks[0].measures
    ]
    assert tempos == [None, 90, None, 140, None] and song.tempo == 120
