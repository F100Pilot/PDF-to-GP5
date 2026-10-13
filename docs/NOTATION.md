# Notation register: notes and techniques

[Português](NOTACAO.md) · **English**

A list of everything a tablature can contain and the state of its conversion to GP5.
It works as an implementation plan: every new song with different notation updates this table.

## Legend

| Status | Meaning |
|---|---|
| ✅ | Implemented and tested |
| 🟡 | Partial (see notes) |
| ⬜ | To be implemented |
| ⛔ | No equivalent in the GP5 format |

Columns:
- **Text**: tab as text (`e|--0--3h5--|`).
- **Engraved**: tab exported from an editor (MuseScore, Guitar Pro, TuxGuitar…).
- **GP5**: the GP5 format (via PyGuitarPro) can store the information.
- **Seen in**: real PDF where the notation has already appeared (for tests). "—" = no example yet, **send a PDF**.

## How to move forward

1. Send a PDF that contains the missing notation, stating the bar and the expected result (a reference image helps).
2. Analyse how the editor draws it in the PDF (text, SMuFL glyph, lines, curves).
3. Implement it, with an automatic test that reproduces the geometry.
4. Update this table and `CHANGELOG.md`.

---

## 1. Rhythm and duration

| Notation | Text | Engraved | GP5 | Seen in | Notes |
|---|---|---|---|---|---|
| Duration from note spacing | ✅ | ✅ | ✅ | Happen To Me | Estimate when there is no rhythm notation |
| Stems + beams (eighth, sixteenth, thirty-second) | ⛔ | ✅ | ✅ | Happen To Me | Beams = 1/2/3 lines |
| Flag (single eighth note ♪) | ⛔ | ✅ | ✅ | Happen To Me (Guitar 2) | SMuFL glyphs `U+E240`–`E245` |
| Quarter note (stem without beam) | ⛔ | ✅ | ✅ | Happen To Me | |
| Half note (short stem) | ⛔ | ✅ | ✅ | Happen To Me (Guitar 2) | |
| Whole note (no stem) | ⛔ | ✅ | ✅ | Happen To Me | |
| Dotted note | ⛔ | ✅ | ✅ | Happen To Me (Guitar 2) | Glyph `U+E1E7` or a drawn dot |
| Double-dotted note | ⛔ | ⬜ | ⛔ | — | GP5 only has a single dot |
| Triplets and other tuplets (3:2, 5:4, 6:4…) | ⬜ | 🟡 | ✅ | — | Detected, but the bar falls back to an estimate |
| Rests (whole…thirty-second) | ⛔ | ✅ | ✅ | Happen To Me | Glyphs `U+E4E3`–`E4E8` |
| Dotted rest | ⛔ | ✅ | ✅ | — | Implemented without a real example |
| Empty bar (bar rest) | ✅ | ✅ | ✅ | Happen To Me | |
| Multi-bar rest (thick bar + number) | ⬜ | ✅ | ✅ | Happen To Me | From the bar numbers |
| Tie | 🟡 | ✅ | ✅ | Happen To Me | Text: only `(n)` |
| Tied note with stem only (hidden fret) | ⛔ | ✅ | ✅ | Happen To Me (Guitar 2) | |
| Fixed duration (tabs without rhythm) | ✅ | ✅ | ✅ | — | "Fixed duration" option |
| Grace note | ⬜ | ⬜ | ✅ | — | With slide/bend/hammer transition |
| Swing / triplet feel | ⬜ | ⬜ | ✅ | — | Text "Swing", "♪♪ = ♪³♪" |
| Pickup bar (incomplete bar at the start) | ⬜ | ⬜ | 🟡 | — | GP5 has no concept of its own |

## 2. Bar, tempo and structure

| Notation | Text | Engraved | GP5 | Seen in | Notes |
|---|---|---|---|---|---|
| Bar lines | ✅ | ✅ | ✅ | Happen To Me | |
| Bar numbers (alignment between tracks) | ⛔ | ✅ | — | Happen To Me | |
| Time signature (4/4, 6/8…) | ⬜ | ✅ | ✅ | Happen To Me | Glyphs `U+E080`–`E08B`; not yet in text |
| Time signature change mid-song | ⬜ | ✅ | ✅ | — | Stacked SMuFL digits (MuseScore); the cautionary signature at the end of the line and the number of multi-bar rests are ignored. Text tabs: no |
| Initial tempo (♩ = 118, "Tempo: 120", "120 bpm") | ✅ | ✅ | ✅ | Happen To Me | |
| Tempo change mid-song | ✅ | ✅ | ✅ | Happen To Me (`♩ = 118` in bar 1) | "♩ = 90", "= 90", "Tempo 90", "90 bpm" above the tab; the mark in bar 1 is the song's tempo. No rit./accel. |
| Key signature | ⬜ | ⬜ | ✅ | — | |
| Repeats `‖: :‖` and "x3" | ✅ `\|: :\|` | ✅ | ✅ | — | Engraved: SMuFL repeat dots and "x3" above; text: `\|:` `:\|` `\|*` `\|o` and "x3" after the line (without signs: the whole line repeats). Without a number: 2 times. "Written out" option (Rocksmith): bars copied in playback order |
| 1st/2nd endings (volta brackets) | ⬜ | ✅ | ✅ | — | "1.", "2.", "1., 2." above the staff with the bracket line |
| Coda, Segno, D.C., D.S., Fine | ✅ | ✅ | ✅ | — | Engraved: SMuFL Segno/Coda symbols and text ("D.S. al Coda", "To Coda", "Fine"…); text: above the tab or after the line. Playback order is the same as alphaTab's; GP5 stores each sign once |
| Sections (Intro, Verse, Chorus…) → markers | ✅ | ✅ | ✅ | Happen To Me | Engraved: bold text above the staff; text: `[Chorus]`, `Verse 2:` |

## 3. Notes

| Notation | Text | Engraved | GP5 | Seen in | Notes |
|---|---|---|---|---|---|
| Fret (0–29) and chords | ✅ | ✅ | ✅ | Happen To Me | |
| Dead note `x` | ✅ | ✅ | ✅ | — | |
| Note in parentheses `(0)` | ✅ | ✅ | ✅ | Happen To Me | Same fret as the note sounding on the string on the previous beat → tie (sustain; in GP the fret is not repeated in the tab). A different fret, or the string silent on the previous beat → ghost note. In MuseScore PDFs (ties drawn as arcs, also cut off at the start of the line) there is a tie only when an arc reaches the note: `(2)(2)` without an arc are two notes |
| Ghost note | ✅ | ✅ | ✅ | — | Parentheses with a fret different from the previous one |
| Accent `>` | ⬜ | ⬜ | ✅ | — | |
| Heavy accent `^` (marcato) | ⬜ | ⬜ | ✅ | — | |
| Staccato `.` | ⬜ | ⬜ | ✅ | — | |
| Fingering (left hand 1–4, right hand p-i-m-a) | ⬜ | ⬜ | ✅ | — | |
| Dynamics (ppp … fff) | ⬜ | ✅ | ✅ | Happen To Me (`f`) | Note velocity up to the next dynamic; SMuFL glyphs or italic letters |
| Crescendo / decrescendo (hairpins) | ⬜ | ⬜ | ⛔ | Happen To Me | Approximate with dynamics |

## 4. Left-hand techniques

| Notation | Text | Engraved | GP5 | Seen in | Notes |
|---|---|---|---|---|---|
| Hammer-on | ✅ `h` | ✅ `H` | ✅ | — | Engraved: letter H above |
| Pull-off | ✅ `p` | ✅ `P` | ✅ | Happen To Me | |
| Slur only (no H/P) | ⛔ | ⬜ | ✅ | — | Arc between notes on different frets |
| Legato slide | ✅ `/` `\` `s` | ✅ | ✅ | Happen To Me (Guitar 2, 3) | Engraved: oblique line between notes with an arc above |
| Shift slide (with attack) | ⬜ | ✅ | ✅ | — | Engraved: oblique line between notes without an arc. Text: "sl." / "S" |
| Slide in (from below / from above) | ✅ `/5` `\5` | ✅ | ✅ | — | `/5`, `\5`; engraved: short stroke before the note |
| Slide out (down / up) | ✅ `5\` `5/` | ✅ | ✅ | Happen To Me (Guitar 2, 3) | `5\`, `5/`; engraved: short stroke after the note |
| Bend (½, 1, 1½, 2) | ✅ `7b9` | ✅ | ✅ | Happen To Me (Guitar 4) | |
| Bend + release | ✅ `7b9r7` | ✅ | ✅ | Happen To Me (Guitar 4) | |
| Pre-bend | ✅ `7pb9` | ✅ | ✅ | Happen To Me (Guitar 4) | Straight arrow |
| Pre-bend + release | ✅ `7pb9r7` | ✅ | ✅ | Happen To Me (Guitar 4) | |
| Held bend (on a tied note) | ⛔ | ✅ | ✅ | Happen To Me (Guitar 4) | |
| Bend + release + bend | ⬜ | ⬜ | ✅ | — | |
| Vibrato | ✅ `~` | ✅ | ✅ | Happen To Me (Guitar 4) | Engraved: wavy line |
| Wide vibrato (whammy bar) | ⬜ | ⬜ | ✅ | — | Thicker wavy line |
| Trill | ⬜ `tr` | ⬜ | ✅ | — | |
| Left-hand tapping | ⬜ | ⬜ | 🟡 | — | |

## 5. Right-hand and strum techniques

| Notation | Text | Engraved | GP5 | Seen in | Notes |
|---|---|---|---|---|---|
| Palm mute (P.M.) | ✅ `PM---` | ✅ | ✅ | Happen To Me | Text: own line above the tab (`PM----|`, `P.M. - - -`, `PM PM`) |
| Let ring | ✅ `let ring---` | ✅ | ✅ | Happen To Me | Text: own line above the tab (also `l.r.`) |
| Strum ↑ ↓ (brush) | ⬜ | ✅ | ✅ | Happen To Me (Acoustic) | Up arrow = downstroke (to be confirmed in GP) |
| Downstroke ⊓ / upstroke V | ⬜ | ⬜ | ✅ | — | |
| Tremolo picking | ⬜ | ⬜ | ✅ | — | Strokes on the stem |
| Tapping `T` | ✅ `t12` | ⬜ | ✅ | — | Text: `t`/`T` before the fret |
| Slap `S` / Pop `P` (bass) | ⬜ | ⬜ | ✅ | — | Note: `P` also means pull-off |
| Flamenco rasgueado (rasg.) | ⬜ | ⬜ | ✅ | — | |
| Arpeggio (vertical wavy line) | ⬜ | ⬜ | 🟡 | — | Approximate with brush |
| Fade in / volume swell | ⬜ | ⬜ | ✅ | — | |
| Whammy bar (dip, dive, release) | ⬜ | ⬜ | ✅ | — | "w/bar" |

## 6. Harmonics

| Notation | Text | Engraved | GP5 | Seen in | Notes |
|---|---|---|---|---|---|
| Natural `<12>` / N.H. | ✅ `<12>` | ⬜ | ✅ | — | |
| Artificial (A.H.) | ⬜ | ⬜ | ✅ | — | |
| Tapped (T.H.) | ⬜ | ⬜ | ✅ | — | |
| Pinch (P.H.) | ⬜ | ⬜ | ✅ | — | |
| Semi-harmonic | ⬜ | ⬜ | ✅ | — | |

## 7. Music, tracks and text

| Notation | Text | Engraved | GP5 | Seen in | Notes |
|---|---|---|---|---|---|
| Title, artist | ✅ | ✅ | ✅ | Happen To Me | |
| Several tracks (one PDF per track) | ✅ | ✅ | ✅ | Happen To Me | Up to 7 tracks |
| Track / part name | ✅ | ✅ | ✅ | Happen To Me | Text from the PDF or the file name |
| Tuning from labels (`e B G D A E`) | ✅ | ✅ | ✅ | — | |
| Written tuning ("Tuning: D A D G B E", "Drop D"…) | ✅ | ✅ | ✅ | Happen To Me | Notes from lowest to highest, or a name; free tunings use the nearest octave |
| Capo ("Capo 3") | ⬜ | ⬜ | ✅ | — | |
| 4–7-string guitar / 4–5-string bass | ✅ | ✅ | ✅ | Happen To Me | |
| 8 strings or more | ⛔ | ⛔ | ⛔ | — | GP5 stores at most 7 strings (gives a clear error) |
| Song lyrics | ⬜ | ✅ | ✅ | Happen To Me | Muted "Lyrics (voice)" track with one note per syllable, where it is printed: full lyrics in the GP5 (GP5 only has one lyrics track). With 7 tracks, it goes to the track that plays in the most bars with lyrics (warning about the bars without it). The 3D highway shows the full lyrics |
| Chord names / diagrams | ⬜ | ⬜ | ✅ | — | |
| Free text over notes | ⬜ | ⬜ | ✅ | — | |
| Second voice | ⬜ | ⬜ | ✅ | — | Today: one voice per track |
| Drums / percussion | ⬜ | ⬜ | ✅ | — | Out of scope for now |
| Tab as an image (PNG/JPEG/WebP, PDF with images only) | ⬜ | 🟡 | — | Jet Lag (Ultimate Guitar screenshot) | OCR: numbers, string lines, bar lines, drawn rhythm and techniques written as words (H/P, P.M., let ring, PH/AH/N.H.), slides, vibrato, ties, legato arcs and bends (with release, pre-bend and amount). Text tab inside an image not yet |

---

## Known limitations of the GP5 format

- At most 7 strings per track and 7 tracks in this application (MIDI channels of port 1 without the percussion channel).
- No double dot and no graphical crescendos/decrescendos.
- Tied notes do not store the fret: the reader (Guitar Pro, TuxGuitar) infers the fret from the previous note.
