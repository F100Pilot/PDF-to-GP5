---
name: pdf-to-gp5-i18n
description: PDF → GP5 is a multilingual app (Portuguese original + English + any language added later). Use this skill WHENEVER a change adds or edits text a user can see — the page markup (app/static/index.html), script strings (app/static/*.js: labels, toasts, alert/confirm, titles, aria-labels, status lines, report rows, the 3D highway's labels), or messages the server writes (HTTPException details, conversion errors and report warnings, audio/library/cover errors) or a CHANGELOG entry (the in-app What's new) — and when adding a new language. Every new text ships translated into EVERY language the app has, in the same change.
---

# PDF → GP5 i18n — every new text, in every language

The app is **polyglot**. Portuguese is the original: code and markup are written
in Portuguese, and **the Portuguese text is the key**. Every other language is
one dictionary. A change that adds visible text is not done until that text
exists in every dictionary — `tests/test_i18n.py` fails otherwise. The design is
the same as RockForge's (`.claude/skills/rockforge-i18n` there).

| where | how |
|---|---|
| `app/static/index.html` | nothing to call — `translateDom()` (in `i18n.js`) translates every text node and the `title`/`aria-label`/`placeholder`/`alt`/`data-name` attributes at load (whitespace collapsed). `translate="no"` skips an element. |
| `app/static/*.js` | `T('texto em português')`, `T('{n} notas', {n})` — a FIXED literal, variable parts as `{placeholders}`, never `${}` in the key. `T` and `LANG` are globals from `i18n.js`. |
| dictionaries | `app/static/i18n-<code>.js`: `(self.I18N_DICTS = self.I18N_DICTS \|\| {}).<code> = { "<pt>": "<translation>", ... };` — strict JSON between the braces, loaded by a `<script defer>` in index.html BEFORE `i18n.js` |
| server (Python) | `from .i18n import tr` → `tr("<pt>", "<en>", es="<es>", …)`; English is mandatory, other languages by keyword; a language not given reads the English. The request's language comes from the `X-App-Lang` header (`LanguageMiddleware`); the conversion's child process gets it from `sandbox.run_isolated`; a thread started from a request copies the context (`contextvars.copy_context().run`). Outside a request it is Portuguese. |

## When you add or change visible text

1. **Write it in Portuguese** (European Portuguese, the app's tone) — in the
   markup, inside `T(...)` in a script, or as the first argument of `tr(...)`.
2. **Script strings:**
   - Wrap the whole visible sentence: `` `${n} de ${m} tracks` `` →
     `T('{n} de {m} tracks', {n, m})`. HTML inside a key is fine; its
     translation keeps the SAME markup.
   - Plurals are two keys chosen by a condition.
   - Never `T()` an id, CSS class, API value, localStorage key, a value sent to
     the server, a file name, or data from the user/server (song titles; server
     messages are already translated by the server).
   - Never compare displayed text with Portuguese (`el.textContent === 'Pausa'`):
     compare state.
   - A Portuguese literal that is NOT shown (a data value such as the GP5 track
     name `"Letra (voz)"`) gets `// i18n-skip` on its line.
   - Decimal-comma number formatting is not text: leave it.
3. **Markup:** a sentence split by `<b>`/`<a>`/`<kbd>`/`<code>` is translated
   fragment by fragment, in the same order. Write it so each fragment translates
   on its own. Get the exact keys with:
   `.venv/bin/python -c "import sys,json; sys.path.insert(0,'tests'); import test_i18n as t; print(json.dumps(t.html_texts(), ensure_ascii=False, indent=1))"`
4. **Add the entry to EVERY `app/static/i18n-*.js`** (today `i18n-en.js`; list
   them with `ls app/static/i18n-*.js`):
   - The key must be byte-for-byte what `T()` receives (after JS unescaping),
     or the whitespace-collapsed page text.
   - Keep every `{placeholder}`, emoji, symbol and piece of markup.
   - Keep the file valid JSON: double quotes, no trailing comma.
   - When you change a Portuguese text, its key changes: replace the old entry
     in every dictionary, don't leave an orphan.
5. **Server text:**
   - `tr("<pt>", "<en>")` for anything a user reads: HTTP error details,
     `ConversionError`, report warnings, audio/library/cover errors.
   - A module-level constant is evaluated once, at import — build the message
     at call time (a function), or it is frozen in one language
     (see `sandbox.generic_error()`).
   - Not translated: logger messages, the CLI (`app/__main__.py`), the words
     used to DETECT text in PDFs (metadata/annotations/tunings keyword lists),
     and data written into the GP5 (track names).
6. **What's new (CHANGELOG):** the banner shows `CHANGELOG.<code>.md` in the
   user's language. A new entry in `CHANGELOG.md` goes, translated, into the same
   release and section of EVERY `CHANGELOG.*.md` (today `CHANGELOG.en.md`:
   Adicionado→Added, Alterado→Changed, Corrigido→Fixed, Removido→Removed,
   Segurança→Security), in the same position; a release bump renames the heading
   in all of them. `tests/test_changelog.py` fails when releases, sections or the
   number of entries differ. UI names quoted in an entry use the English UI's
   own words (look them up in `i18n-en.js`).
7. **Check:**
   - `.venv/bin/python -m pytest -q tests/test_i18n.py tests/test_i18n_server.py tests/test_changelog.py`
     fails on a missing entry in any language, a `${}` inside `T()`,
     placeholders that differ, Portuguese left outside `T()`, or a dictionary
     not loaded by the page.
   - Then `node --check app/static/<file>.js` and the full suite.
   - For UI work, look at the page in each language (the language picker is at
     the bottom of the side rail and in Definições → Aparência).

## Glossary (keep terms consistent)

Converter→Convert · Resultado→Result · Tocar→Play · Áudio→Audio ·
Biblioteca→Library · Definições→Settings · Partitura→Score · Pauta→Staff ·
Tab/tablatura→Tab/tablature · Track/Pista→Track · Compasso (contagem)→Bar ·
Compasso (4/4, 6/8)→Time signature · Andamento→Tempo · Afinação→Tuning ·
Secção→Section · Letra→Lyrics · Letra (voz)→Lyrics (vocals) · Capa→Cover ·
Início da música no áudio→Song start in the audio · Sincronização→Sync ·
Pista 3D→3D highway · Loop A–B→A–B loop · traste→fret · corda→string ·
acorde→chord · ficheiro→file · pasta→folder · Descarregar→Download ·
Guardar→Save · Novidades→What's new · gravada (tab)→engraved · texto (tab)→text ·
Semínima/Colcheia/Semicolcheia→Quarter/Eighth/Sixteenth note. For another
language, follow the same concepts (and Guitar Pro's own terms in that language).

## Adding a new language

1. Create `app/static/i18n-<code>.js` (`es`, `fr`, `de`… — two/three lowercase
   letters): copy `i18n-en.js`, change `.en =` to `.<code> =`, and translate
   every value from the PORTUGUESE key (not from the English).
2. Add `<script src="i18n-<code>.js" defer></script>` to index.html, before
   `i18n.js` (the test checks it). If `I18N_NAMES` in `i18n.js` lacks the
   language's own name, add it. The pickers list it by themselves.
3. `tests/test_i18n.py` picks the file up and demands full coverage.
4. Server messages read the English until a `<code>=` keyword is added to their
   `tr(...)`. Adding it everywhere is a separate, larger pass — say so rather
   than claiming the server is translated.
5. Create `CHANGELOG.<code>.md` (same releases, sections and entries, translated from the Portuguese), and update the README's language note and the CHANGELOG.
