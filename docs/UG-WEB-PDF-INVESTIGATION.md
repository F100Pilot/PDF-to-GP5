# Ultimate Guitar website → native vector PDF: investigation

Question: on Windows, can the user download the same native vector PDF that the
Ultimate Guitar (UG) Android app exports, directly from the UG website or its legitimate
web features, without getting a screenshot/image PDF?

Reference tab: Simple Plan, "Jet Lag", Official, id 2157405. Reference file:
`Simple Plan - Jet Lag - Pro.pdf` (exported by the user in the Android app). Web sample:
a PDF the user saved from Chrome's Print dialog on the UG website (Official tab "You're A
God", Vertical Horizon). Neither file is in the repository.

Nothing has been implemented. Every statement is tagged:

- **CONFIRMED**: measured on a file, or read in a source that was opened in full.
- **LIKELY**: seen only in search-result excerpts, or inferred from several agreeing facts.
- **UNKNOWN**: not verified.

Limit of this investigation: this environment cannot open `ultimate-guitar.com`
(CONFIRMED: blocked by the network policy). That is **not** evidence about the website. It
means every statement about the live site below is LIKELY or UNKNOWN until the user
captures it on their PC (section 4).

## 1. Short answer

**Probably not, through any documented website feature** (LIKELY). The only documented web
path for Pro/Official tabs is the site's Print button followed by the browser's "Save as
PDF". On the user's own capture, that path produced one PNG picture per system (CONFIRMED),
not the Android app's vector file.

Two questions stay open, and both can be answered with a capture from the user's PC:

1. Does clicking Print (or anything else on the page) fetch a PDF from a UG server?
   (UNKNOWN)
2. Does the tab page draw the notation as **SVG** (vector) or as **canvas/PNG** (raster)?
   (UNKNOWN)

If the notation on screen is SVG, the user's own logged-in browser can print it to a vector
PDF (section 6). That PDF would be vector, but it would not be byte-identical to the Android
file.

**Update (user test, airplane mode):** the Android app exports the PDF with no network
connection. CONFIRMED by the user. So the app creates the PDF on the phone (LIKELY; a copy
cached by an earlier export cannot be fully excluded). If so, no UG server produces that
file, and no web or Windows client can download it: there is no request to reproduce.

**Update (user's Network capture and console probe, Windows, Chrome):**

- Network, filter `pdf`, after loading, scrolling and Print → Cancel: the only rows are
  `data:image/png;base64,…` addresses, type png, status 200, size "(memory cache)", all
  started by the site script `8780.123b904….js`. They are pictures made inside the page by
  the site's script, not requests to a server, and none is a PDF. The word "pdf" most likely
  matched by chance inside the base64 text. CONFIRMED.
- Probe: `{"pdf":[],"kinds":{"canvas":2,"svg":1},"svgShapes":70,"pictures":["canvas ","canvas "]}`.
  No PDF resource; two large `<canvas>` elements; one large SVG with only 70 shapes, far too
  few for a full tab. CONFIRMED.
- Reading: the page draws the notation on `<canvas>` with its own script. For Print, the
  script turns the canvas into PNG pictures (`data:image/png`), which Chrome puts in the PDF.
  This matches the 990 px PNG systems of section 2.2. LIKELY for the print step.
- Elements → Ctrl+Shift+C → click a fret number highlights
  `<canvas id="xtz_canvas" width="970" height="932">`. The fret numbers are canvas pixels.
  CONFIRMED.

**Answer: no.** The website gives no vector PDF (no PDF request; the notation reaches the
page only as canvas pixels). The Android file is built inside the app (works offline), so no
server or web feature can deliver it to Windows. The legitimate routes are in section 7.

## 2. Evidence

### 2.1 The Android PDF (reference)

Measured with `tools/ug_pdf_inspect.py`; details in `docs/UG-PDF-INVESTIGACAO.md`.

- PDF 1.7, 4 pages, MediaBox 2976×4209 (A4 × 5). The Info dictionary is empty, and the
  catalog holds only `/Pages`. CONFIRMED.
- No images. All notation is vector paths and text:
  - fonts: Edwin, Leland and Bravura (CFF), plus Roboto (TrueType) for the fret numbers;
  - SMuFL glyphs;
  - coordinates in MuseScore's internal 360-per-inch units.

  CONFIRMED.
- It is engraved by a MuseScore-based engine and written by a PDF writer that is neither
  Qt's nor Skia's. LIKELY. UG and MuseScore both belong to Muse Group. CONFIRMED by public
  sources.

### 2.2 The website print PDF (user's capture)

- `Producer: Skia/PDF m154` and `Creator: Mozilla/5.0 (Windows NT 10.0; Win64; x64) …
  Chrome/154`. Title: `OFFICIAL YOURE A GOD CHORDS & TABS by Vertical Horizon @
  Ultimate-Guitar.Com`. CONFIRMED.
  - So the file was written by Chrome on Windows, not by a UG server. CONFIRMED.
  - The tab is Official. CONFIRMED by the title.
- PDF 1.4, 3 pages, A4 landscape (842 × 595 pt). CONFIRMED.
- Notation: 8 PNG images, all 990 px wide, one per system (3 + 3 + 2). Each is drawn
  622.5 pt wide, about 114 dpi. CONFIRMED.
- The only text is the header ("Youre A God | Vertical Horizon | Tuning: …") in
  TimesNewRomanPSMT. CONFIRMED.
- The pictures look like the Android engraving:
  - bold serif section names and italic bar numbers (Edwin-like);
  - a MuseScore TAB clef;
  - an H-bar multi-measure rest;
  - bold sans fret numbers (Roboto-like).

  So the website most likely shows the **same engraving engine's output, rasterised**.
  LIKELY, judged visually only.
- Chrome keeps vector content vector when it prints, so the notation reached the page as
  raster pixels (`<img>` or `<canvas>`). It was not a vector PDF or SVG that Chrome then
  flattened. LIKELY: Skia/PDF keeps SVG and text as vectors; that is CONFIRMED from Chrome's
  normal behaviour, but this page was not inspected.

### 2.3 UG help centre

Read only as search excerpts, so all LIKELY.

- Article 6735529: Pro/Official tabs have a **Print** button "in the top-right corner,
  positioned over the tab's body". The PDF comes from the browser's "Save as PDF".
- Article 10558773: **"Download PDF"** exists only for text tabs/chords. "For Pro, Power,
  and Official tabs, you need to use the 'Print' button first and save as PDF."
- "Official tabs cannot be downloaded" (as Guitar Pro files).
- Article 6744592: in the app, Print → printer, or download a PDF. This is the path that
  produced the reference file.
- No public document, forum post or open-source tool was found that describes a web
  endpoint returning a vector PDF for Pro/Official tabs. CONFIRMED only in the sense that
  none was found. A UG forum thread (t=2724947, March 2025) reports PC printing problems;
  it was not read (UNKNOWN content).

### 2.4 Community tools (checked against the security limits)

- **UGDownloader**: Selenium with the user's login. Downloads Guitar Pro files and says
  "Official files are not included". It is not a PDF tool. LIKELY.
- **UGTabExport, Tabdown**: text tabs only. LIKELY.
- Projects that call the **mobile API** (`api.ultimate-guitar.com/api/v1`) sign every
  request with `X-UG-API-KEY` = md5(device id + date/hour + an embedded secret). That is
  impersonating the Android app, which is out of scope under the project's rules. LIKELY,
  from source excerpts.
- Projects described as bypassing Pro restrictions: excluded and not studied.

## 3. The ten questions

| # | Question | Answer | Status |
|---|---|---|---|
| 1 | Does the website expose a native PDF export? | Not for Pro/Official tabs: only Print → browser "Save as PDF". "Download PDF" exists for text tabs/chords. | LIKELY |
| 2 | If yes, where/how? | Text tabs/chords: a "Download PDF" control on the tab page. Whether that file is vector is UNKNOWN. Pro/Official: Print button over the tab body. | LIKELY |
| 3 | Which network request is responsible? | Print path: none needed. The PDF is created locally by Chrome (CONFIRMED by Producer/Creator). Where the 990 px system pictures come from (an image URL, or a canvas drawn in the page) is UNKNOWN. | CONFIRMED / UNKNOWN |
| 4 | Does it return `application/pdf`? | Print path: no server PDF. The file is written by Skia in the browser (CONFIRMED). Any other request returning `application/pdf` on a tab page is UNKNOWN. | CONFIRMED / UNKNOWN |
| 5 | Same PDF-generation system as Android? | No, different writer: Android uses a custom writer with vectors in MuseScore units, the web uses Chrome Skia with PNG pictures (CONFIRMED). The engraving engine behind the pictures looks the same (LIKELY). | CONFIRMED / LIKELY |
| 6 | Does it work for Official/Pro tabs? | Print works for Official tabs, but the output is raster: the user's Official tab gave PNG systems. Print for tab 2157405 was not captured (UNKNOWN). | CONFIRMED / UNKNOWN |
| 7 | What authentication is required? | A UG account with a Pro subscription to view and print Official tabs. The web session is cookie-based. | LIKELY |
| 8 | Can a legitimate Windows client reproduce the request? | No vector-PDF web request is known to reproduce. The Android export works offline, so it makes no request to reproduce (CONFIRMED offline; on-phone generation LIKELY). The known mobile API needs app-impersonation signing, which is excluded. | CONFIRMED / LIKELY / UNKNOWN |
| 9 | Can browser automation reproduce it? | It can reproduce Print in the user's own session (Playwright, persistent profile, manual login). The result is vector only if the page draws the notation as SVG (UNKNOWN). | LIKELY / UNKNOWN |
| 10 | If not, what exact obstacle? | The website delivers the engraving to the browser as pixels (CONFIRMED for the printed output; screen rendering UNKNOWN). The vector PDF is built inside the Android app on the phone (works offline), so no server holds it. | CONFIRMED / LIKELY / UNKNOWN |

## 4. What the user needs to capture (Windows, Chrome or Edge)

Use your own logged-in session, on a tab you are entitled to view. Ideally use the
reference tab 2157405; the Official "You're A God" tab is a second choice.

### 4.1 Network capture

1. Open the tab page while logged in, as usual.
2. Press **F12** → **Network** tab.
3. Tick **Preserve log** and **Disable cache**.
4. Press **Ctrl+R** (reload with DevTools open).
5. Scroll to the end of the tab so every system loads.
6. Click the site's **Print** button. When the print dialog appears, press **Cancel**: the
   requests are already logged.
7. In the Network filter box, try each of these in turn and note which match:
   `pdf`, `print`, `download`, `export`, `render`, `png`, `svg`, `api`.
   Also click the **Doc**, **Img** and **Fetch/XHR** type buttons.
8. For every request that looks related (a PDF, the big system pictures, anything named
   print/render/export), click it and copy:
   - **Headers**: Request URL (you may blank out long random tokens), Request Method,
     Status, `content-type` of the response, `content-disposition` if present.
   - **Initiator** tab: which script started it.
   - **Do not copy** the `cookie`, `authorization` or `x-…-token` headers.
9. Optional: right-click the request list → **Export HAR (sanitized)…**. Chrome 130+
   removes cookies and the Authorization header. Query strings and response bodies stay
   in, so open the file and remove anything you consider private before sending it.

### 4.2 How the notation is drawn (one minute)

1. With the tab page open, go to **F12 → Elements**.
2. Press **Ctrl+Shift+C** and click a fret number in the tab.
3. Read the highlighted element. It is one of:
   - `<svg>` / `<text>` / `<path>` → vector on screen. This is the important case.
   - `<canvas>` → drawn as pixels.
   - `<img src="…">` → a picture from the server. Note the URL without its query string.

### 4.3 Automatic summary (optional)

1. Open **F12 → Console** on the tab page.
2. Open `tools/ug_web_probe.js` in a text editor, copy the **whole text** and paste it into
   the Console, then press Enter. Typing the file name does nothing: the Console runs code,
   not files. If Chrome refuses to paste, type `allow pasting` first.
3. It copies one short line of JSON to the clipboard. Paste it in the chat. It lists:
   - `pdf`: requests with "pdf" in the address or type;
   - `kinds`: how many large `svg`/`canvas`/`img`/`iframe` elements the page has;
   - `svgShapes`: how many text/path shapes those SVGs hold (many → vector notation);
   - `pictures`: up to five picture addresses, without query strings.
4. Run it after scrolling to the end of the tab and clicking Print → Cancel.

The script only reads what the page already loaded. It strips query strings from URLs, does
not read cookies and sends nothing. The browser keeps only about 250 resource entries, so
the Network screenshot (filter `pdf`) is the authoritative check for PDF requests.

### 4.4 The Android side (optional, for question 5)

- Done: the export works in airplane mode (CONFIRMED by the user). The PDF is built on the
  phone (LIKELY), so there is no server PDF endpoint to look for.
- Do **not** intercept the app's TLS traffic or extract keys from the app. Both are out of
  scope.

## 5. How each capture result changes the answer

| Capture shows | Meaning | Next step |
|---|---|---|
| A request returning `application/pdf` with vector content | A web PDF export exists (contradicts the help centre) | Document method, URL, parameters, CSRF and signed-URL lifetime. A proof of concept downloads it from the user's own browser session (Playwright), never with copied cookies. |
| Notation drawn as `<svg>` with text/paths | No server PDF, but vector on screen | Playwright prints the page in the user's session, keeping screen styles, to a vector PDF. It is vector, not identical to Android. |
| Notation as `<img>` PNG or `<canvas>`, no PDF request | Website only has pixels | No vector PDF from the website. The remaining options are in section 7. |
| Android export works offline | Phone-side generator, no endpoint | Same as the row above for the web. The Android file cannot be fetched from any server. |

## 6. Browser automation (allowed, not implemented)

Only meaningful if 4.2 shows SVG, or 4.1 shows a PDF request.

- Playwright with `launch_persistent_context(user_data_dir=<a dedicated profile>,
  headless=False)`. The user logs in by hand once in that window. The tool never reads,
  copies or stores cookies or tokens.
- Then, in the same profile:
  1. open the tab URL;
  2. wait until every system is drawn;
  3. call `page.emulate_media(media="screen")`, in case the print stylesheet swaps SVG for
     pictures;
  4. print with `page.pdf(...)`.
- `page.pdf` works only in headless Chromium (LIKELY, from Playwright's documentation; to
  confirm). The same profile can be reopened headless after the manual login.
- If a PDF request exists instead, the PoC clicks the site's own control and saves the
  download (`page.expect_download()`), so the request is made by the site's own code in
  the user's session.

## 7. Remaining routes (none implemented)

1. **The real file, from the official app.** CONFIRMED to work on the phone. The app's own
   share/export can send the PDF to Windows (Google Drive, e-mail, USB). The only way to get
   the *identical* file on a Windows machine without the phone is to run the official
   Android app there, in an Android emulator (e.g. the Android Studio emulator with a Play
   Store image), logged in with the user's own account. Whether the UG app runs and
   exports in an emulator is UNKNOWN; it may refuse devices that fail Google's integrity
   checks, and such a refusal must not be worked around.
2. **Capture the canvas drawing in the user's own browser.** The page's script draws the
   engraving with canvas drawing calls (lines, curves, text in the music fonts). A recorder
   placed in the page, in the user's own logged-in session, could replay those calls into
   SVG/PDF. That would be vector, in the same engraving, but not byte-identical to the
   Android file. Feasibility UNKNOWN: it depends on whether the script draws with vector
   canvas calls or pastes ready-made pictures. It does not touch authentication or cookies,
   but it goes against UG's choice of raster-only printing and may break UG's terms of use.
   The user must check the terms and decide before any work starts.
3. **Android backend.** Ruled out: the export works offline, so there is no server request
   to reproduce. The known mobile API needs the app's signing secret, which is excluded.
4. **MuseScore regeneration** from tab data the user can legitimately get. This is the last
   fallback: a vector PDF in the same style, but not the UG file.

## 8. Not verified (summary)

- Whether the page script draws the canvas with vector calls or pastes pictures (route 2).
- Whether the official UG app runs and exports inside an Android emulator (route 1).
- Print behaviour for tab 2157405 specifically.
- Whether the "Download PDF" of text tabs is vector.
- Whether the offline Android export could have reused a copy cached by an earlier export.
- The content of forum thread t=2724947.
