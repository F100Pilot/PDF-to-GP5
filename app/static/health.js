// The server's /api/health answer (versions, what is installed, what this page may do), asked
// once per page and shared by the scripts that need it; refresh() asks again (after an install).
(() => {
  "use strict";

  let pending = null;

  function get() {
    if (!pending) {
      pending = fetch("/api/health").then((r) => (r.ok ? r.json() : Promise.reject(r.status)));
      pending.catch(() => { pending = null; }); // a failed answer is not kept: the next call asks again
    }
    return pending;
  }

  function refresh() {
    pending = null;
    return get();
  }

  window.Health = { get, refresh };
})();
