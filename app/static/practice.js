"use strict";

// Practice helpers with no page or player of their own (score.js uses them).
(() => {
  // Loop trainer: the speed for the next round of the A–B loop, or null to keep it. A new round is
  // a jump back from near the loop's end (B) to near its start (A); each is `step` faster, up to `top`.
  // `range`: { startTick, endTick }; `lastTick` → `tick`: the player's previous and new positions.
  function nextLoopSpeed(range, lastTick, tick, speed, step = 0.05, top = 1) {
    if (!range || tick >= lastTick || speed >= top) return null;
    const span = range.endTick - range.startTick;
    if (span <= 0) return null;
    const backToStart = tick - range.startTick <= 0.25 * span && range.endTick - lastTick <= 0.25 * span;
    return backToStart ? Math.min(top, Math.round((speed + step) * 100) / 100) : null;
  }

  window.Practice = { nextLoopSpeed };
})();
