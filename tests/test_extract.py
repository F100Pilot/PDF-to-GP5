from app.extract.ascii_tab import extract_ascii_systems
from app.extract.engraved_tab import extract_engraved_systems
from app.extract.pdf_reader import Segment, read_pages
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


def test_bend_starting_on_a_tied_stem_bends_the_tied_note():
    """ "10" (stem at 100) tied over to a stem with no fret (200); the bend curve starts there and
    is released later: a parenthesised 10 at the stem carries the bend and its release."""
    from app.extract.pdf_reader import Char, Page, Segment

    lines = [Segment(50, 550, 100 + 10 * i, 100 + 10 * i) for i in range(6)]
    bars = [Segment(x, x, 100, 150) for x in (50, 550)]
    stems = [Segment(x, x, 155, 175) for x in (100, 200)]
    note = [Char("1", 95, 100, 106, 114), Char("0", 100, 105, 106, 114)]
    curve, head, label = Segment(205, 228, 88, 108), Segment(224, 230, 82, 88), Char("½", 225, 229, 74, 81)
    release, down_head = Segment(230, 280, 84, 98), Segment(277, 283, 98, 104)
    page = Page(1, 600, 800, [*note, label], [*lines, *bars, *stems], [curve, head, release, down_head])
    events = sorted(extract_engraved_systems(page)[0].events, key=lambda e: e.x)
    assert [(e.x, e.fret, e.parenthesized, e.bend_semitones, e.bend_release) for e in events] == [
        (100, 10, False, 0, False),
        (200, 10, True, 1, True),
    ]


def test_pinch_harmonic_range_above_the_staff():
    dash = Segment(110, 300, 84, 84)
    chars = [*_text("PH", 95, 80), *_text("PHASE", 400, 80)]  # a word containing "PH" is not a mark
    systems = extract_engraved_systems(
        _signs_page(notes=((100, "3"), (350, "5"), (420, "7")), chars=chars, segments=[dash])
    )
    assert [(e.fret, e.harmonic) for e in sorted(systems[0].events, key=lambda e: e.x)] == [
        (3, "pinch"),
        (5, None),
        (7, None),
    ]


def test_vibrato_wiggle_line_above_staff():
    from app.extract.pdf_reader import Char

    # Music-font glyph boxes sit about one em below the drawn wiggle (drawn at y ~ 90).
    wiggles = [Char("", x, x + 5, 99, 109) for x in range(90, 130, 5)]
    event = extract_engraved_systems(_bend_page([], wiggles))[0].events[0]
    assert event.vibrato


def test_ascii_section_label_above_tab_block():
    systems, _ = _systems(ascii_tab_pdf([STANDARD], extra_lines=["[Chorus]"]))
    assert systems[0].sections == [(systems[0].start_x, "Chorus")]


def _slide_page(segments, curves=()):
    """Staff at y 100..150 (string 3 at 120); "7" at x 100..106 and "12" at x 130..142 on string 3."""
    from app.extract.pdf_reader import Char, Page, Segment

    lines = [Segment(50, 550, 100 + 10 * i, 100 + 10 * i) for i in range(6)]
    bars = [Segment(x, x, 100, 150) for x in (50, 550)]
    notes = [Char("7", 100, 106, 116, 124), Char("1", 130, 136, 116, 124), Char("2", 136, 142, 116, 124)]
    return Page(1, 600, 800, notes, [*lines, *bars, *segments], list(curves))


def _slide_events(page):
    return {e.fret: e for e in extract_engraved_systems(page)[0].events}


def test_engraved_legato_slide_between_notes_and_slide_out():
    from app.extract.pdf_reader import Segment
    from app.model import Link

    between = Segment(108, 127, 117, 123, rising=True)
    out = Segment(145, 153, 121, 128, rising=False)
    slur = Segment(103, 136, 110, 112)
    events = _slide_events(_slide_page([between, out], [slur]))
    assert events[12].link is Link.SLIDE_UP and events[12].slide_out == "down"
    assert events[7].link is None and events[7].slide_out is None


def test_engraved_slide_without_slur_is_a_shift_slide():
    from app.extract.pdf_reader import Segment
    from app.model import Link

    events = _slide_events(_slide_page([Segment(108, 127, 117, 123, rising=True)]))
    assert events[12].link is Link.SHIFT_SLIDE


def test_engraved_slide_into_note_from_below():
    from app.extract.pdf_reader import Segment

    events = _slide_events(_slide_page([Segment(90, 98, 119, 125, rising=True)]))
    assert events[7].slide_in == "below" and events[12].link is None


def test_engraved_long_stroke_beside_one_note_is_ignored():
    from app.extract.pdf_reader import Segment

    events = _slide_events(_slide_page([Segment(145, 190, 121, 128, rising=False)]))
    assert events[12].slide_out is None


TECHNIQUES = [
    "e|-/5---7\\---------------------|",
    "B|-7pb9---7pb9r7---------------|",
    "G|-<12>---5h7t12p7-------------|",
    "D|-----------------------------|",
    "A|-----------------------------|",
    "E|-----------------------------|",
]


def test_ascii_slide_in_out_prebend_harmonic_and_tapping():
    systems, warnings = _systems(ascii_tab_pdf([TECHNIQUES]))
    assert warnings == []
    events = _events_by_string(systems[0])
    slide_in, slide_out = events[1]
    assert (slide_in.fret, slide_in.slide_in, slide_in.link) == (5, "below", None)
    assert (slide_out.fret, slide_out.slide_out) == (7, "down")
    prebend, prebend_release = events[2]
    assert (prebend.fret, prebend.bend_pre, prebend.bend_semitones, prebend.bend_release) == (7, True, 2, False)
    assert (prebend_release.bend_pre, prebend_release.bend_release) == (True, True)
    harmonic, first, hammer, tap, pull = events[3]
    assert (harmonic.fret, harmonic.harmonic) == (12, "natural")
    assert first.harmonic is None and not first.tapped
    assert hammer.link.value == "h" and not hammer.tapped
    assert (tap.fret, tap.tapped) == (12, True)
    assert (pull.fret, pull.link.value, pull.tapped) == (7, "p", False)


def test_ascii_palm_mute_and_let_ring_lines_above_tab():
    tab = [
        "e|-0-0-0-0--0-0-0-0-----|",
        "B|----------------------|",
        "G|----------------------|",
        "D|----------------------|",
        "A|----------------------|",
        "E|----------------------|",
    ]
    marks = "   PM-----| let ring------"
    systems, warnings = _systems(ascii_tab_pdf([tab], extra_lines=[marks]))
    assert warnings == []
    notes = _events_by_string(systems[0])[1]
    assert [(e.palm_mute, e.let_ring) for e in notes] == [(True, False)] * 4 + [(False, True)] * 4


# --- Time signatures, repeats and voltas (MuseScore-style SMuFL glyphs) ---------------------------
# Staff lines at y 100..150 (spacing 10). Music-font glyphs are drawn about one em (size 40 here)
# above their text box, so a glyph drawn at y has its box at y + 36.


def _glyph(text, x, drawn_y, size=40):
    from app.extract.pdf_reader import Char

    return Char(text, x, x + 8, drawn_y + 0.9 * size, drawn_y + 1.9 * size, "Leland")


def _text(text, x, top, height=8):
    from app.extract.pdf_reader import Char

    return [Char(ch, x + 6 * i, x + 6 * i + 5, top, top + height, "Edwin-Roman") for i, ch in enumerate(text)]


def _signs_page(bar_xs=(50, 300, 550), notes=((100, "3"), (350, "5")), chars=(), segments=(), x1=550):
    from app.extract.pdf_reader import Char, Page, Segment

    lines = [Segment(50, x1, 100 + 10 * i, 100 + 10 * i) for i in range(6)]
    bars = [Segment(x, x, 100, 150) for x in bar_xs]
    fret_chars = [Char(fret, x, x + 6, 116, 124) for x, fret in notes]
    return Page(1, 600, 800, [*fret_chars, *chars], [*lines, *bars, *segments], [])


def test_engraved_time_signature_needs_two_stacked_rows():
    signature = [_glyph("", 310, 112), _glyph("", 310, 132)]  # 3/4 at the start of bar 2
    rest_count = [_glyph("", 150, 93)]  # "2" over a multi-bar rest: one row only
    (system,) = extract_engraved_systems(_signs_page(chars=[*signature, *rest_count]))
    assert system.time_signatures == [(310, 3, 4)]


def test_engraved_repeat_dots_count_and_volta():
    from app.extract.pdf_reader import Segment

    start_dots = [_glyph("", 304, 115), _glyph("", 304, 135)]
    end_dots = [_glyph("", 540, 115), _glyph("", 540, 135)]
    count = _text("x3", 525, 72)
    volta = _text("1.", 306, 60)
    bracket = Segment(302, 540, 57, 57)
    page = _signs_page(chars=[*start_dots, *end_dots, *count, *volta], segments=[bracket])
    (system,) = extract_engraved_systems(page)
    assert system.repeat_starts == [300]
    assert system.repeat_ends == [(550, 3)]
    assert system.endings == [(302, 540, (1,))]


def test_engraved_repeat_end_defaults_to_two_times_and_stray_dot_is_ignored():
    end_dots = [_glyph("", 540, 115), _glyph("", 540, 135)]
    stray = [_glyph("", 200, 125)]
    (system,) = extract_engraved_systems(_signs_page(chars=[*end_dots, *stray]))
    assert system.repeat_starts == [] and system.repeat_ends == [(550, 2)]


def test_engraved_repeat_after_clef_and_courtesy_signature_are_not_bars():
    start_dots = [_glyph("", 84, 115), _glyph("", 84, 135)]  # "|:" drawn after the clef
    courtesy = [_glyph("", 510, 112), _glyph("", 510, 132)]  # next line's 3/4, after the last bar
    page = _signs_page(bar_xs=(50, 80, 300, 500), chars=[*start_dots, *courtesy], x1=550)
    (system,) = extract_engraved_systems(page)
    assert [round(b) for b in system.bars] == [80, 300, 500]
    assert system.repeat_starts == [80]
    assert system.time_signatures == []


def test_ascii_repeat_signs_and_count():
    tab = [
        "e|:-0---3-:|-5---|   x3",
        "B|--1-------|-----|",
        "G|:-------- :|-----|".replace(" ", ""),
        "D|----------|-----|",
        "A|----------|-----|",
        "E|----------|-----|",
    ]
    (system,), _ = _systems(ascii_tab_pdf([tab]))
    bars = sorted(system.bars)
    assert system.repeat_starts == [bars[0]]
    assert system.repeat_ends == [(bars[1], 3)]


def test_ascii_count_after_a_line_without_signs_repeats_the_line():
    (system,), _ = _systems(ascii_tab_pdf([[line + "   x4" for line in STANDARD]]))
    bars = sorted(system.bars)
    assert system.repeat_starts == [bars[0]] and system.repeat_ends == [(bars[-1], 4)]


def test_engraved_segno_jump_and_tempo_marks_above_the_staff():
    segno = [_glyph("", 305, 80)]  # at the start of bar 2
    tempo = _text("=90", 310, 70)
    jump = _text("D.S.", 470, 84) + _text("al", 500, 84) + _text("Coda", 518, 84)  # ends at bar 2's end
    (system,) = extract_engraved_systems(_signs_page(chars=[*segno, *tempo, *jump]))
    assert system.signs == [(305, "Segno")]
    assert system.jumps == [(541, "Da Segno al Coda")]
    assert system.tempos == [(310, 90)]


def test_ascii_navigation_and_tempo_marks():
    tab = [line + ("   D.S. al Coda" if i == 0 else "") for i, line in enumerate(STANDARD)]
    (system,), _ = _systems(ascii_tab_pdf([tab], extra_lines=["Tempo 90           Fine"]))
    assert [name for _, name in system.jumps] == ["Da Segno al Coda"]
    assert [name for _, name in system.signs] == ["Fine"]
    assert [bpm for _, bpm in system.tempos] == [90]


def test_engraved_small_digits_are_grace_notes_of_the_next_note():
    """A small "14" hammered into "16" on the same string (H above): one note with a grace note.
    A small digit with no note on its string in the next column is dropped."""
    from app.extract.pdf_reader import Char

    grace = [Char("1", 86, 89.5, 117.5, 122.5), Char("4", 89.5, 93, 117.5, 122.5)]  # string 3, small
    lonely = [Char("9", 86, 89.5, 107.5, 112.5)]  # string 2, small
    main = [Char("1", 110, 116, 116, 124), Char("6", 116, 122, 116, 124)]
    hammer = Char("H", 97, 103, 88, 96)
    systems = extract_engraved_systems(
        _signs_page(notes=((350, "5"), (400, "7")), chars=[*grace, *lonely, *main, hammer])
    )
    events = sorted(systems[0].events, key=lambda e: e.x)
    assert [(e.string, e.fret) for e in events] == [(3, 16), (3, 5), (3, 7)]
    assert (events[0].grace_fret, events[0].grace_hammer, events[0].link) == (14, True, None)


def test_engraved_staccato_dot_above_the_column():
    systems = extract_engraved_systems(_signs_page(chars=[_glyph("\ue4a2", 99, 90)]))
    assert [(e.fret, e.staccato) for e in sorted(systems[0].events, key=lambda e: e.x)] == [(3, True), (5, False)]


def test_engraved_tie_arc_into_an_empty_bar():
    arc = Segment(110, 320, 114, 117)  # just above string 3, from the "3" across the bar line at 300
    page = _signs_page(notes=((100, "3"),), segments=[])
    page.curves.append(arc)
    assert extract_engraved_systems(page)[0].tied_bars == [300]
    page.chars.append(page.chars[0].__class__("5", 350, 356, 116, 124))  # a fret in the bar: not tied through
    assert extract_engraved_systems(page)[0].tied_bars == []


def test_wavy_arpeggio_line_sets_the_stroke_of_the_chord_after_it():
    from app.extract.pdf_reader import Char

    # Wiggle pieces stacked across strings 2-5 at x ~90, arrow on top: a downstroke (low to high).
    line = [Char("\ueaa9", 85, 95, y, y + 10) for y in (125, 135, 145)] + [Char("\ueaad", 85, 95, 112, 125)]
    chord = [(100, "3"), (350, "5")]
    systems = extract_engraved_systems(_signs_page(notes=chord, chars=line))
    assert [(e.fret, e.stroke) for e in sorted(systems[0].events, key=lambda e: e.x)] == [(3, "down"), (5, None)]
    arrow_below = [Char("\ueaa9", 85, 95, y, y + 10) for y in (112, 122, 132)] + [Char("\ueaad", 85, 95, 142, 152)]
    systems = extract_engraved_systems(_signs_page(notes=chord, chars=arrow_below))
    assert min(systems[0].events, key=lambda e: e.x).stroke == "up"


def test_sideways_music_glyph_is_placed_at_its_origin():
    from app.extract.pdf_reader import _x_span

    turned = {
        "text": "\ueaa9",
        "upright": False,
        "matrix": (0, 1, -1, 0, 246.0, 1485.7),
        "size": 22.0,
        "x0": 347.2,
        "x1": 447.2,
    }
    assert _x_span(turned) == (235.0, 257.0)
    assert _x_span({**turned, "text": "A"}) == (347.2, 447.2)  # rotated text keeps its box


def test_tie_arcs_reaching_parenthesized_notes():
    from app.extract.engraved_tab import _StaffLine, _tie_arrivals
    from app.model import TabEvent

    staff = [_StaffLine(y=100 + 7 * i, x0=50, x1=500) for i in range(6)]
    tied = TabEvent(x=200, string=4, fret=2, parenthesized=True)
    ghost = TabEvent(x=300, string=4, fret=2, parenthesized=True)
    first_on_line = TabEvent(x=60, string=3, fret=4, parenthesized=True)
    events = [TabEvent(x=120, string=4, fret=2), tied, ghost, first_on_line]
    curves = [
        Segment(125, 195, 117, 119),  # arc from the note at 120 to the one at 200
        Segment(52, 56, 112, 112),  # stub of a tie cut at the line's start
    ]
    _tie_arrivals(events, staff, curves, 7.0)
    assert (tied.tie_arc, ghost.tie_arc, first_on_line.tie_arc) == (True, False, True)


def test_song_and_artist_from_the_title_of_a_printed_web_page():
    from app.extract.metadata import detect_metadata
    from app.extract.pdf_reader import Page

    page = Page(0, 595, 842, [], [])
    info = {"Title": "_NIGHTFALL_ Tab by Varia _ Songsterr Tabs with Rhythm", "Author": "Paulo"}
    meta = detect_metadata([page], info)
    assert (meta.title, meta.artist) == ("NIGHTFALL", "Varia")  # not the computer's user
    info = {"Title": "OFFICIAL YOURE A GOD CHORDS & TABS by Vertical Horizon @ Ultimate-Guitar.Com"}
    assert detect_metadata([page], info).artist == "Vertical Horizon"
    assert detect_metadata([page], {"Title": "My Song", "Author": "Me"}).artist == "Me"
