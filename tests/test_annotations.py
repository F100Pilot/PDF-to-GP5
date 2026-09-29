"""Sections, lyrics, dynamics and written tuning."""

from app.converter import _apply_dynamics, _lyric_syllables, _lyrics_text
from app.extract.annotations import VELOCITIES, dynamics, lyrics, section_labels
from app.extract.metadata import _detect_tuning
from app.extract.pdf_reader import Char, Page, Segment
from app.model import TabEvent, TabSystem
from app.tunings import TUNINGS, labels_to_midi, resolve_tuning

SPACING = 10.0
TOP, BOTTOM = 100.0, 150.0


def _word(text: str, x: float, top: float, font: str = "Edwin-Roman", size: float = 8.0) -> list[Char]:
    return [Char(ch, x + 5 * i, x + 5 * i + 4.5, top, top + size, font) for i, ch in enumerate(text) if ch != " "]


def _page(chars=(), segments=()) -> Page:
    return Page(1, 600, 800, list(chars), list(segments), [])


def test_section_labels_are_bold_text_above_the_staff():
    chars = [
        *_word("Chorus", 60, 70, "Edwin-Bold"),
        *_word("Verse", 300, 70, "Edwin-Bold"),
        *_word("2", 330, 70, "Edwin-Bold"),
        *_word("=118", 150, 70, "Edwin-Bold"),  # tempo: no letters
        *_word("lyrics", 60, 170),  # below the staff, not bold
    ]
    assert section_labels(_page(chars), TOP, 50, 550, SPACING) == [(60, "Chorus"), (300, "Verse 2")]


def test_lyrics_join_syllables_on_hyphen_chars_and_drawn_dashes():
    chars = [
        *_word("hap", 60, 170),
        *_word("pened", 90, 170),
        *_word("te", 150, 170),
        *_word("–", 165, 170),
        *_word("qui", 180, 170),
        *_word("la", 210, 170),
    ]
    dash = Segment(76, 86, 174, 174)  # drawn hyphen between "hap" and "pened"
    let_ring = _word("let ring", 60, 160)
    result = lyrics(_page([*chars, *let_ring], [dash]), BOTTOM, 50, 550, SPACING)
    assert [(s, j) for _, s, j in result] == [
        ("hap", True),
        ("pened", False),
        ("te", True),
        ("qui", False),
        ("la", False),
    ]


def test_dynamics_from_glyph_and_standalone_text():
    glyph = Char("", 60, 70, BOTTOM + 30, BOTTOM + 50)  # mf, box one em below the drawn glyph
    text = _word("pp", 200, 160, "Edwin-BoldItalic")
    word_with_f = _word("of", 300, 160, "Edwin-Italic")  # not a dynamic
    marks = dynamics(_page([glyph, *text, *word_with_f]), TOP, BOTTOM, 50, 550, SPACING)
    assert marks == [(60, VELOCITIES["mf"]), (200, VELOCITIES["pp"])]


def _system(events=(), dyn=(), bars=(0.0, 100.0), numbers=(1,), lyr=()):
    return TabSystem(
        page=1,
        string_count=6,
        events=list(events),
        bars=list(bars),
        start_x=0,
        end_x=100,
        char_width=5.0,
        source="engraved",
        bar_numbers=list(numbers),
        dynamics=list(dyn),
        lyrics=list(lyr),
    )


def test_dynamics_carry_across_lines():
    first = _system([TabEvent(10, 1, 0), TabEvent(50, 1, 2)], dyn=[(40, 47)])
    second = _system([TabEvent(10, 1, 3)])
    _apply_dynamics([first, second])
    assert [e.velocity for e in first.events + second.events] == [None, 47, 47]


def test_lyric_syllables_keep_their_bar_and_place_in_the_bar():
    system = _system(bars=(0, 50, 100), numbers=(7, 8), lyr=[(25, "la", True), (60, "lo", False)])
    assert _lyric_syllables([system]) == [(7, 0.5, "la", True), (8, 0.2, "lo", False)]


def _measures(*bars):
    """Measures of quarter notes; a bar given as False is a whole-bar rest."""
    from app.model import ScoreBeat, ScoreMeasure, ScoreNote

    return [
        ScoreMeasure([ScoreBeat(8, [ScoreNote(1, 0)]) for _ in range(4)] if played else [ScoreBeat(32)])
        for played in bars
    ]


def test_lyrics_go_on_the_note_where_printed_and_skip_the_others():
    from app.model import Score

    score = Score(6, list(TUNINGS["standard"]), _measures(True, False, True), 4, 4)
    syllables = [
        (1, 0.0, "one", False),  # first beat
        (1, 0.5, "two", True),  # third beat, a word going on ("two-")
        (1, 0.6, "three", False),  # rest of the word: the next note (no skip after "-")
        (2, 0.0, "lost", False),  # bar 2 is a rest in this track: cannot be shown on a note
        (3, 0.3, "four", False),  # second beat of bar 3
    ]
    line, dropped = _lyrics_text(syllables, score)
    assert dropped == [2]
    # Chunks per note: one, (skip), two-, three | (skip), four
    assert line == (1, "one  two-three  four")


def test_written_tuning_and_custom_octaves():
    assert _detect_tuning(["Tuning : D A D G B E"]) == ("E", "B", "G", "D", "A", "D")
    assert _detect_tuning(["Afinação: Drop D"]) == ("E", "B", "G", "D", "A", "D")
    assert _detect_tuning(["Tuning: half step down"])[0] == "D#"
    assert _detect_tuning(["Tuning is great"]) == ()
    assert labels_to_midi(["E", "C", "G", "C", "G", "C"]) == [64, 60, 55, 48, 43, 36]  # open C
    assert resolve_tuning("auto", 6, ["E", "B", "G", "D", "A", "D"])[0] == list(TUNINGS["drop_d"])
    tuning, warnings = resolve_tuning("auto", 6, ["E", "B", "G", "D"])
    assert tuning == list(TUNINGS["standard"]) and warnings


def test_vocal_track_gives_every_syllable_its_own_note():
    from app.converter import _vocal_score

    syllables = [(1, 0.0, "one", False), (1, 0.5, "two", True), (1, 0.52, "three", False), (3, 0.25, "four", False)]
    vocal = _vocal_score(syllables, [(4, 4)] * 3)
    assert vocal.muted and len(vocal.measures) == 3
    for measure in vocal.measures:
        assert sum(beat.units for beat in measure.beats) == 32
    played = [[i for i, beat in enumerate(m.beats) if not beat.is_rest] for m in vocal.measures]
    assert [len(p) for p in played] == [3, 0, 1]
    line, dropped = _lyrics_text(syllables, vocal)
    assert dropped == [] and line == (1, "one two-three four")


def test_tracks_share_time_signatures_and_repeats_per_bar():
    from app.converter import _unify_bars
    from app.model import Score, ScoreBeat, ScoreMeasure, ScoreNote

    guitar = Score(
        6,
        [64] * 6,
        [
            ScoreMeasure([ScoreBeat(32)], time_signature=(4, 4)),
            ScoreMeasure([ScoreBeat(24, [ScoreNote(1, 0)])], time_signature=(3, 4), repeat_open=True, repeat_times=2),
            ScoreMeasure([ScoreBeat(24)], time_signature=(3, 4)),
        ],
        4,
        4,
    )
    bass = Score(
        4,
        [43] * 4,
        [
            ScoreMeasure([ScoreBeat(32)], time_signature=(4, 4)),
            ScoreMeasure([ScoreBeat(32)]),  # bar filled in with a rest (not in the PDF): 4/4 length
            ScoreMeasure([ScoreBeat(32, [ScoreNote(1, 5)])], time_signature=(4, 4)),  # read too long
        ],
        4,
        4,
    )
    cut = _unify_bars([guitar, bass], (4, 4))
    assert [m.time_signature for m in bass.measures] == [(4, 4), (3, 4), (3, 4)]
    assert [m.units for m in bass.measures] == [32, 24, 24]
    assert bass.measures[1].repeat_open and bass.measures[1].repeat_times == 2
    assert bass.measures[2].beats[0].notes and cut == [(1, 3)]


def test_technique_marks_on_the_lyrics_line_are_not_lyrics():
    chars = [
        *_word("la", 60, 170),
        *_word("da", 90, 170),
        *_word("let", 300, 170),
        *_word("ring", 330, 170),
        *_word("P.M.", 400, 170),
        *_word("Letring", 460, 170),
    ]
    assert [s for _, s, _ in lyrics(_page(chars), BOTTOM, 50, 550, SPACING)] == ["la", "da"]


def test_line_with_only_technique_marks_is_skipped():
    # Lines not starting with the mark itself, so only the word filter removes them.
    chars = [*_word("-", 40, 170), *_word("Let", 60, 170), *_word("Ring", 90, 170), *_word("PM", 300, 190)]
    assert lyrics(_page(chars), BOTTOM, 50, 550, SPACING) == []
