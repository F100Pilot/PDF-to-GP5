// Ultimate Guitar web page probe — paste into the DevTools Console (F12 → Console) on the tab
// page, logged in as usual. It only reads what the page already loaded and copies a JSON summary
// to the clipboard: resource URLs WITHOUT their query strings (no tokens), the elements that hold
// the notation (canvas / svg / img and their sizes), the page's embedded-data keys, and whether
// the "Print" button exists. It sends nothing anywhere and reads no cookies.
// Run it once after the page loads, and once more after clicking the site's Print button.
(() => {
  const strip = (url) => String(url || "").split(/[?#]/)[0];
  const resources = performance.getEntriesByType("resource").map((r) => ({
    url: strip(r.name),
    initiator: r.initiatorType,
    kb: Math.round((r.transferSize || r.encodedBodySize || 0) / 1024),
  }));
  const interesting = resources.filter((r) =>
    /pdf|print|export|download|render|score|notation|tab|png|svg|webp|\.gp|mscz|json|api|graphql/i.test(r.url),
  );
  const notation = [...document.querySelectorAll("canvas, svg, img, object, embed, iframe")]
    .map((el) => ({ el, box: el.getBoundingClientRect() }))
    .filter(({ box }) => box.width >= 300)
    .map(({ el, box }) => ({
      tag: el.tagName.toLowerCase(),
      width: Math.round(box.width),
      height: Math.round(box.height),
      src: strip(el.currentSrc || el.getAttribute("src") || el.getAttribute("data") || "").slice(0, 160),
    }));
  const embedded = {};
  try {
    const store = document.querySelector(".js-store");
    const data = store && JSON.parse(store.getAttribute("data-content"));
    const page = data && data.store && data.store.page && data.store.page.data;
    embedded.jsStore = page ? Object.keys(page) : null;
    embedded.tabView = page && page.tab_view ? Object.keys(page.tab_view) : null;
    embedded.tab = page && page.tab ? Object.keys(page.tab) : null;
  } catch (error) {
    embedded.jsStore = "error: " + error.message;
  }
  const next = document.getElementById("__NEXT_DATA__");
  embedded.nextData = next ? next.textContent.length + " chars" : null;
  const buttons = [...document.querySelectorAll("button, a, [role=button]")]
    .map((b) => (b.innerText || b.getAttribute("aria-label") || b.title || "").trim())
    .filter((t) => /print|pdf|download|export|imprim|descarreg/i.test(t));
  const summary = {
    page: strip(location.href),
    when: new Date().toISOString(),
    resources: interesting.slice(0, 300),
    resourceCount: resources.length,
    notationElements: notation.slice(0, 60),
    embedded,
    buttons: [...new Set(buttons)].slice(0, 30),
  };
  copy(JSON.stringify(summary, null, 1));
  console.log("UG probe copied to the clipboard:", summary);
})();
