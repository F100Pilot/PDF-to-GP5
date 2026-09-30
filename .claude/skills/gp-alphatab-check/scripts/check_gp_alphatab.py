"""Check that a Guitar Pro file reads the same in alphaTab as in the file itself.

Two comparisons, note by note (string, fret, tie, bend curve, hammer/pull, slides,
harmonics, vibrato, ghost, dead, staccato, palm mute, let ring, accent, dynamics,
grace notes) and beat by beat (rhythm, tuplets, rests, strum/arpeggio, tapping),
plus bars (time signature, repeats, voltas, sections):

1. ``.gp3/.gp4/.gp5``: what the file holds (PyGuitarPro) against what alphaTab reads.
2. Any file (also ``.gp``): alphaTab's reading against what survives alphaTab's own
   ``.gp`` export and re-import — what is lost when the file is saved as ``.gp``
   through alphaTab (e.g. a bend with more than 4 points).

alphaTab is the one vendored by PDF-to-GP5 (app/static/vendor/alphatab), run in
headless Chromium through Playwright.

Usage: python check_gp_alphatab.py FILE [FILE...] [--max-examples N]
Exit code: 0 all equal, 1 differences found, 2 could not run.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ALPHATAB_JS = ROOT / "app" / "static" / "vendor" / "alphatab" / "alphaTab.min.js"
PYGUITARPRO_SUFFIXES = {".gp3", ".gp4", ".gp5"}

HARMONICS = {0: None, 1: "natural", 2: "artificial", 3: "pinch", 4: "tapped", 5: "semi", 6: "feedback"}
GP_HARMONICS = {1: "natural", 2: "artificial", 3: "tapped", 4: "pinch", 5: "semi"}
SLIDE_OUT = {0: None, 1: "shift", 2: "legato", 3: "out-up", 4: "out-down", 5: "pick-down", 6: "pick-up"}
SLIDE_IN = {0: None, 1: "in-below", 2: "in-above"}
GP_SLIDES = {-2: "in-above", -1: "in-below", 1: "shift", 2: "legato", 3: "out-down", 4: "out-up"}
BRUSH = {0: None, 1: "up", 2: "down", 3: "up", 4: "down"}
GRACE = {0: None, 1: "on-beat", 2: "before-beat", 3: "bend"}

# Runs in the page: the score as plain data, in the same shape as _gp_dump().
DUMP_JS = """
(score) => {
  const out = {tempo: score.tempo, bars: [], beats: [], notes: []};
  for (const mb of score.masterBars) {
    out.bars.push({bar: mb.index + 1,
      time: mb.timeSignatureNumerator + '/' + mb.timeSignatureDenominator,
      repeatStart: mb.isRepeatStart, repeatCount: mb.repeatCount,
      alternateEndings: mb.alternateEndings, section: mb.section ? mb.section.text : null});
  }
  score.tracks.forEach((track, ti) => {
    const staff = track.staves[0];
    const strings = staff.tuning.length;
    staff.bars.forEach((bar, bi) => {
      bar.voices.forEach((voice, vi) => {
        let graces = [];
        for (const beat of voice.beats) {
          if (beat.isEmpty) continue;
          if (beat.graceType !== 0) { graces.push(beat); continue; }
          const key = {track: ti, bar: bi + 1, voice: vi, pos: beat.displayStart};
          out.beats.push(Object.assign({}, key, {
            duration: beat.duration, dots: beat.dots,
            tuplet: beat.tupletNumerator > 0 ? beat.tupletNumerator + ':' + beat.tupletDenominator : null,
            rest: beat.isRest, brush: beat.brushType, tap: beat.tap}));
          for (const note of beat.notes) {
            const grace = graces.flatMap(g => g.notes).find(g => g.string === note.string);
            out.notes.push(Object.assign({}, key, {
              string: strings - note.string + 1,
              fret: note.isTieDestination ? null : note.fret,
              tie: note.isTieDestination, dead: note.isDead, ghost: note.isGhost,
              hammer: note.isHammerPullOrigin, vibrato: note.vibrato > 0 || beat.vibrato > 0,
              letRing: note.isLetRing, palmMute: note.isPalmMute, staccato: note.isStaccato,
              accent: note.accentuated, harmonic: note.harmonicType,
              slideIn: note.slideInType, slideOut: note.slideOutType,
              bend: note.hasBend ? note.bendPoints.map(p => [Math.round(p.offset / 60 * 1000) / 1000, p.value]) : null,
              dynamics: note.dynamics,
              grace: grace ? [grace.fret, graces.find(g => g.notes.includes(grace)).graceType] : null}));
          }
          graces = [];
        }
      });
    });
  });
  return out;
}
"""

LOAD_JS = """
([b64, dump]) => {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const settings = new alphaTab.Settings();
  const score = alphaTab.importer.ScoreLoader.loadScoreFromBytes(bytes, settings);
  const exported = new alphaTab.exporter.Gp7Exporter().export(score, settings);
  const again = alphaTab.importer.ScoreLoader.loadScoreFromBytes(exported, settings);
  const dumpFn = eval(dump);
  return JSON.stringify({version: alphaTab.meta ? alphaTab.meta.version : '?',
                         read: dumpFn(score), exported: dumpFn(again)});
}
"""


def _alphatab_side(page, data: bytes) -> tuple[str, dict, dict]:
    raw = page.evaluate(LOAD_JS, [base64.b64encode(data).decode(), DUMP_JS])
    result = json.loads(raw)
    return result["version"], _normalize_alphatab(result["read"]), _normalize_alphatab(result["exported"])


def _normalize_alphatab(dump: dict) -> dict:
    for note in dump["notes"]:
        note["harmonic"] = HARMONICS.get(note["harmonic"], note["harmonic"])
        note["slides"] = sorted(filter(None, [SLIDE_IN.get(note.pop("slideIn")), SLIDE_OUT.get(note.pop("slideOut"))]))
        note["accent"] = {0: None, 1: "accent", 2: "heavy"}.get(note["accent"], note["accent"])
        if note["grace"]:
            note["grace"] = [note["grace"][0], GRACE.get(note["grace"][1])]
        if note["bend"]:
            note["bend"] = [tuple(p) for p in note["bend"]]
    for beat in dump["beats"]:
        beat["brush"] = BRUSH.get(beat["brush"], beat["brush"])
    return dump


def alphatab_bend(points: list[tuple[float, int]]) -> list[tuple[float, int]]:
    """A GP3-5 bend as alphaTab keeps it (``Note.finish``): with 3 or 4 points, a
    bend, pre-bend, release or hold keeps only origin and destination (the middle
    points are holds, as in GP7's 4-point model); a bend-and-release keeps 4."""
    if len(points) == 4:
        o, m1, m2, d = points
        if m1[1] != m2[1]:
            return points
        release = m1[1] > d[1] if d[1] > o[1] else (d[1] == o[1] and m1[1] > o[1])
        return points if release else [o, d]
    if len(points) == 3:
        o, m, d = points
        if (d[1] > o[1] and m[1] > d[1]) or (d[1] == o[1] and m[1] > o[1]):
            return [o, m, m, d]
        return [o, d]
    return points


def _gp_dump(data: bytes) -> dict:
    """The file as PyGuitarPro reads it, in the alphaTab dump's shape."""
    import guitarpro

    song = guitarpro.parse(io.BytesIO(data))
    out: dict = {"tempo": song.tempo, "bars": [], "beats": [], "notes": []}
    for h in song.measureHeaders:
        out["bars"].append(
            {
                "bar": h.number,
                "time": f"{h.timeSignature.numerator}/{h.timeSignature.denominator.value}",
                "repeatStart": h.isRepeatOpen,
                "repeatCount": h.repeatClose + 1 if h.repeatClose > 0 else 0,
                "alternateEndings": h.repeatAlternative,
                "section": h.marker.title if h.marker else None,
            }
        )
    for ti, track in enumerate(song.tracks):
        for measure in track.measures:
            for vi, voice in enumerate(measure.voices):
                for beat in voice.beats:
                    if beat.status == guitarpro.BeatStatus.empty:
                        continue
                    d = beat.duration
                    key = {"track": ti, "bar": measure.number, "voice": vi, "pos": beat.start - measure.start}
                    tuplet = f"{d.tuplet.enters}:{d.tuplet.times}" if d.tuplet.enters != 1 else None
                    out["beats"].append(
                        {
                            **key,
                            "duration": d.value,
                            "dots": 1 if d.isDotted else 0,
                            "tuplet": tuplet,
                            "rest": beat.status == guitarpro.BeatStatus.rest,
                            "brush": {1: "up", 2: "down"}.get(beat.effect.stroke.direction.value),
                            "tap": beat.effect.slapEffect == guitarpro.SlapEffect.tapping,
                        }
                    )
                    for n in beat.notes:
                        e = n.effect
                        tie = n.type == guitarpro.NoteType.tie
                        slides = sorted(GP_SLIDES[s.value] for s in e.slides if s.value in GP_SLIDES)
                        bend = None
                        if e.bend:
                            bend = [(round(p.position / 12, 3), p.value) for p in e.bend.points]
                            kept = alphatab_bend(bend)
                            if kept != bend:
                                out["simplified"] = out.get("simplified", 0) + 1
                            bend = kept
                        grace = None
                        if e.grace:
                            grace = [e.grace.fret, "on-beat" if e.grace.isOnBeat else "before-beat"]
                        out["notes"].append(
                            {
                                **key,
                                "string": n.string,
                                "fret": None if tie else n.value,
                                "tie": tie,
                                "dead": n.type == guitarpro.NoteType.dead,
                                "ghost": e.ghostNote,
                                "hammer": e.hammer,
                                "vibrato": e.vibrato or beat.effect.vibrato,
                                "letRing": e.letRing,
                                "palmMute": e.palmMute,
                                "staccato": e.staccato,
                                "accent": "heavy"
                                if e.heavyAccentuatedNote
                                else "accent"
                                if e.accentuatedNote
                                else None,
                                "harmonic": GP_HARMONICS.get(e.harmonic.type) if e.harmonic else None,
                                "slides": slides,
                                "bend": bend,
                                "dynamics": max(0, min(7, (n.velocity - 15) // 16)),
                                "grace": grace,
                            }
                        )
    return out


def _compare(left_name: str, left: dict, right_name: str, right: dict, max_examples: int) -> list[str]:
    """Differences, grouped by field, with a few examples each."""
    diffs: dict[str, list[str]] = defaultdict(list)
    if left["tempo"] != right["tempo"]:
        diffs["tempo"].append(f"{left_name}={left['tempo']} {right_name}={right['tempo']}")
    for kind, key_fields in (
        ("bars", ("bar",)),
        ("beats", ("track", "bar", "voice", "pos")),
        ("notes", ("track", "bar", "voice", "pos", "string")),
    ):
        a = {tuple(r[k] for k in key_fields): r for r in left[kind]}
        b = {tuple(r[k] for k in key_fields): r for r in right[kind]}
        for key in sorted(a.keys() - b.keys()):
            diffs[f"{kind}: only in {left_name}"].append(_where(key_fields, key))
        for key in sorted(b.keys() - a.keys()):
            diffs[f"{kind}: only in {right_name}"].append(_where(key_fields, key))
        for key in sorted(a.keys() & b.keys()):
            for field, value in a[key].items():
                if field in key_fields or right_value_equal(value, b[key].get(field)):
                    continue
                diffs[f"{kind}.{field}"].append(
                    f"{_where(key_fields, key)}: {left_name}={value!r} {right_name}={b[key].get(field)!r}"
                )
    lines = []
    for field, items in sorted(diffs.items()):
        bars = sorted({int(i.split("bar ")[1].split()[0].rstrip(":,")) for i in items if "bar " in i})
        where = f" (bars {', '.join(map(str, bars[:20]))}{'…' if len(bars) > 20 else ''})" if bars else ""
        lines.append(f"  {field}: {len(items)}{where}")
        lines.extend(f"      {item}" for item in items[:max_examples])
    return lines


def right_value_equal(a, b) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return [tuple(x) if isinstance(x, list) else x for x in a] == [
            tuple(x) if isinstance(x, list) else x for x in b
        ]
    return a == b


def _where(fields: tuple[str, ...], key: tuple) -> str:
    return ", ".join(f"{f} {v}" for f, v in zip(fields, key, strict=True))


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
    parser.add_argument("--max-examples", type=int, default=3)
    args = parser.parse_args(argv)
    if not ALPHATAB_JS.is_file():
        print(f"alphaTab not found at {ALPHATAB_JS}", file=sys.stderr)
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is missing: pip install playwright && python -m playwright install chromium", file=sys.stderr)
        return 2
    found = False
    with sync_playwright() as p:
        browser = _launch(p)
        page = browser.new_page()
        page.set_content("<!doctype html><html><body></body></html>")
        page.add_script_tag(path=str(ALPHATAB_JS))
        for path in args.files:
            data = path.read_bytes()
            if path.suffix.lower() == ".gp" and not zipfile.is_zipfile(io.BytesIO(data)):
                print(f"{path}: not a .gp (zip) file", file=sys.stderr)
                return 2
            version, read, exported = _alphatab_side(page, data)
            print(f"== {path.name} (alphaTab {version}: {len(read['notes'])} notes, {len(read['bars'])} bars)")
            checks = []
            if path.suffix.lower() in PYGUITARPRO_SUFFIXES:
                checks.append(("file vs alphaTab", "file", _gp_dump(data), "alphaTab", read))
            checks.append(("alphaTab vs its .gp export", "alphaTab", read, "exported.gp", exported))
            if checks[0][2].get("simplified"):
                print(
                    f"   (info: alphaTab keeps {checks[0][2]['simplified']} bend(s) without their hold "
                    "points — its model for bend/pre-bend/release/hold, also for Guitar Pro's own files)"
                )
            for title, ln, left, rn, right in checks:
                lines = _compare(ln, left, rn, right, args.max_examples)
                print(f"-- {title}: {'EQUAL' if not lines else 'DIFFERENT'}")
                if lines:
                    print("\n".join(lines))
                found = found or bool(lines)
        browser.close()
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
