// PDF → GP5 speaks several languages. Portuguese is the original — written in
// the code and the markup — and every other language is ONE dictionary file,
// i18n-<code>.js, keyed by the Portuguese text:
//
//     (self.I18N_DICTS = self.I18N_DICTS || {}).en = { "Guardar": "Save", ... };
//
// Each dictionary is a <script> in index.html, loaded before this file; the
// pickers list whatever is registered. See .claude/skills/pdf-to-gp5-i18n/SKILL.md.
//
// - Script text goes through T('texto em português', {vars}) — the Portuguese
//   IS the key, so a string a dictionary lacks still shows, in Portuguese.
//   Placeholders are {name}: T('{n} notas', {n: 3}).
// - index.html is translated once at load by translateDom(): every text node
//   and the title/aria-label/placeholder/alt/data-name attributes whose text
//   (whitespace collapsed) is a key. `translate="no"` on an element skips it.
// - Every same-origin fetch carries X-App-Lang, so the server answers in the
//   same language (app/i18n.py).
// - Switching reloads the page: everything built at load is built again.
/* exported T, setLang, LANG */
"use strict";

const I18N_DICTS = self.I18N_DICTS || {};

// Each language's name in its own language, for the pickers. A dictionary for a
// language missing here is still offered, under its code.
const I18N_NAMES = {
  pt: "Português", en: "English", es: "Español", fr: "Français", de: "Deutsch",
  it: "Italiano", nl: "Nederlands", pl: "Polski", ru: "Русский", ja: "日本語", zh: "中文",
};

const I18N_LANGS = ["pt", ...Object.keys(I18N_DICTS).filter((c) => c !== "pt").sort()];
const LANG_KEY = "pdf-to-gp5.lang";

// The saved choice; else the first of the browser's languages we have; else
// English when it exists, else Portuguese.
const LANG = (() => {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (I18N_LANGS.includes(saved)) return saved;
  } catch {}
  const wanted = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || ""])
    .map((l) => String(l).toLowerCase().split("-")[0]);
  const hit = wanted.find((l) => I18N_LANGS.includes(l));
  if (hit) return hit;
  return I18N_LANGS.includes("en") ? "en" : "pt";
})();

const I18N = LANG === "pt" ? {} : I18N_DICTS[LANG] || {};

function i18nKey(s) {
  return String(s).replace(/\s+/g, " ").trim();
}

function T(pt, vars) {
  let s = pt;
  if (LANG !== "pt") {
    const tr = I18N[pt] ?? I18N[i18nKey(pt)];
    if (typeof tr === "string") s = tr;
  }
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
  return s;
}

const I18N_ATTRS = ["title", "aria-label", "placeholder", "alt", "data-name"];

// Translate a text in place, keeping the whitespace around it (it separates
// inline elements in the markup).
function i18nText(raw) {
  const key = i18nKey(raw);
  if (!key) return null;
  const tr = I18N[key];
  if (typeof tr !== "string") return null;
  const lead = raw.match(/^\s*/)[0];
  const trail = raw.match(/\s*$/)[0];
  return lead + tr + trail;
}

function translateDom(root) {
  if (LANG === "pt" || !root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (node.nodeType === Node.ELEMENT_NODE) {
        const tag = node.tagName;
        if (tag === "SCRIPT" || tag === "STYLE" || tag === "symbol") return NodeFilter.FILTER_REJECT;
        if (node.getAttribute("translate") === "no") return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  for (let node = walker.currentNode; node; node = walker.nextNode()) {
    if (node.nodeType === Node.TEXT_NODE) {
      const tr = i18nText(node.nodeValue);
      if (tr !== null) node.nodeValue = tr;
      continue;
    }
    for (const attr of I18N_ATTRS) {
      const v = node.getAttribute(attr);
      if (v) {
        const tr = i18nText(v);
        if (tr !== null) node.setAttribute(attr, tr);
      }
    }
  }
}

function setLang(lang) {
  if (!I18N_LANGS.includes(lang) || lang === LANG) return;
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {}
  location.reload();
}

(() => {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const url = typeof input === "string" ? input : (input && input.url) || String(input);
    const abs = new URL(url, location.href);
    if (abs.origin !== location.origin) return nativeFetch(input, init);
    const headers = new Headers((init && init.headers) || (input instanceof Request ? input.headers : undefined));
    if (!headers.has("X-App-Lang")) headers.set("X-App-Lang", LANG);
    return nativeFetch(input, { ...(init || {}), headers });
  };
  document.documentElement.lang = LANG;
})();

// The language pickers (rail: codes; Definições: names). A switch reloads the
// page, so a conversion or playback in progress stops: that is expected.
function wireLangSelects() {
  for (const sel of document.querySelectorAll("select[data-lang-select]")) {
    const short = sel.dataset.langSelect === "short";
    sel.replaceChildren(
      ...I18N_LANGS.map((code) => {
        const o = document.createElement("option");
        o.value = code;
        o.textContent = short ? code.toUpperCase() : I18N_NAMES[code] || code.toUpperCase();
        return o;
      }),
    );
    sel.value = LANG;
    sel.addEventListener("change", () => setLang(sel.value));
  }
}

// Deferred like the other scripts and listed before them in index.html, so
// they all see translated markup.
translateDom(document.body);
document.title = T(document.title);
wireLangSelects();
