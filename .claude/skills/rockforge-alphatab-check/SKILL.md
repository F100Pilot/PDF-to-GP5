---
name: rockforge-alphatab-check
description: Compare what RockForge charts from a Guitar Pro file (.gp5/.gp4/.gp3 or .gp) with what alphaTab plays, note by note, per track. Use when the user asks to compare with RockForge ("compara com o RockForge", "o RockForge lê igual ao alphaTab?"), when something plays in alphaTab but is wrong or missing in RockForge/Rocksmith, or after changing RockForge's GP import. Runs here in the session, on attached files or PDFs converted here — never ask the user to run it.
---

# RockForge vs alphaTab

The user checks a song in alphaTab (the app's player) and then builds it for
Rocksmith with RockForge. This check says where RockForge's GP import charts a
note differently from what alphaTab plays, before it gets to the game.

## Steps

1. **Get the file.** It is either an attached `.gp5`/`.gp` under
   `/root/.claude/uploads/<session>/`, or a PDF converted here, as in the
   `gp-alphatab-check` skill. Never commit the user's files.
2. **RockForge** must be checked out with its own `.venv`. Set `ROCKFORGE_DIR`,
   or put the checkout at `../rockforge` next to this repo (in the cloud
   session: `/home/user/rockforge`). If it is missing:
   - attach `F100Pilot/RockForge`;
   - clone it;
   - run `python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev,psarc]"`.
   To check a particular RockForge version, point `ROCKFORGE_DIR` at a worktree
   of that commit with a `.venv` symlink.
3. **Run** from this repo's root:
   ```bash
   .venv/bin/python .claude/skills/rockforge-alphatab-check/scripts/check_rockforge_alphatab.py FILE [FILE...] [--track N] --max-examples 3
   ```
   - Exit code: 0 all equal, 1 differences, 2 could not run.
4. **Report in PT-PT, briefly.**
   - For each track: igual, or the differences by technique, with the bars and
     an example.
   - Then the cause, in RockForge's `gpimport` (`parser.py` for GP3–5,
     `gpif_parser.py` for `.gp`), and offer the fix.
   - A fix in RockForge gets a test in `tests/test_gp_import.py` or
     `tests/test_gpif_import.py`, and this check is run again.

## How it compares

- **alphaTab** is the app's own, in headless Chromium. It plays the notes of
  every track in played order (repeats unrolled, via its `MidiFileGenerator`).
- **RockForge** runs `parse_gp_track` with its own Python (`scripts/rockforge_dump.py`).
- **Matching:** notes are matched by played bar, position in the bar (±0.02 of
  a bar), string and fret. Position is used instead of seconds, so tempo and
  sync don't matter.
- **Both sides in Rocksmith terms:**
  - a tie chain is one note, and its bend and vibrato belong to the held note;
  - hammer/pull is on the destination, and a hammerOn or pullOff depends on
    whether the fret goes up or down;
  - a bend is its peak in half-steps, and its curve: each side's points are
    read on the other's curve, in seconds on RockForge's bar grid (points
    past RockForge's shortened note end are not compared; a note without a
    curve is RockForge's single-peak bend, a rise across the note);
  - harmonics are plain (natural, tapped, semi) or pinch (artificial, pinch);
  - a slide-to has a target fret;
  - grace notes are notes of their own.
- **Not counted as extra:** notes RockForge adds on purpose, which are the
  lead-in of a slide into a note and the notes of a trill.
- **Tracks RockForge does not chart** (percussion, not 6 strings) are listed
  with its reason.

## Reading the result

| Line | Meaning |
|---|---|
| `only in alphaTab (missing in RockForge)` | A note alphaTab plays is missing from the chart (e.g. grace notes before RockForge handled them) |
| `only in RockForge` | A note in the chart that alphaTab does not play |
| `<technique>: in alphaTab, not in RockForge` | The technique is lost in RockForge (e.g. let ring written as `<LetRing/>` in a `.gp`) |
| `<technique>: in RockForge, not in alphaTab` | RockForge adds or misreads the technique (e.g. pinch read as a natural harmonic) |
| `bend size` / `slide target` | Same note, a different bend size or slide target fret |
| `bend curve` | Same bend size, a different shape: the first moment where the pitch differs (e.g. a flat pre-bend, which RockForge charts as a rise) |

Sustain lengths are not compared: RockForge trims each one to leave a gap
before the next note.
