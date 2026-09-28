from app.extract.ascii_tab import extract_ascii_systems
from app.extract.engraved_tab import extract_engraved_systems
from app.extract.pdf_reader import read_pages
from tests.pdf_factory import ascii_tab_pdf, engraved_tab_pdf

STANDARD = [
    "e|-0---3h5---7p5-|",
    "B|---------------|",
    "G|-----------4/6-|",
    "D|-5b7r5--x------|",
    "A|---(3)--7~-----|",
    "E|---------------|",
]


def _systems(pdf: bytes):
    page = read_pages(pdf, max_pages=5)[0]
    return extract_ascii_systems(page)


def _events_by_string(system):
    result = {}
    for event in sorted(system.events, key=lambda e: e.x):
        result.setdefault(event.string, []).append(event)
    return result


def test_ascii_detects_system_labels_and_bars():
    systems, warnings = _systems(ascii_tab_pdf([STANDARD], extra_lines=["Intro - Some Song", "Tuning: standard"]))
    assert warnings == []
    assert len(systems) == 1
    system = systems[0]
    assert system.string_count == 6
    assert system.labels == ["e", "B", "G", "D", "A", "E"]
    assert len(system.bars) == 2


def test_ascii_techniques():
    events = _events_by_string(_systems(ascii_tab_pdf([STANDARD]))[0][0])
    high = events[1]
    assert [e.fret for e in high] == [0, 3, 5, 7, 5]
    assert high[2].link.value == "h" and high[4].link.value == "p"
    assert events[3][1].link.value == "/"
    bend, dead = events[4]
    assert (bend.fret, bend.bend_semitones, bend.bend_release) == (5, 2, True)
    assert dead.dead
    ghost, vib = events[5]
    assert ghost.parenthesized and ghost.fret == 3
    assert vib.vibrato and vib.fret == 7


def test_ascii_ignores_prose_and_trailing_repeat_marks():
    tab = [line + "   x4" for line in STANDARD]
    systems, _ = _systems(ascii_tab_pdf([tab], extra_lines=["This is just text - not a tab ---"]))
    assert len(systems) == 1
    assert not any(e.fret == 4 and e.x > systems[0].bars[-1] for e in systems[0].events)


def test_ascii_bass_four_strings_and_two_systems():
    bass = ["G|-----|", "D|-----|", "A|-3-5-|", "E|-----|"]
    bass = [line.replace("|", "|------", 1) for line in bass]
    systems, _ = _systems(ascii_tab_pdf([bass, bass]))
    assert [s.string_count for s in systems] == [4, 4]


def test_engraved_staff_and_numbers():
    page = read_pages(engraved_tab_pdf([[(1, 0), (2, 12)], [(6, 3)]]), max_pages=5)[0]
    assert extract_ascii_systems(page)[0] == []
    systems = extract_engraved_systems(page)
    assert len(systems) == 1
    system = systems[0]
    assert system.string_count == 6
    assert sorted((e.string, e.fret) for e in system.events) == [(1, 0), (2, 12), (6, 3)]
    assert len(system.bars) == 3


def _engraved(pdf: bytes):
    return [s for page in read_pages(pdf, max_pages=5) for s in extract_engraved_systems(page)]


def test_engraved_keeps_empty_staves_and_segmented_lines():
    systems = _engraved(engraved_tab_pdf([[[(1, 0)], [(2, 1)], [(3, 2)]], [[], [], []]]))
    assert [len(s.events) for s in systems] == [3, 0]
    assert all(s.start_x == 60.0 for s in systems)  # segments merged regardless of drawing order
    assert [len(s.bars) for s in systems] == [4, 4]


def test_engraved_short_final_staff():
    systems = _engraved(engraved_tab_pdf([[[(1, 0)], [(1, 2)]], [[(2, 3)]]], widths=[480.0, 90.0]))
    assert len(systems) == 2 and systems[1].events[0].fret == 3


def test_engraved_frets_survive_many_small_digits_on_page():
    systems = _engraved(engraved_tab_pdf([[(1, 5), (2, 7)]], measure_number_noise=400))
    assert sorted(e.fret for e in systems[0].events) == [5, 7]


def test_engraved_reads_bar_numbers():
    systems = _engraved(engraved_tab_pdf([[[(1, 0)], [], [(1, 2)]]], bar_numbers=[[7, 8, 12]]))
    assert systems[0].bar_numbers == [7, 8, 12]


def test_ascii_tolerates_unknown_symbols_and_rejects_prose():
    tab = [line.replace("-0---", "-0v--") for line in STANDARD]
    tab[3] = "D|-5b7r5--x--T[2]---------|"
    systems, _ = _systems(ascii_tab_pdf([tab], extra_lines=["---- Chorus ---- (play twice) ----"]))
    assert len(systems) == 1 and systems[0].string_count == 6


def test_ascii_double_spaced_lines():
    systems, _ = _systems(ascii_tab_pdf([STANDARD, STANDARD], line_spacing=2.2))
    assert [s.string_count for s in systems] == [6, 6]


def test_ascii_systems_without_blank_line_are_split_by_labels():
    systems, _ = _systems(ascii_tab_pdf([STANDARD + STANDARD]))
    assert [s.string_count for s in systems] == [6, 6]


def test_ascii_reports_incomplete_tab_lines():
    _, warnings = _systems(ascii_tab_pdf([STANDARD[:3]]))
    assert any("ignoradas" in w for w in warnings)


def test_engraved_parentheses_drawn_as_curves():
    systems = _engraved(engraved_tab_pdf([[(4, 0), (3, 2), (4, 0, "("), (2, 12, "(")]]))
    marked = sorted((e.fret, e.parenthesized) for e in systems[0].events)
    assert marked == [(0, False), (0, True), (2, False), (12, True)]


def test_engraved_pull_off_letter_links_the_note_pair():
    systems = _engraved(engraved_tab_pdf([[(3, 4), (3, 2, "P"), (4, 2), (3, 4)]], widths=[120.0]))
    linked = [(e.string, e.fret) for e in systems[0].events if e.link is not None]
    assert linked == [(3, 2)]
    assert next(e for e in systems[0].events if e.link).link.value == "p"


def test_engraved_let_ring_and_palm_mute_ranges():
    staves = [[[(4, 2), (4, 2), (4, 2), (4, 2)]], [[(1, 0), (1, 0)]]]
    pdf = engraved_tab_pdf(staves, ranges=[(0, "P.M.", 60, 300), (1, "let ring", 60, 540)])
    first, second = _engraved(pdf)
    assert [e.palm_mute for e in sorted(first.events, key=lambda e: e.x)] == [True, True, False, False]
    assert not any(e.let_ring for e in first.events)
    assert all(e.let_ring and not e.palm_mute for e in second.events)


def _staff_page(extra_segments=(), chars=()):
    from app.extract.pdf_reader import Char, Page, Segment

    lines = [Segment(50, 550, 100 + 10 * i, 100 + 10 * i) for i in range(6)]
    bars = [Segment(x, x, 100, 150) for x in (50, 300, 550)]
    notes = [Char("3", 100, 106, 120 - 4, 120 + 4), Char("5", 350, 356, 120 - 4, 120 + 4)]
    return Page(1, 600, 800, [*notes, *chars], [*lines, *bars, *extra_segments], [])


def test_multi_bar_rest_bar_inside_staff_does_not_split_it():
    from app.extract.pdf_reader import Segment

    page = _staff_page([Segment(60, 280, 125, 125)])  # thick rest bar drawn as a line between strings 3 and 4
    systems = extract_engraved_systems(page)
    assert len(systems) == 1 and systems[0].string_count == 6


def test_strum_arrow_is_not_a_bar_line_and_sets_stroke():
    from app.extract.pdf_reader import Char, Segment

    arrow = Segment(340, 340, 98, 158)  # spans the staff like a bar line
    head = Char("", 336, 344, 160, 180)
    systems = extract_engraved_systems(_staff_page([arrow], [head]))
    assert [round(b) for b in systems[0].bars] == [50, 300, 550]
    assert {(e.fret, e.stroke) for e in systems[0].events} == {(3, None), (5, "down")}


def _bend_page(arrow_segments, chars=()):
    """Staff at y 100..150 (string 1 at 100); one note "10" on string 2 at x 100."""
    from app.extract.pdf_reader import Char, Page, Segment

    lines = [Segment(50, 550, 100 + 10 * i, 100 + 10 * i) for i in range(6)]
    bars = [Segment(x, x, 100, 150) for x in (50, 550)]
    note = [Char("1", 95, 100, 106, 114), Char("0", 100, 105, 106, 114)]
    return Page(1, 600, 800, [*note, *chars], [*lines, *bars], list(arrow_segments))


def test_bend_arrow_with_amount():
    from app.extract.pdf_reader import Char, Segment

    curve, head = Segment(108, 118, 88, 107), Segment(114, 120, 82, 88)
    label = Char("½", 115, 119, 74, 81)
    event = extract_engraved_systems(_bend_page([curve, head], [label]))[0].events[0]
    assert (event.fret, event.bend_semitones, event.bend_pre, event.bend_release) == (10, 1, False, False)


def test_prebend_and_release():
    from app.extract.pdf_reader import Segment

    straight, up_head = Segment(100, 100, 88, 106), Segment(97, 103, 82, 88)
    release, down_head = Segment(100, 160, 84, 98), Segment(157, 163, 98, 104)
    event = extract_engraved_systems(_bend_page([release, down_head, straight, up_head]))[0].events[0]
    assert (event.bend_semitones, event.bend_pre, event.bend_release) == (2, True, True)


def test_vibrato_wiggle_line_above_staff():
    from app.extract.pdf_reader import Char

    # Music-font glyph boxes sit about one em below the drawn wiggle (drawn at y ~ 90).
    wiggles = [Char("", x, x + 5, 99, 109) for x in range(90, 130, 5)]
    event = extract_engraved_systems(_bend_page([], wiggles))[0].events[0]
    assert event.vibrato
