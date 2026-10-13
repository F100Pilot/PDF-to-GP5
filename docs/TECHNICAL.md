# PDF → GP5 — technical documentation

[Português](TECNICO.md) · **English**

Formats read, how it works, API, security, configuration and development. To use the app, see the [manual](MANUAL.en.md).

## Supported formats

| PDF type | Example | Support |
|---|---|---|
| Text tab (monospaced) | `e|--0--3h5--|` printed from a `.txt` / website | ✅ |
| Engraved tab from an editor | PDF export from Guitar Pro, MuseScore, TuxGuitar | ⚠️ experimental |
| Engraved tab image (OCR) | PNG, JPEG or WebP screenshot; image-only PDF (a screenshot saved as PDF, a scan) | ⚠️ experimental: numbers, string lines, bar lines, drawn rhythm and written techniques (H/P, P.M., let ring, harmonics), slides, vibrato, ties, legato arcs and bends |
| Text tab as an image | Screenshot of `e|--0--3h5--|` | ❌ not yet (no drawn string lines) |

- 4–8 strings (bass, 6/7/8-string guitar); tuning read from the labels (`e B G D A D` → Drop D) or chosen manually.
- Techniques: hammer-on/pull-off (`h`/`p`), slides (`/`, `\`, `s`), bend (`b`, `7b9`, `7b9r7`), vibrato (`~`), dead note (`x`), ghost note (`(5)`).
- Engraved tabs: bends (bend, pre-bend, release, held bend), vibrato (wavy line), strum arrows (brush), notes in parentheses (a tie if they repeat the fret of the note sounding on the string at the previous beat and, in MuseScore PDFs, which draws ties as arcs, only when an arc reaches the note; otherwise a ghost note), `H`/`P` above the staff (hammer-on/pull-off), `let ring` and `P.M.` with a dashed line, multi-bar rests (from the bar numbers).
- Several systems and pages are concatenated into a single track.
- Images (OCR): the string lines and bar lines are detected in the image (OpenCV) and the numbers are read by a text recognition model ([RapidOCR](https://github.com/RapidAI/RapidOCR), PP-OCR models on ONNX Runtime, which run on the computer, without a network: ONNX Runtime telemetry is turned off with `ORT_DISABLE_TELEMETRY=1`). The title, artist, BPM ("♩ = 97") and tuning ("Tuning: …") are read from the text above the first staff of the image (text detection by the same RapidOCR); in a PDF whose page 1 is an image, they fill in what the PDF's own text lacks (in a screenshot of a web page, the BPM is only in the image). The time signature (the two big numbers on the staff, at the start or at a change mid-way) is also read: the digits are read as digits only, because the model, trained mostly on Chinese, reads a lone big "4" as a Chinese character. The rhythm drawn with the tab ("tab with stems": stems, eighth and sixteenth beams, half-beams, flags, augmentation dots and rests on the staff) is read as in a vector PDF; in a bar where the marks do not add up (a tuplet, a rest of another shape), that bar's rhythm is estimated from the spacing. In the 13 test PDFs drawn as an image, 96.5% of the bars end up with the same rhythm as the PDF (66% by spacing alone); in a web screenshot of a tab, the 24 bars with notes use the drawn rhythm. Rests are recognized by size, as MuseScore (and the sites that use it) draws them. Techniques written as words next to the staff are also read: "H"/"P" (hammer-on/pull-off), "P.M." and "let ring" with the dashes up to the end of the passage, and the harmonics "PH", "AH" and "N.H." — each word near the staff is read and only these are kept, written as the PDF reader expects them, so they apply to the notes as in a vector PDF (in 12 test tabs with these marks, drawn as an image at 1000, 1300 and 1600 px, the techniques of the 1269 marked notes come out as in the PDF, none invented). Slides (straight slanted strokes next to the numbers: between two notes, into and out of a note) are also read, joining the stroke that removing the string line cuts in two (in 10 test tabs, 589 of 590 slides as in the PDF, none invented; none invented in 2049 notes on pages without slides). Vibrato (the wavy line above the staff) is also read: only a line with a single stroke per column, without stems, long and low, rising and falling at least three times at a regular rhythm counts, so words above the staff do not (in 8 test tabs, 382 of 382 vibratos, none invented; none invented in 51 pages full of words above the staff). Ties and legato arcs are also read (an arc reaching a note in parentheses makes it a tie, without an arc it is a ghost note; an arc over a slide makes it a legato slide; an arc to an empty bar extends the note), joining the arc that a bar line cuts and separating consecutive arcs (in 12 test tabs, on staves whose numbers equal the PDF's: 116 of 117 ties, 48 of 48 ghost notes, 47 of 47 legato slides, no arc invented; none invented in 69 images without arcs). Bends are also read: the arrow with the curve rising from the note, the straight arrow of the pre-bend, the downward arrow of the release and the amount above ("full", "1/2") — the tip is a filled triangle tapering to a point and the stem is the blob touching it at the base; only an arrow whose stem comes down to the staff counts (in 8 test tabs at 1300 px: 42 of 42 bends, 37 of 38 releases, 29 of 36 pre-bends; weaker at 1000 px; no bend invented). An image is one track: several screenshots of the same part are joined in a PDF. Works best with the whole page at 1000 px or more in width (string lines 10 px or more apart). In a PDF, pages without a tab with notes in the text that have images, or that have drawn lines and no text, are read by OCR (a Songsterr PDF printed with "Microsoft Print to PDF" has the numbers and words as outlines); the tuning letters to the left of the staff ("C G D# A# F A#") are also read. The analysis and the conversion show a progress bar. Bar numbers and the counts of multi-bar rests are also read (so the song has the right number of bars), and so are the notes in parentheses (ghost notes or ties, as in a PDF). In the 13 test PDFs (exported from editors) drawn as an image, 99.9% of the notes are found and 99.7% get the right fret, with about 4% extra notes (numbers that are not frets): the report asks you to check. For Jet Lag (Simple Plan) as an image, compared bar by bar with the PDF: 119 of 119 bars equal at 1300 px, 116 at 1600 px and 101 at 1000 px (at that resolution, drawn rests are sometimes read as "9"). The title, artist and BPM come out the same as the PDF's in all of them (at 1000, 1300, 1600 and 2600 px), and so does the time signature (with no extra bars).

The detailed status of each note and technique (implemented, partial, to be implemented, unsupported in GP5) is in [`NOTATION.md`](NOTATION.md).

### Metadata

Title, artist, BPM and time signature are detected automatically when the fields are left empty (highlighted text at the top of the page, `Title:`/`Artist:`/`Tempo:` lines, metronome marking `♩ = 118`, time signature glyphs, PDF metadata). Values filled in by the user take priority.

### Rhythm

If the engraved tab has rhythm notation (stems, beams, rests — the "tab with stems" from MuseScore/Guitar Pro), the durations are read directly. Bars with triplets, or whose notation does not add up to the time signature, use the estimate below. Without notation, there are two modes:

- **By spacing** (the default when there are bar lines): the positions of the notes within each bar are quantized to the grid (eighths → sixteenths → thirty-seconds) that fits best. Durations that cannot be represented by a single note value are split with ties.
- **Fixed duration**: all notes have the same note value and the bars are rebuilt from the time signature.

All generated bars add up exactly to the chosen time signature. Always check the preview: the rhythm is an estimate.

## Interface

One page per topic, with the menu on the left (at the bottom, on a phone): **Convert** (the tracks' PDFs, metadata and rhythm), **Result** (summary, warnings, preview and download), **Play** (score, tab or 3D highway, with the audio and video panels beside it), **Audio** (choose the song's audio or get it from an address) and **Settings** (server status and version). Each page has its own address (`#/converter`, `#/tocar`…): the browser's back/forward buttons work and nothing reloads when changing page — the music keeps playing. Sora and IBM Plex Sans fonts included in `app/static/vendor/fonts/` (SIL OFL 1.1).

- **Player**: playback bar always visible at the bottom, with the song's sections (Intro, Verse, Chorus…) above the time bar — clicking a section jumps there —, speed and **A–B loop** (press at the start and at the end of the passage; again to turn off). For practice: **Metronome** (a click on every beat, accent on the first of the bar), **Count-in** (one bar of clicks before starting; not when the song's audio or video plays along, since they would start a bar before the score) and **Speed up the loop** (with the A–B loop on, each round is 5% faster, from the chosen speed up to 100%). The three choices are remembered in the browser.
- **Opening a Guitar Pro file** (.gp, .gpx, .gp5, .gp4, .gp3): chosen or dragged into the same zone as the PDFs, it opens right away, without conversion — read in the browser by alphaTab, with the summary (title, artist, BPM, bars, notes, tracks and tunings), the score, the 3D highway, the audio and the video, and it stays in the library in the format it came in (up to 40 MB: a .gp can carry the audio). A Guitar Pro file opens on its own: with PDFs in the same selection, the page asks you to choose only that one.
- **Library**: each converted song is saved in a folder on the computer — by default `PDF-to-GP5/Biblioteca` in the user's folder (e.g. `C:\Users\<name>\PDF-to-GP5\Biblioteca`), or the one given in `LIBRARY_DIR` — one subfolder per song with the `.gp5` (opens in Guitar Pro), the chosen audio, the cover (`capa.jpg`) and `musica.json` (report and data). "Play" reopens it without converting again, with the audio and the alignment. Converting the same song again replaces the GP5 (keeping the audio and the cover); "Remove" deletes only the app's files (others you put in the subfolder stay). The folder does not depend on the browser or the port: changing port, changing browser or clearing the browser's data loses nothing. It only exists with the app open on the computer itself (`127.0.0.1`/`localhost`); on a copy published on a server, the library stays in the browser of whoever uses it (IndexedDB), as before. Songs that are in the browser move to the folder by themselves when the app is opened at that address (to recover those from another port, open the app once on that port: `python -m app --port 8020`). Variables: `LIBRARY_DIR`, `LIBRARY_MAX_AUDIO_MB` (200, audio of one song).
- **Exporting / importing the library** (to another computer): in the Library, "Export…" lets you choose the songs and saves them in a ZIP (`biblioteca-pdf-to-gp5-<date>.zip`), with one folder per song as in the library — the `.gp5`, the cover, `musica.json` — and `definicoes.json` with the song settings kept in the browser (where bar 1 starts in the audio, tempo, YouTube video and its alignment); the audio (MP3) is not included. On the other computer, "Import…" shows the ZIP's songs to choose from; those that already exist there appear with both dates and which one is newer, and are only replaced if you tick "Replace" (that song's audio stays). Each song's date is that of the computer it came from. Only with the app open on the computer itself (like the library folder).
- **Covers**: when saving a song in the library, the server looks for the album cover by artist and title in the public iTunes search (no key; only a result by the same artist counts, JPEG/PNG image up to 2 MB from Apple's servers, cached for a day) — needs internet. "Find cover" tries again and "Choose image" uses an image of your own (JPEG, PNG or WebP up to 5 MB). The cover is kept in the library, with the song.
- **MP3 in the scores folder** (Chrome/Edge): when you choose the PDFs through the "Drag the song's PDFs or images" zone (click or drag), the app learns which folder they are in (without reading anything else); after getting the MP3 from an address, "Save the MP3 in the scores folder" opens the save dialog in that folder with the name already filled in — just confirm. The folder is remembered in the library. The browser does not allow saving to a folder without this confirmation; in other browsers the button is a normal download.
- **Shortcuts**: Space play/pause · ← → previous/next bar · 1–4 view · [ ] delay/advance the score 0.1 s (with audio) · L A–B loop · **Ctrl K** (⌘K on Mac) searches pages, library songs and commands.
- **Theme**: system, light or dark (Settings; saved in the browser).
- **Languages** / **Idiomas**: Portuguese and English. The choice is at the bottom of the side menu and in Settings → Appearance; by default it follows the browser's language. Changing language reloads the page; the open song is reopened from the library, on the same page. The server's messages (errors, conversion warnings) come in the same language. So does What's new: `CHANGELOG.md` (Portuguese) and `CHANGELOG.en.md` (English), with the same entries. Each language is a dictionary `app/static/i18n-<code>.js`, with Portuguese as the key; new text must have a translation in all of them (see `.claude/skills/pdf-to-gp5-i18n/SKILL.md`; `tests/test_i18n.py` fails if one is missing).
- **Tracks**: the order changes with the arrows or by dragging the ⠿ handle.

## Quick start (Windows)

Two scripts in the project root do `git pull`, install/update the dependencies, open the browser at http://127.0.0.1:8021 and start the server (Ctrl+C to stop):

| Script | For | Python |
|---|---|---|
| `start.bat` | Unrestricted PC | Virtual environment in `.venv`, in the project folder, created on first run |
| `start_env.bat` | Restricted PC (no administrator, project on OneDrive) | Virtual environment in `%USERPROFILE%\venvs\pdf-to-gp5`, created on first run |

Just double-click the script: the app opens in Chrome (in Brave the YouTube video does not play inside the page); without Chrome installed, it opens in the default browser. Chrome opens with a profile just for the app (`%LocalAppData%\PDF-to-GP5\Chrome`, in a separate window), where the graphics acceleration the 3D highway needs is always on, and with `--ignore-gpu-blocklist`, to use the graphics card even if Chrome has it on its list of cards it does not use (common on laptops). The library does not change: it stays in the server's folder. Port and address can be changed in the `PORT` and `HOST` variables at the top of each file.

To stop, just close the app's page in the browser: the server shuts down about 8 seconds after the last page is closed (reloading the page does not shut it down) and the script window closes. You can also use Ctrl+C in the script window.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install --no-deps --ignore-requires-python -r requirements-ocr.txt  # OCR (see below)
.venv/bin/uvicorn app.main:app --port 8021 --workers 1
# http://localhost:8021
```

Personal use on your own PC: `python -m app --port 8021 --close-with-browser` starts the same server and shuts it down when the last page of the app is closed (this is what the startup scripts use). Without `--close-with-browser` (or with `uvicorn` directly) the server only stops with Ctrl+C and ignores the pages' presence notices.

**Installing what is missing from the page**: in Settings → Server status, each missing part that is a Python package (OCR, yt-dlp, FFmpeg, Deno) has an "Install" button, which runs the same two `pip` steps as the startup scripts in the app's environment and shows the last lines of pip if it fails; the automatic video search has "Set up key", which saves the pasted key to `youtube_api_key.txt` (it is never returned to the page). Only with the app open on the computer itself; the commands are fixed, nothing from the request reaches them.

The OCR for tabs in images (RapidOCR) is installed separately, with `requirements-ocr.txt`: the package declares that it only accepts Python up to 3.12, but it works on the newest versions (all the tests pass on 3.13), so it is installed with `--no-deps --ignore-requires-python`; its dependencies are in `requirements.txt`. The startup scripts do both steps; if the OCR one fails, the app runs anyway, without reading images.

Use a single worker: rate limiting and the limit on simultaneous conversions are per process.

## Using the converter in another program

The converter installs as a Python package, without the web app: `pip install "pdf-to-gp5 @ git+https://github.com/F100Pilot/PDF-to-GP5@<commit>"` (with `[ocr]` at the end of the name for tabs in images). It is named `pdf_to_gp5` — the `app/` folder installed under another name, so the converter's code imports its modules relatively (`tests/test_packaging.py` guarantees this). It only brings what the conversion needs (pdfplumber and PyGuitarPro); the app still uses `requirements.txt`.

```python
from pdf_to_gp5 import i18n
from pdf_to_gp5.converter import ConversionOptions
from pdf_to_gp5.sandbox import run_isolated

i18n.use("en")  # warnings and errors in this language
result = run_isolated([pdf_bytes], ConversionOptions(), timeout_s=120, memory_mb=2048)
open("tab.gp5", "wb").write(result.gp5)  # result.report: title, warnings…
```

This is how [RockForge](https://github.com/F100Pilot/RockForge) converts a PDF or an image in "New project".

## Audio from an address (URL → MP3)

In "Song audio" → "Get the audio from an address (URL)": the server gets the audio with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and converts it to MP3 (128–320 kbit/s) with FFmpeg, shows the progress and delivers the MP3, which immediately plays with the score (and can be saved).

- **YouTube, for personal use**: the audio of a video, when the app is open on the same computer it runs on (`http://127.0.0.1:8021` or `localhost`, as the startup scripts open it). "On this computer" means both things: the request comes from this machine and is made to a local address — so a copy published on the internet (even behind a proxy on the same machine) does not become a YouTube converter for its visitors, and there it only accepts Creative Commons videos. YouTube's terms do not allow downloading outside YouTube's own features: use it only with music you have the right to.
- **Other addresses**: a direct audio/video file, content under a Creative Commons licence or in the public domain (as the site indicates), or a site of your own declared in `AUDIO_DOWNLOAD_HOSTS`. Everything else is refused with the reason. No cookies, accounts or DRM formats are used.
- **When it fails, it says why**: yt-dlp's warnings go to the server log (never to the page) and the recognized cause appears on the page — the JavaScript runtime is missing (install Deno), YouTube asked to confirm you are not a robot, age restriction, private or unavailable video, no audio format (update yt-dlp). Without the runtime or `yt-dlp-ejs`, a YouTube video is refused straight away when requested, saying what is missing.
- Security: only `http(s)`, no credentials in the address, no local-network addresses (except declared sites); FFmpeg runs with arguments in a list (no shell); size and duration limits, maximum time per task; one temporary folder per task, deleted after the download, on error, or after 15 min.
- YouTube: accepts the link (`watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`) or just the video ID. The page sends only the ID; the server validates it again (11 characters `A–Z a–z 0–9 _ -`) and builds the address — no host, path or parameter (`list=`, `t=`) from the user reaches yt-dlp. Playlists and channels are refused.
- Dependencies (installed by the startup scripts with `requirements.txt`): `yt-dlp[default]` (includes `yt-dlp-ejs`, the scripts YouTube needs, used locally — never downloaded at run time) and `imageio-ffmpeg`, which brings FFmpeg for Windows, macOS and Linux. Without them, the section warns that it is not available.
- YouTube also needs a JavaScript runtime. `requirements.txt` installs the official **Deno** (the `deno` package from PyPI) in the app's Python environment, without administrator rights or winget, and the app finds it there. A Deno, Node.js, QuickJS or Bun installed on the PC (in the PATH) also works. Without any, the section warns and the other addresses keep working; `/api/health` reports the state in `audio_youtube`.
- Variables: `AUDIO_DOWNLOAD_HOSTS` (e.g. `musica.meusite.pt,nas.local`), `AUDIO_MAX_MB` (200), `AUDIO_MAX_DURATION_S` (1200), `AUDIO_TIMEOUT_S` (300), `AUDIO_TTL_S` (900), `AUDIO_JOBS_PER_MINUTE` (5), `AUDIO_CONCURRENT_JOBS` (1).
- API: `POST /api/audio/jobs` `{"url", "bitrate", "authorized": true}` → `{id, status, progress, message}`; `GET /api/audio/jobs/{id}` (progress); `GET /api/audio/jobs/{id}/file` (the MP3, once); `DELETE /api/audio/jobs/{id}` (cancel).

## Repeats

Repeat signs, the number of times ("x3"), endings (1st/2nd time) and the D.C./D.S./To Coda/Fine jumps go into the file, as do tempo changes. For Rocksmith, which has no repeats, tick "Write out repeats in full" under Rhythm: the repeated bars are copied in the order they are played (the choice is saved in the browser).

## Audio (.gp file)

After converting, you can choose the song's audio (mp3, ogg or wav, up to 100 MB). The audio plays in sync with the score, the 3D highway and the video (Play, Pause, Stop, time bar and speed). The controls (Play, song start, "Mark start", "Delay" / "Advance the score" — the start can fall before 0 —, "Score tempo" for a recording that is not exactly at the PDF's BPM, song volume and notes volume) sit beside the score. On the 3D highway, the song appears drawn on the floor, aligned with playback. The start and tempo are saved per song in this browser. With audio, "Download" gives a `.gp` file (Guitar Pro 7/8) with the audio as an audio track and a sync point at bar 1 ("Mark start" while listening to the audio on the page; the sync can be fine-tuned in Guitar Pro). Without audio, the download is the usual `.gp5` (the GP5 format does not store audio). The `.gp` is created in the browser by alphaTab: the audio does not leave the computer. Inside the `.gp`, the audio is stored as `Content/Assets/backing-track.mp3` (or `.ogg`/`.wav`), with an extension as in Guitar Pro and Songsterr files — alphaTab writes it without an extension and some programs then cannot find it. Check that your converter (for example for Rocksmith) accepts `.gp`; otherwise use the `.gp5`.

## Lyrics

The lyrics printed in the PDF go in full into the GP5 on a track of their own, "Lyrics (vocals)", muted (volume 0): one note per syllable, where the syllable is printed. This way Guitar Pro, TuxGuitar and the GP5-to-Rocksmith (PSARC) converters read all the lyrics. With 7 tracks already in use, the lyrics go to the track that plays in the most bars with lyrics and the page warns about the bars left without them.

## Score

After converting, the page shows the generated GP5's score (staff and tab, tab only or staff only), with all the tracks or only the chosen ones, each in its own colour, and plays it (play/pause/stop, speed, muting tracks; clicking a note starts playing from there). It uses [alphaTab](https://alphatab.net) 1.8.4, included in `app/static/vendor/alphatab/` (works offline) and loaded only when there is a result to show. Licences: alphaTab MPL-2.0, Bravura font SIL OFL 1.1, Sonivox sounds Apache-2.0 (licence files in the same folder). The "YouTube video" button turns the video on and off (off, it stays paused and the score's sound comes back; the choice is remembered). The time bar below the buttons shows the current time and the song's duration; clicking or dragging on it skips ahead or back (the video and the 3D highway follow).

**3D highway (Rocksmith)**: in View, "3D highway" shows a track as in Rocksmith — strings in Rocksmith's colours (low E red at the top), notes with the fret arriving at the strike line, open strings as a bar, trail on long and tied notes, frame on chords, bar and beat lines with the bar number and the sections, panel with the current bar and the progress, camera following the fretboard area, adjustable tilt and side angle (and, with the mouse over the highway, dragging rotates the view around the strings, sideways and up and down, up to 120° on each axis; Ctrl + drag rotates about the line of sight; Shift or right button + drag moves the view; the wheel zooms in or out toward the cursor; a double click resets the view), lyrics at the top with the current syllable, chord name above the frame (computed from the notes; no name when it is not a known chord) and a glow with the number on the string when the note is played (on notes with a bend, the note rises and falls on the string in real time, following the bend). Notes with rounded corners and the fret printed; headstock at fret 0 (wooden head, nut and tuning pegs, with each open string's name in the string's colour). Techniques: bends and pre-bends (the trail rises with the bend — a whole tone reaches the next string — and falls on the release; arrow and amount), slides (slanted trail to the destination fret; in and out), hammer-on/pull-off (H/P, translucent note), palm mute (PM), harmonics (diamond), vibrato (wavy trail), tapping (T), ghost notes (n) and strum direction. It follows the same audio, speed and position as the score. It uses [three.js](https://threejs.org) 0.186.1 (MIT, in `app/static/vendor/three/`) and needs WebGL (graphics acceleration); without WebGL the page warns and keeps the score.

**YouTube video alongside**: after converting, the app searches for the song's video (artist + title) and opens the panel with the first result; the others stay in a list to choose from. The chosen video and the start alignment are saved per song in the browser. The automatic search uses the YouTube Data API and needs a free key (step-by-step guide in [`YOUTUBE_KEY.md`](YOUTUBE_KEY.md)):

1. At https://console.cloud.google.com create a project, enable the "YouTube Data API v3" and, under Credentials, create an "API key" (restrict it to that API).
2. Save the key on the first line of a file `youtube_api_key.txt` in the project folder (next to the startup scripts; the file is not committed to git) or in the environment variable `YOUTUBE_API_KEY`, and restart the server.

The free quota gives about 100 searches per day (each song is searched at most once a day; the server caches the results). Without a key, the panel shows "Search on YouTube" (opens the search already filled in) and you can paste the video's address. The song's start in the video is set with "Mark start" (with the video playing, press on the first beat of bar 1) and fine-tuned with the ±0.1 s / ±1 s buttons. If the video's owner does not allow watching it outside YouTube, the panel says so (choose another video); with the key, the search only returns videos that can be watched outside YouTube. In the panel you can also paste the address of another video (`youtube.com/watch?v=…`, `youtu.be/…`, `/shorts/…`; a `t=` in the address fills in the start). The video follows the score's Play/Pause/Stop, position and speed, with an adjustment of the song's start in the video (in seconds, saved per song in the browser); the score's sound can be muted to hear only the video. It uses the official `youtube-nocookie.com` player controlled by messages (`postMessage`), with no YouTube scripts on the page; needs internet.

## API

| Method | Route | Response |
|---|---|---|
| `GET` | `/api/health` | status |
| `GET` | `/api/options` | tunings, instruments, limits |
| `GET` | `/api/changelog` | published versions and their changes |
| `POST` | `/api/inspect` | JSON: detected title, artist, BPM and time signature (without converting) |
| `POST` | `/api/convert` | JSON: `filename`, `gp5_base64`, `report` (warnings, preview) |
| `POST` | `/api/convert/gp5` | `.gp5` file |

Fields (multipart):
- `file` (required; PDF, PNG, JPEG or WebP; repeat for several tracks, up to 7, in track order).
- Per track (one value per PDF, or a single value for all): `track_name`, `tuning`, `instrument`.
- For the song: `title`, `artist`, `tempo` (20–400), `time_signature` (`auto` or `N/D`, e.g. `6/8`), `rhythm_mode` (`auto`/`spacing`/`fixed`), `fixed_value` (4/8/16), `parentheses` (`tie` = tie, `note` = normal note).

Omitted or `auto` fields are detected from the PDFs.

```bash
curl -F file=@tab.pdf -F tuning=drop_d -o tab.gp5 http://localhost:8021/api/convert/gp5
curl -F file=@guitarra.pdf -F file=@baixo.pdf -F track_name=Guitarra -F track_name=Baixo \
     -o musica.gp5 http://localhost:8021/api/convert/gp5
```

## Security

- The app does not store files: PDFs and images are processed in memory. Uploads above 1 MB are placed by the server (Starlette) in a temporary file, deleted at the end of the request.
- Validation: maximum size (`Content-Length` header **and** streaming count), `%PDF-` signature (or PNG/JPEG/WebP), limits on pages, on pages read by OCR, on pixels per image and on notes, validated fields.
- Each conversion runs in a child process with a per-request **timeout** (process killed) and a **memory limit** (`RLIMIT_AS` + `RLIMIT_CPU` on Linux; Job Object on Windows; on macOS, which refuses the memory limit, only `RLIMIT_CPU`); the result comes back as JSON (never `pickle`) with a maximum size. Number of bars limited.
- Limited concurrency (HTTP 503) and per-IP rate limiting (HTTP 429; IPv6 grouped by /64), checked before reading the request body; inspection has its own budget.
- It only answers to the names in `ALLOWED_HOSTS` (blocks DNS rebinding) and refuses POSTs from another origin (`Origin` different from `Host`).
- Headers: strict CSP with no inline scripts or styles (alphaTab's two style blocks are allowed by hash; workers only from the site itself; only the youtube-nocookie.com player can be embedded), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on the API; optional HSTS.
- Internal errors are never exposed to the client; file names and GP5 metadata are sanitized.
- OpenAPI documentation off by default. `pip-audit` in CI.

Behind a reverse proxy, rate limiting uses the proxy's IP unless you configure `uvicorn --proxy-headers --forwarded-allow-ips=<proxy ip>`.

### Configuration (environment variables)

| Variable | Default |
|---|---|
| `MAX_UPLOAD_MB` (per PDF) | 10 |
| `MAX_TOTAL_UPLOAD_MB` (all PDFs) | 40 |
| `MAX_PAGES` | 40 |
| `MAX_IMAGE_PAGES` (pages read by OCR, per file) | 15 |
| `MAX_IMAGE_MEGAPIXELS` (per image) | 40 |
| `MAX_EVENTS` | 50000 |
| `CONVERSION_TIMEOUT_S` (without progress: each page read gives this time again) | 120 |
| `WORKER_MEMORY_MB` | 2048 (OCR needs ~1.5 GB of address space) |
| `MAX_CONCURRENT_CONVERSIONS` | 2 |
| `RATE_LIMIT_PER_MINUTE` | 20 |
| `INSPECT_RATE_LIMIT_PER_MINUTE` | 60 |
| `MAX_JOB_TIMEOUT_S` (whole request, even with progress) | 900 |
| `MAX_MEASURES` | 2000 |
| `ALLOWED_HOSTS` (comma-separated) | `127.0.0.1,localhost,[::1]` |
| `YOUTUBE_API_KEY` (or file `youtube_api_key.txt`) | — (automatic video search off) |
| `VIDEO_SEARCH_PER_MINUTE` | 10 |
| `ENABLE_DOCS` | off |
| `ENABLE_HSTS` | off |

## Known limitations

- Text tabs in a proportional font misalign the columns; chords may be split.
- In engraved tabs, stems/rhythmic note values, techniques drawn as curves and the notation staff are not interpreted.
- In images (OCR): numbers, string lines, bar lines, drawn rhythm and written techniques (H/P, P.M., let ring, harmonics), slides, vibrato, ties and bends (at 1000 px bends fail more); "(1)" may come out as "11"; numbers that touch the string line (without the white space editors leave) or very small images may fail. A text tab in an image is not read yet.
- One track per PDF (within each PDF, lines with a number of strings different from the majority are ignored, with a warning). Maximum of 7 tracks (MIDI channels of port 1, without the percussion channel).
- Spelled-out chords, ritardando/accelerando ("rit.", "accel.") and, in text tabs, time signature changes are not converted. Repeats, endings, D.C./D.S./Coda/Fine and tempo marks are only read above the tab itself (on a staff with notation and tab, signs printed only on the notation are not read). GP5 stores each navigation sign (Segno, Coda, D.S. al Coda…) only once per song.

## Versions

[Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`, defined in `app/__init__.py`, visible in the interface and in `/api/health`, with a git tag `vX.Y.Z` per version. Changes in `CHANGELOG.md`.

- Each change is recorded under `## [Unreleased]` in `CHANGELOG.md`, without changing the version.
- The version only goes up when several changes are published together: the `[Unreleased]` section becomes `[X.Y.Z] - date` and `__version__` is updated.
- When the app opens, a "What's new" banner shows the versions published since the last one the user saw (kept in the browser); it is closed with "Close". Changes not yet published do not appear.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install --no-deps --ignore-requires-python -r requirements-ocr.txt
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
.venv/bin/pytest -q
.venv/bin/pip-audit -r requirements.txt
```

Structure:

```
app/
  extract/        pdf_reader (chars + lines), ascii_tab, engraved_tab
  rhythm.py       columns → bars with durations
  gp5_writer.py   Score → .gp5 (PyGuitarPro)
  converter.py    pipeline
  sandbox.py      isolated process with timeout/memory limit
  security.py     headers, limits, rate limiting, sanitization
  main.py         FastAPI API + static frontend
  static/         index.html, app.js, styles.css
tests/            unit tests, API and GP5 round trip
```
