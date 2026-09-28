"""Sections, lyrics, dynamics and written tuning."""

from app.converter import _apply_dynamics, _lyric_lines
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


def test_lyric_lines_start_at_their_bar_and_are_limited_to_five():
    systems = [_system(bars=(0, 50, 100), numbers=(n, n + 1), lyr=[(10, f"w{n}", False)]) for n in range(1, 30, 4)]
    lines = _lyric_lines(systems)
    assert len(lines) == 5
    assert lines[0][0] == 1 and all(start > 0 for start, _ in lines)
    hyphen = _system(lyr=[(10, "hap", True), (20, "pen", False)])
    assert _lyric_lines([hyphen]) == [(1, "hap-pen")]


def test_written_tuning_and_custom_octaves():
    assert _detect_tuning(["Tuning : D A D G B E"]) == ("E", "B", "G", "D", "A", "D")
    assert _detect_tuning(["Afinação: Drop D"]) == ("E", "B", "G", "D", "A", "D")
    assert _detect_tuning(["Tuning: half step down"])[0] == "D#"
    assert _detect_tuning(["Tuning is great"]) == ()
    assert labels_to_midi(["E", "C", "G", "C", "G", "C"]) == [64, 60, 55, 48, 43, 36]  # open C
    assert resolve_tuning("auto", 6, ["E", "B", "G", "D", "A", "D"])[0] == list(TUNINGS["drop_d"])
    tuning, warnings = resolve_tuning("auto", 6, ["E", "B", "G", "D"])
    assert tuning == list(TUNINGS["standard"]) and warnings
