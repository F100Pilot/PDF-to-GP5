"""Run with RockForge's own Python: what RockForge's GP parser makes of a file, as JSON.

Usage: <rockforge>/.venv/bin/python rockforge_dump.py ROCKFORGE_DIR FILE
Prints {"tracks": [{"index", "name", "error" | "notes", "downbeats"}]}: the notes
(time in seconds from bar 1, string 0 = lowest, fret, techniques, bend, slides)
and the time of each played bar's downbeat, as parse_gp_track returns them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    rockforge, path = Path(sys.argv[1]), Path(sys.argv[2])
    sys.path.insert(0, str(rockforge / "src"))
    from rockforge.domain.errors import IngestionError
    from rockforge.infrastructure.gpimport.parser import inspect_gp, parse_gp_track

    out = []
    for info in inspect_gp(path).tracks:
        entry: dict = {"index": info.index, "name": info.name}
        try:
            parsed = parse_gp_track(path, info.index)
        except IngestionError as exc:
            entry["error"] = str(exc)
            out.append(entry)
            continue
        entry["notes"] = [
            {
                "time": n.time,
                "sustain": n.sustain,
                "string": n.string,
                "fret": n.fret,
                "techniques": sorted(t.value for t in n.techniques),
                "bend": n.bend_semitones,
                "slide_to": n.slide_to_fret,
                "slide_unpitch_to": n.slide_unpitch_to,
                "slide_in_from": n.slide_in_from,
            }
            for n in parsed.notes
        ]
        entry["downbeats"] = [b.time for b in parsed.tempo_map.beats if b.measure and b.measure > 0]
        out.append(entry)
    print(json.dumps({"tracks": out}))


if __name__ == "__main__":
    main()
