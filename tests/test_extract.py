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
