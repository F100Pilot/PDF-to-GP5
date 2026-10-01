// Ultimate Guitar tab page probe. Paste the whole text into F12 → Console on the tab page (logged in
// as usual) and press Enter; Chrome may first ask you to type "allow pasting". It only reads what the
// page already loaded, drops query strings (no tokens), reads no cookies and sends nothing. The short
// result is copied to the clipboard. Run it after scrolling to the end and clicking Print → Cancel.
(() => {
  const strip = (url) => String(url || "").split(/[?#]/)[0];
  const tag = (el) => el.tagName.toLowerCase();
  const pdf = performance.getEntriesByType("resource")
    .filter((r) => /pdf/i.test(r.name) || /pdf/i.test(r.contentType || ""))
    .map((r) => [strip(r.name), r.contentType || "?", r.initiatorType]);
  const big = [...document.querySelectorAll("svg, canvas, img, iframe")]
    .filter((el) => el.getBoundingClientRect().width >= 400);
  const kinds = {};
  big.forEach((el) => { kinds[tag(el)] = (kinds[tag(el)] || 0) + 1; });
  const svgShapes = big.filter((el) => tag(el) === "svg")
    .reduce((n, el) => n + el.querySelectorAll("text, path, use").length, 0);
  const pictures = big.filter((el) => tag(el) !== "svg").slice(0, 5)
    .map((el) => tag(el) + " " + strip(el.currentSrc || el.src || "").slice(0, 120));
  const result = { pdf, kinds, svgShapes, pictures };
  copy(JSON.stringify(result));
  console.log("Copied:", result);
})();
