---
name: gp-alphatab-check
description: Check that a Guitar Pro file (.gp5/.gp4/.gp3 or .gp) reads the same in alphaTab as in the file, and that nothing is lost when alphaTab saves it as .gp. Use after changing the GP5 writer, when a technique (bend, grace note, harmonic, slide, tie, vibrato…) shows in one program and not in another, before handing a GP file to RockForge, or when the user asks whether the gp/gp5 and alphaTab agree.
---

# GP file vs alphaTab

alphaTab is the reference the user works with (the app's player, and the tool that
saves `.gp` files with the MP3 for RockForge). This check says, note by note,
where a Guitar Pro file and alphaTab disagree.

## Run

```bash
.venv/bin/python .claude/skills/gp-alphatab-check/scripts/check_gp_alphatab.py FILE [FILE...] [--max-examples N]
```

- A converted song: convert the PDF first (the app, or
  `app.converter.convert(pdf_bytes, ConversionOptions()).gp5` written to a file),
  then check that file. Never commit the user's PDFs or GP files.
- Needs Playwright with Chromium (`pip install -r requirements-dev.txt` and
  `python -m playwright install chromium`). With another Chromium, set
  `CHROMIUM_PATH` (in the cloud sandbox the one under `/opt/pw-browsers` is found
  on its own).
- Exit code: 0 all equal, 1 differences, 2 could not run.

## What it compares

The alphaTab used is the app's own (`app/static/vendor/alphatab/alphaTab.min.js`),
in headless Chromium.

1. **file vs alphaTab** (`.gp3/.gp4/.gp5` only): the file as PyGuitarPro reads it
   against alphaTab's model.
2. **alphaTab vs its .gp export**: alphaTab's reading against what comes back
   after alphaTab's `Gp7Exporter` and a re-import. This is what survives when the
   file is saved as `.gp` through alphaTab. It runs for `.gp` files too.

It compares these fields:

- **Notes** (by track, bar, voice, tick position in the bar and string, with
  string 1 = the highest): fret, tie, dead, ghost, hammer/pull origin, vibrato,
  let ring, palm mute, staccato, accent, harmonic type, slides (in/out/shift/legato),
  bend curve, dynamics (ppp=0 … fff=7), and the grace note before it (fret,
  before or on the beat).
- **Beats**: duration, dots, tuplet, rest, strum/arpeggio direction, tapping.
- **Bars**: time signature, repeats, voltas, section name.
- **Song**: tempo.

## Reading the report

- `EQUAL` in both checks: alphaTab shows the file as written and a `.gp` saved
  through alphaTab keeps it.
- `notes.bend … exported.gp=None`: the bend is lost in the `.gp` export.
  alphaTab's `GpifWriter` writes no bend with more than 4 points (origin, two
  middle, destination), because the GP7 format holds no more. Fix: write the
  curve in at most 4 points (see `app/gp5_writer.py` `_bend`).
- `info: alphaTab keeps N bend(s) without their hold points` is not a
  difference. alphaTab's `Note.finish` keeps only origin and destination for a
  bend, pre-bend, release or hold with 3–4 points, and does the same for Guitar
  Pro's own files. The comparison applies that rule to the file before comparing.
- `only in file` / `only in alphaTab`: a beat or note the other side does not
  have, usually a rhythm or tick-position difference. Check the bar's durations
  and tuplets first.

When a difference is real, fix the writer so that the file matches alphaTab, add
a test in `tests/test_gp5_writer.py`, and run the check again on the song that
showed it.
