---
name: gp-alphatab-check
description: Compare a Guitar Pro file (.gp5/.gp4/.gp3 or .gp) with how alphaTab reads it and with what survives alphaTab's .gp export, note by note. Use when the user asks to compare ("compara", "comparar", "está igual ao alphaTab?", "o gp e o alphatab estão iguais?"), when a technique (bend, grace note, harmonic, slide, tie, vibrato…) shows in one program and not in another, or after changing the GP5 writer. Runs here in the session, on files the user attaches or on PDFs converted here — never ask the user to run it.
---

# GP file vs alphaTab

The user works with alphaTab: it is the app's player, and the tool that saves
`.gp` files with the MP3 for RockForge. When they ask to compare, run this check
here and report the result. They do not run it themselves.

## Steps

1. **Get the file.**
   - An attached `.gp5`/`.gp` is under `/root/.claude/uploads/<session>/`.
   - An attached PDF: convert it here, from the repo root:
     ```python
     from app.converter import convert, ConversionOptions
     open(out, "wb").write(convert(open(pdf, "rb").read(), ConversionOptions()).gp5)
     ```
     Write `out` in the scratchpad. Never commit the user's PDFs or GP files.
2. **Run** from the repo root:
   ```bash
   .venv/bin/python .claude/skills/gp-alphatab-check/scripts/check_gp_alphatab.py FILE [FILE...] --max-examples 3
   ```
   - Exit code: 0 all equal, 1 differences, 2 could not run.
   - Needs Playwright in `.venv` (`pip install -r requirements-dev.txt`). Don't
     run `playwright install`: the sandbox Chromium under `/opt/pw-browsers` is
     found on its own. Elsewhere, set `CHROMIUM_PATH`.
3. **Report in PT-PT, briefly.**
   - For each file and each check: igual, or a table of the differences by
     technique, with the bars and an example.
   - Then the cause, and whether it is in the file, in our GP5 writer or in
     alphaTab.
   - Offer the fix when the cause is ours.

## What it compares

The alphaTab used is the app's own (`app/static/vendor/alphatab/alphaTab.min.js`),
run in headless Chromium.

1. **file vs alphaTab** (`.gp3/.gp4/.gp5`): the file as PyGuitarPro reads it
   against alphaTab's model.
2. **alphaTab vs its .gp export**: alphaTab's reading against what comes back
   after alphaTab's `Gp7Exporter` and a re-import. This is what survives when the
   file is saved as `.gp` through alphaTab. It also runs for `.gp` files.

The fields compared are:
- **Notes**, keyed by track, bar, voice, tick in the bar and string (1 = the
  highest): fret, tie, dead, ghost, hammer/pull, vibrato, let ring, palm mute,
  staccato, accent, harmonic, slides, bend curve, dynamics (ppp=0 … fff=7), and
  the grace note before the note.
- **Beats**: duration, dots, tuplet, rest, strum/arpeggio direction, tapping.
- **Bars**: time signature, repeats, voltas, section.
- **Song**: tempo.

## Reading the result

- `EQUAL` in both checks means alphaTab shows the file as written, and a `.gp`
  saved through alphaTab keeps it.
- `notes.bend … exported.gp=None`: the bend is lost in the `.gp` export.
  alphaTab's `GpifWriter` writes no bend with more than 4 points (origin, two
  middle, destination), because GP7 holds no more. If the file came from us, fix
  `_bend` in `app/gp5_writer.py`.
- `info: alphaTab keeps N bend(s) without their hold points` is not a
  difference. alphaTab's `Note.finish` keeps only origin and destination for a
  3–4 point bend, pre-bend, release or hold, and does the same for Guitar Pro's
  own files. The check applies that rule to the file before comparing.
- `only in file` / `only in alphaTab`: a beat or note the other side does not
  have, usually a rhythm or tick-position difference. Look at that bar's
  durations and tuplets.

When the difference is in our writer, fix it so the file matches alphaTab, add a
test in `tests/test_gp5_writer.py`, and run the check again on the same song.
