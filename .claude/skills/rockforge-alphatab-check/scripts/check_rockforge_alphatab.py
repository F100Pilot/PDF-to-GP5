"""Check that RockForge reads a Guitar Pro file the way alphaTab plays it.

For every track RockForge can chart, each note alphaTab plays is looked for among
the notes RockForge's GP parser produces, and their techniques compared. Notes
are matched by played bar (repeats unrolled), position in the bar, string and
fret, so the check does not depend on tempo or sync. Both sides are brought to
Rocksmith's terms first, the way RockForge charts a score:

- a tie chain is ONE note (its bend and vibrato belong to the held note);
- hammer-on / pull-off is on the destination note, from the origin's fret;
- a bend is its peak in half-steps, and its curve over the tie chain (the pitch
  at each point of either side, in seconds on RockForge's bar grid);
- harmonics are plain or pinch;
- grace notes are notes of their own.

Notes RockForge adds on purpose (the lead-in of a slide into a note, the notes of
a trill) are not counted as extra.

Usage: python check_rockforge_alphatab.py FILE [FILE...] [--track N] [--max-examples N]
RockForge: $ROCKFORGE_DIR (default: ../rockforge next to this repo), run with its
own .venv. Exit code: 0 all equal, 1 differences, 2 could not run.
"""

from __future__ import annotations

import argparse
import base64
import bisect
import itertools
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ALPHATAB_JS = ROOT / "app" / "static" / "vendor" / "alphatab" / "alphaTab.min.js"
ROCKFORGE_DIR = Path(os.environ.get("ROCKFORGE_DIR", ROOT.parent / "rockforge"))
DUMP = Path(__file__).with_name("rockforge_dump.py")
POSITION_TOLERANCE = 0.02  # of a bar (a 64th note in 4/4 is 0.016)

# alphaTab note/beat → Rocksmith techniques, as RockForge charts them.
HARMONIC = {1: "harmonic", 2: "pinchHarmonic", 3: "pinchHarmonic", 4: "harmonic", 5: "harmonic", 6: "harmonic"}

# In the page: every note alphaTab plays, in played order, tie chains merged.
DUMP_JS = """
(b64) => {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const settings = new alphaTab.Settings();
  const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(bytes, settings);
  const gen = new alphaTab.midi.MidiFileGenerator(score, settings,
    new alphaTab.midi.AlphaSynthMidiFileHandler(new alphaTab.midi.MidiFile()));
  gen.generate();
  const passes = gen.tickLookup.masterBars.map(m => ({index: m.masterBar.index, start: m.start,
    duration: m.masterBar.calculateDuration()}));
  const tracks = score.tracks.map((track, ti) => {
    const staff = track.staves[0];
    const notes = [];
    passes.forEach((pass, p) => {
      const bar = staff.bars[pass.index];
      if (!bar) return;
      for (const voice of bar.voices) {
        for (const beat of voice.beats) {
          if (beat.isEmpty || beat.isRest) continue;
          for (const note of beat.notes) {
            if (note.isTieDestination) continue;  // part of its origin's chain
            const chain = [note];
            while (chain[chain.length - 1].tieDestination) chain.push(chain[chain.length - 1].tieDestination);
            const last = chain[chain.length - 1];
            let peak = 0;
            const curve = [];  // [tick, half-steps] over the chain
            const start = pass.start + beat.playbackStart;
            for (const n of chain) {
              if (!n.hasBend) continue;
              const at = start + n.beat.absolutePlaybackStart - beat.absolutePlaybackStart;
              for (const b of n.bendPoints) {
                peak = Math.max(peak, b.value);
                curve.push([at + b.offset / 60 * n.beat.playbackDuration, b.value / 2]);
              }
            }
            notes.push({
              tick: pass.start + beat.playbackStart, string: note.string - 1, fret: note.fret,
              grace: beat.graceType !== 0,
              bend: peak / 2, curve, bentFromStart: note.hasBend,
              vibrato: chain.some(n => n.vibrato > 0 || n.beat.vibrato > 0),
              palmMute: note.isPalmMute, letRing: note.isLetRing, dead: note.isDead,
              accent: note.accentuated > 0, harmonic: note.harmonicType,
              tap: beat.tap, slap: beat.slap, pop: beat.pop, tremolo: !!beat.tremoloPicking,
              trill: note.trillValue >= 0, hammerOrigin: last.isHammerPullOrigin,
              slideIn: note.slideInType, slideOut: last.slideOutType,
            });
          }
        }
      }
    });
    return {index: ti, name: track.name, notes};
  });
  return JSON.stringify({version: alphaTab.meta ? alphaTab.meta.version : '?',
                         passes: passes.map(p => [p.start, p.duration]), tracks});
}
"""


def _alphatab(page, data: bytes) -> dict:
    return json.loads(page.evaluate(DUMP_JS, base64.b64encode(data).decode()))


def _rockforge(path: Path) -> dict:
    python = ROCKFORGE_DIR / ".venv" / "bin" / "python"
    if not python.exists():
        raise RuntimeError(f"RockForge not found at {ROCKFORGE_DIR} (with .venv): set ROCKFORGE_DIR")
    run = subprocess.run(
        [str(python), str(DUMP), str(ROCKFORGE_DIR), str(path)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if run.returncode != 0:
        raise RuntimeError(f"RockForge failed: {run.stderr.strip()[-500:]}")
    return json.loads(run.stdout)


def _where_tick(passes: list[list[int]], tick: float) -> tuple[int, float]:
    """(played bar, 1-based; position 0..1 in it) of an alphaTab tick."""
    starts = [s for s, _ in passes]
    i = max(0, bisect.bisect_right(starts, tick) - 1)
    start, duration = passes[i]
    return i + 1, (tick - start) / duration if duration else 0.0


def _where_time(downbeats: list[float], time: float) -> tuple[int, float]:
    """(played bar, 1-based; position 0..1 in it) of a RockForge time."""
    i = max(0, bisect.bisect_right(downbeats, time + 1e-6) - 1)
    if i + 1 < len(downbeats):
        span = downbeats[i + 1] - downbeats[i]
    else:
        span = downbeats[i] - downbeats[i - 1] if i > 0 else 1.0
    return i + 1, (time - downbeats[i]) / span if span > 0 else 0.0


def _to_seconds(downbeats: list[float], bar: int, pos: float) -> float:
    """RockForge time of a (played bar, position) — the inverse of _where_time."""
    i = min(bar, len(downbeats)) - 1
    if i + 1 < len(downbeats):
        span = downbeats[i + 1] - downbeats[i]
    else:
        span = downbeats[i] - downbeats[i - 1] if i > 0 else 1.0
    return downbeats[i] + pos * span


def _pitch(curve: list[tuple[float, float]], t: float, before: float) -> float:
    """A bend curve's value at time t: linear between points, held after the
    last, ``before`` ahead of the first."""
    if t < curve[0][0]:
        return before
    for (t0, v0), (t1, v1) in itertools.pairwise(curve):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v1
    return curve[-1][1]


def _bend_curve_diff(e: dict, g: dict, passes: list, downbeats: list[float]) -> str | None:
    """Where the two bend curves disagree, or None.

    alphaTab's points are read on RockForge's curve, and RockForge's on
    alphaTab's. RockForge ends a note a little early (a gap before the next
    note), moving points past the new end onto it: those are not compared.
    A RockForge note without a curve is its single-peak bend, a rise across the
    note."""
    at = [(_to_seconds(downbeats, *_where_tick(passes, tick)), v) for tick, v in e["curve"]]
    end = g["time"] + g["sustain"]
    rf = [tuple(p) for p in g["bend_points"]] or [(g["time"], 0.0), (end, g["bend"])]
    at_before = at[0][1] if e["bentFromStart"] else 0.0
    eps = 1e-3
    for t, v in at:
        if t <= end - eps and abs(_pitch(rf, t, rf[0][1]) - v) > 0.05:
            return f"at {t:.3f} s alphaTab {v:g}, RockForge {_pitch(rf, t, rf[0][1]):.2f}"
    for t, v in rf:
        if t < end - eps and abs(_pitch(at, t, at_before) - v) > 0.05:
            return f"at {t:.3f} s RockForge {v:g}, alphaTab {_pitch(at, t, at_before):.2f}"
    return None


def _expected(notes: list[dict]) -> list[dict]:
    """alphaTab notes in Rocksmith terms (hammer/pull and slide-to on the next note)."""
    by_string: dict[int, list[dict]] = defaultdict(list)
    for n in sorted(notes, key=lambda n: n["tick"]):
        by_string[n["string"]].append(n)
    for run in by_string.values():
        for a, b in itertools.pairwise(run):
            if a["hammerOrigin"]:
                b["hammer_to"] = "hammerOn" if b["fret"] > a["fret"] else "pullOff"
            if a["slideOut"] in (1, 2):
                a["slide_to"] = b["fret"]
    for n in notes:
        techs = set()
        if n["bend"] > 0:
            techs.add("bend")
        for flag, name in (
            ("vibrato", "vibrato"),
            ("palmMute", "palmMute"),
            ("letRing", "letRing"),
            ("dead", "mute"),
            ("accent", "accent"),
            ("tap", "tap"),
            ("slap", "slap"),
            ("pop", "pluck"),
            ("tremolo", "tremolo"),
        ):
            if n[flag]:
                techs.add(name)
        if n["harmonic"]:
            techs.add(HARMONIC.get(n["harmonic"], "harmonic"))
        if n["slideOut"] in (1, 2):
            techs.add("slide")
        if n.get("hammer_to"):
            techs.add(n["hammer_to"])
        n["techniques"] = techs
    return notes


def _compare_track(at_track: dict, passes: list, rf_track: dict, max_examples: int) -> list[str]:
    expected = _expected(at_track["notes"])
    for n in expected:
        n["bar"], n["pos"] = _where_tick(passes, n["tick"])
    got = rf_track["notes"]
    downbeats = sorted(rf_track["downbeats"])
    for n in got:
        n["bar"], n["pos"] = _where_time(downbeats, n["time"]) if downbeats else (1, 0.0)
        n["techniques"] = set(n["techniques"])

    pool: dict[tuple[int, int, int], list[dict]] = defaultdict(list)
    for n in got:
        pool[(n["bar"], n["string"], n["fret"])].append(n)
    diffs: dict[str, list[str]] = defaultdict(list)
    matched: set[int] = set()
    for e in expected:
        candidates = [
            g
            for g in pool[(e["bar"], e["string"], e["fret"])]
            if id(g) not in matched and abs(g["pos"] - e["pos"]) <= POSITION_TOLERANCE
        ]
        where = f"bar {e['bar']} at {e['pos']:.3f}, string {6 - e['string']}, fret {e['fret']}"
        if not candidates:
            diffs["only in alphaTab (missing in RockForge)"].append(where)
            continue
        g = min(candidates, key=lambda c: abs(c["pos"] - e["pos"]))
        matched.add(id(g))
        compare = e["techniques"] - ({"vibrato", "hammerOn", "pullOff"} if e["trill"] else set())
        have = g["techniques"] - ({"hammerOn", "pullOff"} if e["trill"] else set())
        for tech in sorted(compare - have):
            diffs[f"{tech}: in alphaTab, not in RockForge"].append(where)
        for tech in sorted(have - compare):
            diffs[f"{tech}: in RockForge, not in alphaTab"].append(where)
        if e["bend"] > 0 and abs(g["bend"] - e["bend"]) > 1e-6:
            diffs["bend size"].append(f"{where}: alphaTab {e['bend']} RockForge {g['bend']} half-steps")
        elif e["bend"] > 0 and downbeats and (why := _bend_curve_diff(e, g, passes, downbeats)):
            diffs["bend curve"].append(f"{where}: {why}")
        if "slide_to" in e and g.get("slide_to") != e["slide_to"]:
            diffs["slide target"].append(f"{where}: alphaTab {e['slide_to']} RockForge {g.get('slide_to')}")

    # Notes RockForge adds on purpose: slide-in lead-ins and trill runs.
    # Positions as bar + fraction, so a lead-in may sit just before the bar line.
    def intended(g: dict) -> bool:
        at = g["bar"] + g["pos"]
        for e in expected:
            if e["string"] != g["string"]:
                continue
            if e["slideIn"] and 0 <= e["bar"] + e["pos"] - at <= 0.1:
                return True
            if e["trill"] and 0 <= at - (e["bar"] + e["pos"]) <= 0.5:
                return True
        return False

    for g in got:
        if id(g) not in matched and not intended(g):
            diffs["only in RockForge"].append(
                f"bar {g['bar']} at {g['pos']:.3f}, string {6 - g['string']}, fret {g['fret']}"
            )
    lines = []
    for field, items in sorted(diffs.items()):
        bars = sorted({int(i.split()[1]) for i in items})
        shown = ", ".join(map(str, bars[:20])) + ("…" if len(bars) > 20 else "")
        lines.append(f"  {field}: {len(items)} (bars {shown})")
        lines.extend(f"      {item}" for item in items[:max_examples])
    return lines


def _launch(playwright):
    try:
        return playwright.chromium.launch()
    except Exception:  # this Playwright's browser build is not installed: try the known ones
        candidates = [
            os.environ.get("CHROMIUM_PATH", ""),
            *map(str, Path("/opt/pw-browsers").glob("chromium_headless_shell-*/chrome-linux/headless_shell")),
        ]
        for path in filter(None, candidates):
            if Path(path).exists():
                return playwright.chromium.launch(executable_path=path)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--track", type=int, help="only this track (0-based)")
    parser.add_argument("--max-examples", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is missing: pip install -r requirements-dev.txt", file=sys.stderr)
        return 2
    found = False
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page()
        page.set_content("<!doctype html><html><body></body></html>")
        page.add_script_tag(path=str(ALPHATAB_JS))
        for path in args.files:
            try:
                rockforge = _rockforge(path)
            except RuntimeError as exc:
                print(exc, file=sys.stderr)
                return 2
            alphatab = _alphatab(page, path.read_bytes())
            print(f"== {path.name} (alphaTab {alphatab['version']}, {len(alphatab['passes'])} bars played)")
            for rf_track in rockforge["tracks"]:
                if args.track is not None and rf_track["index"] != args.track:
                    continue
                name = f"track {rf_track['index']} '{rf_track['name']}'"
                if "error" in rf_track:
                    print(f"-- {name}: not charted by RockForge ({rf_track['error']})")
                    continue
                at_track = alphatab["tracks"][rf_track["index"]]
                lines = _compare_track(at_track, alphatab["passes"], rf_track, args.max_examples)
                total = len(at_track["notes"])
                print(f"-- {name}: {'EQUAL' if not lines else 'DIFFERENT'} ({total} alphaTab notes)")
                if lines:
                    print("\n".join(lines))
                found = found or bool(lines)
        browser.close()
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
