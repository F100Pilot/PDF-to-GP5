"""Correcting notes of a Guitar Pro file: another fret, a note removed, tied chains, refusals."""

import io
import json

import guitarpro as gp
import pytest
from fastapi.testclient import TestClient

from app import main
from app.converter import ConversionError
from app.gp5_writer import GP5_VERSION
from app.gp_edit import NoteEdit, _repair_ties, apply_edits, parse_edits


def _song(version=GP5_VERSION) -> bytes:
    """One 6-string track, two bars of 4/4 quarters in voice 0:
    bar 1: [s2 f5], [s2 f7 + s3 f6], [s1 f3], [s1 f3 tied]; bar 2: [s1 f3 tied], [s4 f0], rest, rest."""
    song = gp.Song()
    track = song.tracks[0]
    song.addMeasureHeader(gp.MeasureHeader())
    for header in song.measureHeaders[1:]:
        track.measures.append(gp.Measure(track, header))

    def beat(measure, notes):
        voice = measure.voices[0]
        made = gp.Beat(voice, status=gp.BeatStatus.normal if notes else gp.BeatStatus.rest)
        for string, fret, tie in notes:
            note = gp.Note(made, value=fret, string=string, type=gp.NoteType.tie if tie else gp.NoteType.normal)
            made.notes.append(note)
        voice.beats.append(made)

    first, second = track.measures
    for notes in ([(2, 5, False)], [(2, 7, False), (3, 6, False)], [(1, 3, False)], [(1, 3, True)]):
        beat(first, notes)
    for notes in ([(1, 3, True)], [(4, 0, False)], [], []):
        beat(second, notes)
    out = io.BytesIO()
    gp.write(song, out, version=version)
    return out.getvalue()


def _notes(data: bytes) -> list[list[list[tuple[int, int, str]]]]:
    song = gp.parse(io.BytesIO(data))
    _repair_ties(song)  # PyGuitarPro reads a tie at the start of a bar as fret 0
    return [
        [sorted((n.string, n.value, n.type.name) for n in b.notes) for b in m.voices[0].beats]
        for m in song.tracks[0].measures
    ]


def _edit(bar=0, beat=0, string=2, expected=5, fret=8, track=0, voice=0) -> NoteEdit:
    return NoteEdit(track=track, bar=bar, voice=voice, beat=beat, string=string, expected=expected, fret=fret)


def test_a_note_gets_another_fret():
    notes = _notes(apply_edits(_song(), [_edit(fret=8)]))
    assert notes[0][0] == [(2, 8, "normal")]
    assert notes[0][1] == [(2, 7, "normal"), (3, 6, "normal")]  # the rest stays


def test_one_note_of_a_chord_is_removed_and_a_lone_note_leaves_a_rest():
    edited = apply_edits(_song(), [_edit(beat=1, string=3, expected=6, fret=None), _edit(fret=None)])
    notes = _notes(edited)
    assert notes[0][1] == [(2, 7, "normal")]
    assert notes[0][0] == []
    assert gp.parse(io.BytesIO(edited)).tracks[0].measures[0].voices[0].beats[0].status == gp.BeatStatus.rest


@pytest.mark.parametrize("beat_at", [(0, 2), (0, 3), (1, 0)])
def test_a_tied_chain_changes_as_one_sound_from_any_of_its_notes(beat_at):
    bar, beat = beat_at
    notes = _notes(apply_edits(_song(), [_edit(bar=bar, beat=beat, string=1, expected=3, fret=12)]))
    assert [notes[0][2], notes[0][3], notes[1][0]] == [[(1, 12, "normal")], [(1, 12, "tie")], [(1, 12, "tie")]]


def test_a_tied_chain_is_removed_whole():
    notes = _notes(apply_edits(_song(), [_edit(bar=0, beat=3, string=1, expected=3, fret=None)]))
    assert notes[0][2] == notes[0][3] == notes[1][0] == []
    assert notes[1][1] == [(4, 0, "normal")]


def test_a_tie_across_the_bar_line_keeps_its_fret():
    """PyGuitarPro alone reads it as fret 0; the file is written back with the real fret."""
    edited = apply_edits(_song(), [_edit(fret=8)])
    raw = gp.parse(io.BytesIO(edited)).tracks[0].measures[1].voices[0].beats[0].notes[0]
    assert raw.type == gp.NoteType.tie
    assert _notes(edited)[1][0] == [(1, 3, "tie")]


def test_a_gp4_file_stays_gp4():
    edited = apply_edits(_song((4, 0, 0)), [_edit(fret=9)])
    assert edited.startswith(b"\x18FICHIER GUITAR PRO v4")
    assert _notes(edited)[0][0] == [(2, 9, "normal")]


@pytest.mark.parametrize(
    "edit",
    [
        _edit(expected=6),  # the score shows another fret than the file has
        _edit(string=5),  # no note on that string
        _edit(beat=4),
        _edit(bar=2),
        _edit(track=1),
        _edit(voice=1),
    ],
)
def test_a_note_not_in_the_file_as_on_the_score_is_refused(edit):
    with pytest.raises(ConversionError, match="compasso"):
        apply_edits(_song(), [edit])


def test_a_fret_past_the_neck_is_refused():
    with pytest.raises(ConversionError, match="Traste inválido"):
        apply_edits(_song(), [_edit(fret=31)])


def test_a_file_that_is_not_guitar_pro_3_to_5_is_refused():
    with pytest.raises(ConversionError, match=".gp5"):
        apply_edits(b"PK\x03\x04 not a gp5", [_edit()])


def test_the_edits_from_the_page_are_checked():
    good = {"track": 0, "bar": 1, "voice": 0, "beat": 2, "string": 3, "expected": 5, "fret": None}
    assert parse_edits([good]) == [NoteEdit(0, 1, 0, 2, 3, 5, None)]
    for bad in (
        [],
        {"track": 0},
        [{**good, "fret": "5"}],
        [{**good, "string": 0}],
        [{**good, "voice": 2}],
        [{**good, "expected": True}],
        [{**good, "extra": 1}],
        [good] * 501,
    ):
        with pytest.raises(ConversionError):
            parse_edits(bad)


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def _post(client, data, edits):
    return client.post(
        "/api/edit", files={"file": ("song.gp5", data, "application/octet-stream")}, data={"edits": edits}
    )


def test_the_server_corrects_a_note(client):
    edits = json.dumps([{"track": 0, "bar": 0, "voice": 0, "beat": 0, "string": 2, "expected": 5, "fret": 10}])
    response = _post(client, _song(), edits)
    assert response.status_code == 200, response.text
    assert _notes(response.content)[0][0] == [(2, 10, "normal")]


def test_the_server_refuses_what_it_cannot_correct(client):
    edit = {"track": 0, "bar": 0, "voice": 0, "beat": 0, "string": 2, "expected": 5, "fret": 10}
    assert _post(client, b"PK\x03\x04zip", json.dumps([edit])).status_code == 415
    assert _post(client, _song(), "not json").status_code == 422
    assert _post(client, _song(), json.dumps([{**edit, "expected": 4}])).status_code == 422
    response = client.post(
        "/api/edit",
        files={"file": ("song.gp5", _song(), "application/octet-stream")},
        data={"edits": json.dumps([edit])},
        headers={"X-App-Lang": "en"},
    )
    assert response.status_code == 200
    wrong = client.post(
        "/api/edit",
        files={"file": ("song.gp5", _song(), "application/octet-stream")},
        data={"edits": json.dumps([{**edit, "fret": 50}])},
        headers={"X-App-Lang": "en"},
    )
    assert wrong.status_code == 422
    assert wrong.json()["detail"] == "Invalid fret: 50 (at most 30)."


def _lengths(data: bytes, bar: int = 0) -> list[tuple[int, bool, bool, bool]]:
    """(value, dotted, triplet, rest) of each beat of voice 0 in `bar`."""
    song = gp.parse(io.BytesIO(data))
    return [
        (b.duration.value, b.duration.isDotted, b.duration.tuplet.enters == 3, not b.notes)
        for b in song.tracks[0].measures[bar].voices[0].beats
    ]


def _length_edit(beat, expected, length, bar=0):
    from app.gp_edit import Length, LengthEdit

    return LengthEdit(0, bar, 0, beat, Length(*expected), Length(*length))


def test_a_shorter_beat_leaves_a_rest_at_the_end_of_the_bar():
    edited = apply_edits(_song(), [_length_edit(0, (4,), (8,))])
    assert _lengths(edited) == [
        (8, False, False, False),
        (4, False, False, False),
        (4, False, False, False),
        (4, False, False, False),
        (8, False, False, True),
    ]


def test_a_longer_beat_takes_the_rests_at_the_end_of_the_bar_or_is_refused():
    # bar 2: [s1 f3 tied], [s4 f0], rest, rest — the half note takes both rests
    edited = apply_edits(_song(), [_length_edit(1, (4,), (2,), bar=1)])
    assert _lengths(edited, 1) == [(4, False, False, False), (2, False, False, False), (4, False, False, True)]
    dotted = apply_edits(_song(), [_length_edit(1, (4,), (4, True), bar=1)])
    assert _lengths(dotted, 1) == [
        (4, False, False, False),
        (4, True, False, False),
        (4, False, False, True),
        (8, False, False, True),
    ]
    with pytest.raises(ConversionError, match="4 semicolcheia"):
        apply_edits(_song(), [_length_edit(0, (4,), (2,))])  # bar 1 is full of notes


def test_triplets_keep_the_bar_whole_one_beat_at_a_time():
    """Three quarters made triplet eighths one by one: the bar's end is a triplet's rest while
    the group is incomplete, and plain rests once the three make a beat."""
    one = apply_edits(_song(), [_length_edit(0, (4,), (8, False, True))])
    assert _lengths(one)[-1] == (4, False, True, True)  # a triplet quarter's rest: 2 of 3 missing
    three = apply_edits(_song(), [_length_edit(i, (4,), (8, False, True)) for i in range(3)])
    assert _lengths(three) == [(8, False, True, False)] * 3 + [(4, False, False, False), (2, False, False, True)]


def test_a_length_edit_checks_the_beat_is_as_shown():
    with pytest.raises(ConversionError, match="compasso 1"):
        apply_edits(_song(), [_length_edit(0, (8,), (16,))])  # the score showed another length


def test_length_edits_from_the_page_are_checked():
    good = {
        "track": 0,
        "bar": 0,
        "voice": 0,
        "beat": 0,
        "expected_length": {"value": 4, "dotted": False, "triplet": False},
        "length": {"value": 8, "dotted": True, "triplet": False},
    }
    assert len(parse_edits([good])) == 1
    for bad in (
        {**good, "length": {"value": 3, "dotted": False, "triplet": False}},
        {**good, "length": {"value": 8, "dotted": "yes", "triplet": False}},
        {**good, "length": {"value": True, "dotted": False, "triplet": False}},
        {**good, "extra": 1},
    ):
        with pytest.raises(ConversionError):
            parse_edits([bad])
