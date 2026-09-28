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
    assert ghost.ghost and ghost.fret == 3
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
