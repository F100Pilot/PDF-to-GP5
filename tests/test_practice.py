"""Practice helpers of the page (app/static/practice.js), run with Node when it is installed."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PRACTICE = Path(__file__).resolve().parents[1] / "app" / "static" / "practice.js"


def _next_loop_speed(*cases):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    script = (
        f"global.window = {{}}; require({json.dumps(str(PRACTICE))});"
        f"console.log(JSON.stringify({json.dumps(cases)}.map((c) => window.Practice.nextLoopSpeed(...c))));"
    )
    done = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True, timeout=30)
    return json.loads(done.stdout)


def test_each_round_of_the_loop_is_faster_up_to_normal_speed():
    loop = {"startTick": 1000, "endTick": 5000}
    assert _next_loop_speed(
        [loop, 4900, 1000, 0.75],  # from B back to A: 5 % faster
        [loop, 4900, 1000, 0.98],  # never past 100 %
        [loop, 4900, 1000, 1],  # already at 100 %
        [loop, 3000, 1000, 0.75],  # a jump from the middle (a click) is no new round
        [loop, 1000, 1200, 0.75],  # playing on
        [None, 4900, 1000, 0.75],  # no loop
    ) == [0.8, 1, None, None, None, None]
