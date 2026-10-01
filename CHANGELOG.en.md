# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).
While the version is `0.x`, the API and the reading heuristics may change between minor versions.
Changes accumulate under `[Unreleased]`; the version only goes up when several are released together.

## [Unreleased]
### Added
- Tabs in images: the rhythm drawn with the tab (stems, 8th and 16th beams, partial beams, flags, dots and rests on the staff) is now read, as in a vector PDF; only bars whose marks do not add up keep the rhythm estimated from the spacing. In the 13 test PDFs drawn as images, bars with the same rhythm as the PDF go from 66 % to 96.5 % (Jet Lag: 100 %); in the web print of an Ultimate Guitar Official tab ("You're A God"), all 24 bars with notes use the drawn rhythm.
- Tabs in images (OCR, experimental): PNG, JPEG or WebP prints/screenshots, and PDFs that are only images (a print saved as PDF, a scan), are now converted. The string lines and bar lines are found in the image and the numbers read by a text-recognition model that runs on the computer (RapidOCR); nothing leaves the computer (ONNX Runtime's telemetry is turned off); the rhythm is estimated from the spacing and the report asks you to check the notes (bends, slides, ties and other techniques are not read). In a PDF, only the pages with no text or engraved tab are read this way. In the report, the format shows as "image (OCR)". Limits: 15 pages read by OCR per file (`MAX_IMAGE_PAGES`) and 40 megapixels per image (`MAX_IMAGE_MEGAPIXELS`).

- Tabs in images: the title, artist, BPM ("♩ = 97") and tuning are read from the text above the first staff, and fill in the form as with a PDF. In a PDF that is only images, when page 1 has no text of its own.
- Tabs in images: the time signature (the two big numbers on the staff, at the start or at a change mid-song) is now read. In a PDF whose page 1 is an image but has some text (a printed web page: title and artist as text), the BPM and time signature that are only in the image are read too; they used to stay at 120 and 4/4.

### Changed
- `start.bat` and `start_env.bat` open Chrome with a profile of the app's own, where graphics acceleration (WebGL) is always on, and with `--ignore-gpu-blocklist`: on a laptop with acceleration turned off, or with its graphics card on Chrome's block list, the 3D highway did not show.
- Faster tabs in images: numbers are read in batches at their real width (the model read each one on a 320 px line) — Jet Lag as an image goes from 60 s to 16 s; when a file is chosen, the analysis that fills in the form no longer reads the frets (3 s instead of 15 s).
- Windows startup scripts renamed: `start-casa.bat` is now `start.bat` and `start-trabalho.bat` is now `start_env.bat` (the one with the virtual environment).
- The conversion process may use up to 2048 MB (`WORKER_MEMORY_MB`, was 1024): OCR needs about 1.5 GB of address space.

### Fixed
- Rhythm of staves printed close together: a staff could take the stems of the staff above (ending less than 3 spaces from it) when those outnumbered its own.
- Tabs in images (OCR), tested with Jet Lag (Simple Plan) drawn as an image and compared bar by bar with the PDF — from 108 to 119 matching bars out of 119:
  - Notes in parentheses: the parentheses were read as "1" ("(2)" became 12 or 21); they are now recognised by their shape and by the chord (when the other notes in the column are in parentheses) and the note becomes a ghost note or a tie, as in a PDF.
  - Rests drawn on the staff are no longer read as "1".
  - Bar numbers and multi-bar rests: they are read (the small number over each bar and the big number over the rest), and the song gets the right number of bars — bars used to be missing and the rest came early. A number cut at the picture's edge or misread is dropped and, where possible, worked out from its neighbour and the rest's count.
  - A double bar line (‖) read as two bars.
  - Chords in small pictures: numbers on neighbouring strings that touch were dropped (at 1000 px, 84 % of notes found; now 99 %).
  - BPM next to another number ("♩ = 145" followed by a rest's "3" was read as 1453).
  - Small prints (such as an Ultimate Guitar Official tab printed to PDF, 990 px per tab line): where the string line touches the number, a 4 lost its bar and a 6 the top of its loop, and they were read as 1 and 5; and digits read as letters ("d" for 0, "的" for 9) were dropped — they are now read again as digits only. In "You're A God": from 92 % to 99.6 % of notes right, with no extra notes (there were 9).
- Notes in parentheses taken for ties: a note kept sounding over bars where its string is not even played (Simple Plan "Jet Lag", bars 77–90: the open low E from bar 76 to 82), and repeated palm-muted notes (`(9)(9)(9)…`) became one long note. A tie now only continues a note sounding on the string in the beat before and, in MuseScore PDFs (which draw ties as arcs), only when an arc reaches the note, also when cut at the start of a line; without an arc, the note in parentheses is a new note (ghost note).
- `start.bat` (formerly `start-casa.bat`) installed the dependencies into the PC's shared Python (`pip install --user`) and changed versions other apps need: on the same PC as RockForge, PyGuitarPro went down to 0.9.3 (RockForge asks for 0.10 or later) and OCR brought NumPy 2 (RockForge asks for below 2). It now uses its own virtual environment, in `.venv` in the project folder, like `start_env.bat`.
- A written tuning with the notes run together ("Tuning: D♯ G♯ C♯ F♯A♯ D♯", as in an Ultimate Guitar print saved as PDF): it was ignored and the track stayed in standard tuning.

## [0.7.0] - 2026-09-30
### Added
- App in Portuguese and English: language picker at the bottom of the side menu and in Settings (defaults to the browser's language). The whole interface and the server messages (conversion errors and warnings, audio, library) follow the chosen language. A new language is a dictionary `app/static/i18n-<code>.js`; the `pdf-to-gp5-i18n` skill and `tests/test_i18n.py` make sure new text reaches everyone translated. So does What's new: `CHANGELOG.en.md`, with the same releases and entries as `CHANGELOG.md` (`tests/test_changelog.py` checks it).
- Skill `rockforge-alphatab-check` (runs in the Claude session when asked to compare with RockForge): compares, note by note and per track, what RockForge makes of a `.gp5`/`.gp` with what alphaTab plays — by bar played and position, with ties, hammer/pull, bends, harmonics, slides and graces in Rocksmith terms.
- Skill `gp-alphatab-check` (`.claude/skills`, runs in the Claude session when asked to compare): compares, note by note, a `.gp5`/`.gp` with what alphaTab reads from it and with what survives when alphaTab saves it as `.gp` (bends, graces, harmonics, slides, ties, dynamics, rhythm, repeats…). Uses the app's alphaTab in a headless Chromium (Playwright, in `requirements-dev.txt`).
- Library in a folder on the computer (`~/PDF-to-GP5/Biblioteca`, or `LIBRARY_DIR`), one subfolder per song with the GP5, the audio, the cover and `musica.json`: it is no longer lost when changing port or browser, or when clearing browser data. Only with the app open on the computer itself; on a published copy it stays in the browser. Songs saved in the browser move to the folder on their own (those from another port: open the app once on that port).
- Covers in the library: the album cover is looked up by artist and title (public iTunes search, through the server — `/api/cover`, rate-limited by `COVER_SEARCH_PER_MINUTE`) and saved with the song; "Find cover" tries again and "Choose image" uses your own image.
- MP3 obtained from an address, saved in the scores folder (Chrome/Edge): the PDFs you choose or drag in let the app know the folder, and "Save the MP3 in the scores folder" opens the save dialog in that folder with the name filled in; the folder is remembered in the library.
- Library: converted songs are kept in the browser (IndexedDB) with the report and the chosen audio; "Play" reopens the song without converting again, with the audio and the sync. Search by title/artist, two-step removal and space used.
- Player: playback bar fixed at the bottom, with the song's sections (in the order they are played, with repeats) above the time bar — the current one highlighted, clicking jumps there — and A–B loop.
- Keyboard shortcuts (Space, ← →, 1–4, [ ], L) and Ctrl K / ⌘K to search pages, library songs and commands (play, view, loop, theme).
- System theme, light or dark, chosen in Settings (applied before the page appears, with no flash).
- Tracks: reorder by dragging the handle (the arrows stay, for the keyboard).
- Strum drawn as a wavy arpeggio line with an arrow (editor tabs): the chord that follows gets a strum (up arrow = from the low strings to the high ones), as already happened with straight arrows. The rotated glyph is placed where it is drawn.
- Pinch (PH), artificial (AH) and natural (N.H.) harmonics in editor tabs: the text above the staff with a dash to the end of the span marks the notes in that span, also when it continues on the next line; in the GP5 they become pinch / artificial (an octave up) / natural harmonics.
- Bend on a tied note (a stem with no number, after a tie): the bend curve that starts on that stem now bends the tied note, with the release when the arrow goes down further on; before, the bend was lost.
- Triplets and sextuplets in editor tabs (MuseScore): the notes under a "3" or "6" with a square bracket are read as a triplet (3 in the time of 2) and written as such in the GP5; before, the whole bar fell back to rhythm estimated from the spacing. Other numbers (5, 7…) still give estimated rhythm.
- Grace notes in editor tabs (MuseScore): the small numbers before a note become a grace note of that note in the GP5 (with a hammer-on when there is an "H"/"P"), instead of normal notes that broke the bar's rhythm; the crossed-out stem no longer counts as time. A grace note with no note on the same string after it is ignored.
- Staccato (dot above the note) in editor tabs.
- Crescendo and diminuendo (the "<" / ">" drawn below the staff): the notes' volume changes gradually along the marking, also when it continues on the next line, up to the dynamic that follows (e.g. f → ppp); with no dynamic after it, it goes up/down two levels and stays at that level. In the GP5 they are Guitar Pro's 8 levels (ppp … fff).
- YouTube URL → MP3 for personal use: with the app open on the computer itself (127.0.0.1/localhost, as the startup scripts open it), the audio of a YouTube video is now fetched and converted to MP3 — before, only Creative Commons videos, and a song's music was always refused. Requests from another computer, or through a public name (proxy), remain limited to Creative Commons.
- When the audio from an address fails, the page states the cause: the JavaScript runtime (Deno/Node.js) is missing, YouTube asked to confirm you are not a robot, age restriction, private or unavailable video, or no audio format. A YouTube video without the runtime or `yt-dlp-ejs` is refused right at the request, with what is missing.
- Audio panel: ▴ collapses it (leaving only Play and the time; the choice is saved in the browser) and ✕ hides it, giving the whole width to the score; the audio keeps playing and the panel comes back with the "Audio" button next to the score's Play.
- URL → MP3, YouTube: the page sends only the video ID and the server validates it and builds the address (no host, path or parameter from the user reaches yt-dlp); playlists and channels refused. `yt-dlp[default]` (with `yt-dlp-ejs`, used locally, with no remote components) and detection of the installed JavaScript runtime (Deno, Node.js, QuickJS or Bun), needed for YouTube; `/api/health` and the page say if it is missing. The technical limits (playlists, live, duration) are kept separate from the authorization check, and the downloaded file is confirmed to be inside the task folder.
- Getting the audio from an address (URL → MP3): the server downloads with yt-dlp and converts to MP3 with FFmpeg (128–320 kbit/s quality), with progress and cancellation; the MP3 is immediately ready to play with the score and can be saved. Only content that may be downloaded (a direct file, Creative Commons / public domain, or your own site in `AUDIO_DOWNLOAD_HOSTS`); anything else is refused with the reason. Address validation (http(s) only, no credentials or local network), FFmpeg without a shell, limits on size, duration and time, and a temporary folder per task deleted at the end. New dependencies: `yt-dlp` and `imageio-ffmpeg` (FFmpeg included).
- Score: only one instrument track at a time (chosen with a radio button), with the optional "Lyrics (vocals)" below it; the same track is shown in the 3D highway (and the lyrics no longer appear in the 3D highway's list).
- 3D highway: the camera tilt goes all the way to the top-down view, vertical (slider fully to the right), to line the notes up with the drawing of the music on the floor without perspective; the side angle does not apply in that view.
- The audio sync is saved per song (artist – title) in the browser: when you convert the same song again, the start and the score tempo come back as they were, and the name of the audio used last time appears.
- "Score tempo" in the audio panel (±0.1 BPM, Reset): the score plays at the recording's tempo when it is not exactly at the PDF's BPM (the drift no longer grows over the song); the video and the audio follow it and the .gp gets that tempo.
- The song start in the audio can be before 0 (the score starts before the audio, which waits): "Advance the score" no longer stops at 0.
- 3D highway: with audio chosen, the music is drawn on the floor (intensity over time), placed with the same start and tempo as playback, to line the beats up with the notes and the beats.
- "Delay the score" / "Advance the score" buttons (0.1 s and 1 s) in the audio and video panels, instead of the ±, showing the sync applied; they work while playing.
- Audio controls next to the score (in the video column), always visible when scrolling down the page, with "Song volume" and "Notes volume" (saved in the browser); they replace the audio's "Mute the score's sounds" option.
- Song audio playing with the score: Play (in the audio panel or on the score) plays both, and Pause, Stop, the time bar and the speed control the audio too; "Mark start" restarts the score at bar 1 at the marked moment, with ±0.1 s/±1 s buttons to fine-tune; "Play with the score" and "Mute the score's sounds" options. Audio panel looking like the rest of the page (without the browser's player).
- Application icon in the browser tab (`GET /favicon.ico 404` no longer shows up on the server).
- D.C., D.S., Segno, Coda, "To Coda" and Fine (D.C./D.S. al Coda, al Fine): read above the tab (Segno and Coda symbols and text in engraved tabs; text above the tab or after the line in text tabs) and written to the GP5. The score, the 3D highway and the time bar follow the jumps; with "written out" the song is written in the order it is played, with the right tempo after each jump. The summary shows the "Navigation".
- Tempo changes in the middle of the song ("♩ = 90", "= 90", "Tempo 90" above the tab): each goes into the GP5 at its bar (the score, the 3D highway, the video and the time bar follow) and they appear in the summary. The mark at bar 1 is the song's tempo; a tempo chosen in the form replaces it.
- Option "Write repeats out in full (for Rocksmith, which has no repeats)" (under Rhythm; the choice is saved): the GP5/.gp gets the repeated bars copied in the order they are played (endings and repeats inside repeats included, in the same order as the page's player), with no repeat signs; the lyrics, the section markers and the 3D highway follow each pass.
- Song audio in the Guitar Pro file: after converting, you can choose the song's mp3 (or ogg/wav); the download becomes a .gp file (Guitar Pro 7/8) with the audio as an audio track and the song start marked ("Mark start" while listening to the audio on the page). Without audio, the download is still .gp5. The .gp file is created in the browser (with alphaTab): the audio is not sent to the server.

### Changed
- Conversion report: the text tab preview only appears on tracks read from a text tab; on a tab engraved by an editor it no longer appears (the result is seen on the score).
- Bends in the GP5 the way alphaTab plays them: the simple bend and the pre-bend with release now have only two points (a line along the note), so Guitar Pro and TuxGuitar show the same curve as alphaTab. Bend + release still has 4 points.
- Skill `rockforge-alphatab-check`: also compares the bend's shape (`bend curve` line), not just its size.
- Audio panel, song start: the value sits in the center, always with hundredths of a second, with −1 −0.1 −0.01 on the left (advance the score) and +0.01 +0.1 +1 on the right (delay); "Mark start" moves down. In the narrow panel, the value sits above the buttons.
- Default port changes from 8020 to 8021 (`python -m app`, startup scripts and README). The browser stores the library and preferences per address: what was saved at `127.0.0.1:8020` does not show up at `127.0.0.1:8021`.
- Audio panel in the player: collapsing it tucks it to the side, into a narrow bar (expand, Play/Pause), and the score gets the full width; with the video panel also open, only the title line and Play remain. The button that shows the panel again after closing it with ✕ moved to the playback bar (always visible), and it is also in Ctrl K ("Show the audio panel").
- New interface, with one page per topic and a menu on the left (tab bar at the bottom, on phones): Convert, Result, Play, Audio and Settings. Each page has its own address (`#/tocar`…), the browser's back/forward works and changing page does not interrupt the music. After converting, Result opens; "Open in player" takes you to the score. Pages without a song show what to do. The audio sync panel stays next to the score, collapsing and hiding as before. New Settings page with the server status (conversion, URL → MP3, YouTube, video search) and the version. Refreshed look (system light/dark theme, Sora and IBM Plex Sans fonts included in the app); the What's new panel sits on the Convert page, with limited height.

### Fixed
- `.gp` with audio: the audio now goes inside the file as `backing-track.mp3` (or `.ogg`/`.wav`), with an extension as in Guitar Pro and Songsterr files. alphaTab saved it as `backing-track`, with no extension, and RockForge versions before 09/30 did not find the audio. Only the name changes: the audio is the same, byte for byte.
- Bend with release (e.g. ½ going up and back) disappeared when saving the GP5 as `.gp` (Guitar Pro 7/8) with alphaTab: it was written with 5 points and the `.gp` format only stores 4 (origin, two in the middle and destination) — alphaTab's exporter drops the bend without warning. It now has 4 points, with the same shape.
- Audio panel closed with ✕: a "◂ Audio" tab appears on the score's right margin to open it again, and the playback bar button now says "Show audio" / "Hide audio" (before, it only said "Audio" and went unnoticed).
- Tied notes with only a stem (continuation of a tie) got the default volume (f) instead of the dynamic in effect: the score showed "f" in the middle of the bar and the sound jumped up.
- Empty bar crossed by a tie (the tied note is not printed and the whole note has no stem): it now continues the note for the entire bar, instead of being a rest.
- Line with only half notes (short stems): they were read as quarter notes, because the "normal" stem was measured on the line itself; the bar ended up with estimated rhythm.
- Dynamics written with one letter per glyph ("ppp" as three "p", "mf" as "m" + "f"): they were read as p and f; they are now ppp and mf.
- 3D highway: the bar of an open string (0) no longer takes up the fret window of several beats (often 5 or more); it gets the width of the largest hand position in that window, at least 4 frets.
- Conversion and PDF analysis failed ("zip() argument 2 is longer than argument 1") when a line below the tab only had markings such as "let ring" or "PM".
- Lyrics: "let ring", "P.M." and "palm mute" markings printed on the same line as the lyrics no longer end up in the lyrics.

## [0.6.0] - 2026-09-29
### Added
- Repeats: repeat signs `|: :|` (repeat dots in engraved tabs; `|:`, `:|`, `|*`, `|o` in text tabs), number of times ("x3", "3x", "(x3)", "3 times"; 2 when not written) and 1st/2nd endings ("1.", "2.", "1., 2.") go into the GP5. In text tabs, "x4" after a line without signs repeats the whole line. The score plays the repeats, and the 3D highway and the time bar follow the order in which the song is played (the bar shown is the printed one).
- Time signature changes in the middle of the song (e.g. a bar in 2/4 or a section in 3/4): each bar keeps its own time signature in the GP5, on the score and in the 3D highway; the courtesy signature at the end of the line and the number above multi-bar rests do not count as a change. The summary shows the time signature changes and the number of repeats; the text preview shows `|:`, `:|x3`, `[1.]` and `[3/4]`.
- Turning the video off: the "YouTube video" button turns the video on and off. When off, the video is paused, stops following the score and the score's sound comes back (even with "Mute the score's sounds" checked); the choice is saved and the following songs neither open nor search for the video until you turn it back on.
- Song time bar below the score's buttons: current time and duration ("0:42 / 3:03", song time, the same at any speed); clicking or dragging moves forward or back, and the video and the 3D highway follow. In the 3D highway, the progress bar shows the same time and can also be clicked.
- "What's new" banner on entering the app with the changes from versions the user has not yet seen.
- Several tracks: load several PDFs (one per track, up to 7) and get a single GP5; name, tuning and sound per track, adjustable order; shorter tracks padded with rests (with a warning).
- Track name detected in the PDF ("Bass", "Electric Guitar"…) or in the file name ("Artist - Song - Bass.pdf" → "Bass").
- Notes in parentheses (e.g. `(0)`) that repeat the previous fret are ties (the note sustains; importers such as Rocksmith's convert them into sustain). In Guitar Pro the tie shows on the staff; the fret is not repeated in the tab.
- Tracks aligned by the printed bar numbers: unread bars are filled with a rest in the right place (with a warning saying which), instead of throwing the rest of the song out of alignment.
- Strum arrows (↑/↓) in engraved tabs converted into a brush effect in the GP5.
- Bends in engraved tabs: bend (curved arrow), pre-bend (straight arrow), release (downward arrow) and held bend on tied notes, with the amount indicated (½, 1, 1½, 2).
- Vibrato (wavy line) applied to the notes it covers, including tied notes with only a stem.
- Rocksmith-style 3D highway (three.js, included in the app): one track at a time, strings in Rocksmith colors, notes with the fret, open strings, long notes, chords and a camera that follows the neck, synchronized with the score's playback. Notes with rounded corners and the fret printed on the face (no artifacts), 3D headstock with nut, tuning pegs and the tuning names in each string's color; soft glow (no white flash on chords) and the chord name well above the notes. Bar and beat lines, bar number, sections, progress panel, camera tilt and side angle, lyrics at the top, chord names (computed from the notes) and a glow with the number when the note reaches the strings; on bends the note rises (and falls on the release) in real time. Techniques on the highway: bends (the trail rises and falls as in Rocksmith), slides, hammer-on/pull-off, palm mute, harmonics, vibrato, tapping, ghost notes and strum, with a legend.
- Full-screen page: on wide screens, a two-column form, tracks side by side and the score at full width.
- Full lyrics in the GP5: a muted "Lyrics (vocals)" track (volume 0, voice sound), with one note per syllable where it is printed; Guitar Pro, TuxGuitar and the Rocksmith (PSARC) converters read all the lyrics from that track. If there are already 7 tracks, the lyrics go to the track that plays in the most bars with lyrics (with a warning about the bars left without them). The 3D highway shows the PDF's full lyrics, at the right time.
- Guide to creating the YouTube API key: `docs/CHAVE_YOUTUBE.md`. The key is read even when saved with a BOM or in UTF-16 (Notepad); the server says at startup whether search is on or why not, and the panel shows the same reason.
- Video: when the video's owner does not allow watching it outside YouTube, it also tries the regular YouTube player and then moves on by itself to the next search result until it finds one that plays (10 results per search); if none plays, it says how many were tried. In Brave (whose Shields block the embedded player), the message says how to unblock it.
- Video: if the youtube-nocookie.com player refuses the page, the regular YouTube player is used; when the video does not play, "Open the video on YouTube" appears (at the start of the song).
- Video: "Mark start" sets the song start in the video at the moment you click (video time), ±0.1 s / ±1 s buttons to fine-tune, a clear message when the video's owner does not allow watching it outside YouTube, and a search only for videos that can be watched outside YouTube.
- The song's video is searched for automatically on YouTube (artist + title) and appears in the panel, with the other results to choose from; it needs a YouTube Data API key (`youtube_api_key.txt` or `YOUTUBE_API_KEY`); without it, a link to the YouTube search.
- YouTube video in a panel next to the score / 3D highway, synchronized with Play, Pause, Stop, position and speed, with start sync and an option to mute the score's sounds.
- Score on the page after converting (alphaTab, included in the app): staff and tab, tab only (with rhythm) or staff only; choose the visible tracks; play, pause, stop, speed and mute tracks.
- Each track has its own color (1st blue, 2nd orange, 3rd green…), the same in the app and in the GP5 file (Guitar Pro / TuxGuitar).
- Server shutdown when closing the page: it no longer gets stuck on "Shutting down" when the browser keeps connections open (it waits at most 3 s for them and, if needed, forces the exit).
- Closing the app's page shuts down the local server (startup scripts; `python -m app --close-with-browser`); reloading the page does not shut it down.
- Text tabs: entry slide (`/5`, `\5`) and exit slide (`5\`, `5/`), pre-bend (`7pb9`, `7pb9r7`), natural harmonic (`<12>`), tapping (`t12`) and palm mute / let ring lines above the tab (`PM----|`, `let ring---`).
- Slides in engraved tabs: slide between notes (legato with an arc, shift without an arc), entry slide and exit slide.
- `docs/NOTACAO.md`: a record of all notes and techniques, with the implementation status of each.
- Sections (Intro, Verse, Chorus…) converted into GP5 markers (engraved and text tabs).
- Song lyrics imported into the GP5 (up to 5 blocks, on the track with the most notes).
- Tuning written in the PDF ("Tuning: D A D G B E", "Drop D", "Eb standard"…) and free tunings.
- Dynamics (ppp … fff) applied as note velocity.
- The startup scripts open the app in Chrome (in Brave the YouTube video does not play inside the page); without Chrome, in the default browser.
- Startup scripts for Windows: `start-trabalho.bat` (virtual environment outside OneDrive) and `start-casa.bat` (no virtual environment); both do `git pull` and start the server.
### Fixed
- Video panel: long titles in the search results stretched the panel off the screen; now the panel stays in its column and titles are cut off with "…".
- Windows: the `ConnectionResetError: [WinError 10054]` (`_call_connection_lost`) error no longer shows up on the server when the browser closes a connection; it was just noise, nothing failed.
- After an update, the page could keep using the old version saved in the browser; the page's files are now always revalidated.
- Tabs with more than 7 strings now give a clear error (the GP5 format only stores 7 strings; before, it generated an invalid file). The 8-string tuning was removed.
- Multi-bar rests at the start of the song (the rest's thick bar broke staff detection and the first line was lost).
- Rhythm: half notes (short stems), eighth notes with a flag, dotted notes and stems without a fret (tied continuation) are now read; musical symbols located despite the font's text-box offset.
- Strum arrows were no longer mistaken for bar lines (they created extra bars).
- Security: memory limit on Windows too (Job Object) and CPU limit on Linux/macOS; maximum timeout per request; limit on bars and bar numbers; `Host` (`ALLOWED_HOSTS`) and `Origin` verification; rate limit and concurrency checked before reading the upload, with its own budget for inspection and IPv6 grouped by /64; failure to start the conversion process returns 503.
- Interface: total size of the PDFs validated before sending; Convert button blocked during inspection; a new selection clears the previous state.
### Changed
- Default port of the startup scripts and the documentation goes from 8000 to 8020.
- API: `file` can be repeated (one per track); `track_name`, `tuning` and `instrument` accept one value per PDF; the report has the `tracks` list. `/api/inspect` returns `part_name`, `strings` and `tuning`.

## [0.5.0] - 2026-09-28
### Added
- `POST /api/inspect`: detects title, artist, BPM and time signature without converting.
### Changed
- Interface: choosing the PDF runs the inspection right away; the Metadata section only appears afterward, filled with the detected values (editable) and the detected time signature preselected.
- Parentheses allowed in the downloaded file's name.

## [0.4.0] - 2026-09-28
### Added
- Rhythm read from the rhythmic notation of engraved tabs (stems, eighth-note beams, flags, dots, rests); bars whose notation does not add up to the meter are estimated from the spacing, with a warning.
- Automatic detection of title, artist, BPM and time signature (highlighted text, "Title:/Artist:" fields, metronome marking, time signature glyphs, PDF metadata).
- Version visible in the interface and in `/api/health`.
### Changed
- API: `numerator`/`denominator` replaced by `time_signature` (`auto` or `N/D`); empty or omitted `title`, `artist` and `tempo` mean "detect".

## [0.3.0] - 2026-09-28
### Added
- Notes in parentheses (tie or ghost note), `H`/`P` (hammer-on/pull-off), `let ring` and `P.M.` in engraved tabs.

## [0.2.0] - 2026-09-28
### Fixed
- Missing bars in engraved tabs: staves without notes, short staves, lines drawn in segments, discarded fret digits, multi-bar rests.
- Text tabs: unknown symbols, double spacing, systems without a blank line.

## [0.1.0] - 2026-09-28
### Added
- First version: conversion of text and engraved tabs to GP5, web interface, API, processing isolation.
