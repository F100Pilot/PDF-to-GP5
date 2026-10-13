# PDF → GP5

**English** · [Português](README.pt.md)

Turn guitar and bass tablature PDFs — or screenshots of tabs — into **Guitar Pro** files, then
practise them in your browser: notation that plays, a Rocksmith-style 3D highway, the song's audio
and YouTube video in sync, an A–B loop, a metronome and a library of your songs.

[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/F100Pilot/PDF-to-GP5)](https://github.com/F100Pilot/PDF-to-GP5/releases/latest)
[![CI](https://github.com/F100Pilot/PDF-to-GP5/actions/workflows/ci.yml/badge.svg)](https://github.com/F100Pilot/PDF-to-GP5/actions/workflows/ci.yml)

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-PayPal-0070ba?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/F100Pilot)

![Demo: two tab PDFs converted, then the notation and the 3D highway playing](docs/media/demo-en.gif)

## Features

- **Reads tabs in many forms**: text tabs (`e|--0--3h5--|`), PDFs exported by Guitar Pro, MuseScore, TuxGuitar or Songsterr, and pictures of tabs (PNG, JPEG, WebP or scanned PDFs, read by OCR on your computer).
- **Finds the song's details**: title, artist, tempo, time signature, tuning, rhythm, techniques (bends, slides, hammer-ons, vibrato, palm mute…), repeats and lyrics.
- **Writes Guitar Pro files**: `.gp5`, or `.gp` (Guitar Pro 7/8) with the song's audio inside. Up to 7 tracks, 4 to 8 strings.
- **Opens Guitar Pro files** (`.gp`, `.gpx`, `.gp5`, `.gp4`, `.gp3`) to play them.
- **Practice player**: staff and tab, 3D highway, speed, A–B loop that can speed up each pass, metronome and count-in.
- **Plays along with the real song**: an audio file or a YouTube video, lined up with the notation.
- **Library** of your songs, with album covers, that you can move to another computer.
- **Portuguese and English** interface.
- **Private**: it runs on your computer, and your files are not uploaded anywhere.

## Which files work best

| Source | How it is read | Result |
|---|---|---|
| **PDF with real text**: a text tab, or a PDF exported by Guitar Pro, MuseScore, TuxGuitar or printed from Songsterr | The numbers, lines and symbols are in the file itself | **The most reliable.** Use this whenever you can |
| **Picture or scanned PDF**: a screenshot, a photo, a "PDF" that is only an image | Read by OCR (character recognition) on your computer | **Experimental**: good on clean, large pictures; always check the result |

**Quick test:** open the PDF and try to select a fret number with the mouse. If you can, the PDF has real text and will convert well. If the whole page selects as one block, or nothing selects, it is an image.

**Limitations of pictures and image PDFs**
- **Quality matters.** Use the whole page, at least 1000 px wide, without the browser's bars around it. Small, blurred or heavily compressed (JPEG) pictures give wrong numbers, extra notes or missing bars.
- **Numbers can be misread** (a bold 0 read as 6 or 9, for example). The report warns you to check them.
- **Rhythm** is read from the drawn stems, beams and rests when they are clear; otherwise it is estimated from the spacing of the notes, bar by bar.
- **Not read in pictures yet:** tuplets, section names (Intro, Verse…), and tabs written as plain text (`e|--0--3--|`) inside a picture.
- **One picture is one track.** To combine several screenshots of the same part, put them in one PDF.

## Not supported yet

Some notation is not converted yet, or only in part:

- **Tuplets** (triplets, quintuplets…): detected, but the rhythm of that bar is estimated.
- Grace notes, swing feel, pickup bars and key signatures.
- Accents, staccato, fingering, crescendo/decrescendo hairpins, and pick-stroke marks (⊓ / V).
- Trills, tremolo picking, whammy bar (dips and dives), wide vibrato, volume swells, and bend + release + bend.
- Slap/pop, rasgueado, and harmonics in PDFs exported by editors (in text tabs, `<12>` works).
- Gradual tempo changes (rit. / accel.).
- Capo, chord names and diagrams, a second voice in the same staff, and drums.

The full list, technique by technique, is in [NOTATION.md](docs/NOTATION.md). If your tab uses something missing, open an [issue](https://github.com/F100Pilot/PDF-to-GP5/issues) describing the bar and what it should be.

## Get started

You need **Python 3.11 or later** ([python.org](https://www.python.org/downloads/)) and **Google Chrome** (recommended) or Edge.

**Windows**

1. Download the latest version from [Releases](https://github.com/F100Pilot/PDF-to-GP5/releases/latest) (*Source code (zip)*) and extract it.
2. Double-click `start.bat`. On a work PC without administrator rights, or with the folder on OneDrive, use `start_env.bat`.
3. The first run installs what is needed, which takes a few minutes. The app then opens in Chrome at `http://127.0.0.1:8021`.

To quit, close the app window.

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install --no-deps --ignore-requires-python -r requirements-ocr.txt
.venv/bin/python -m app --port 8021 --close-with-browser
```

Then open `http://127.0.0.1:8021`.

## Documentation

| | English | Português |
|---|---|---|
| User manual | [MANUAL.en.md](docs/MANUAL.en.md) | [MANUAL.md](docs/MANUAL.md) |
| Technical documentation (API, configuration, security, development) | [TECHNICAL.md](docs/TECHNICAL.md) | [TECNICO.md](docs/TECNICO.md) |
| Notes and techniques supported | [NOTATION.md](docs/NOTATION.md) | [NOTACAO.md](docs/NOTACAO.md) |
| YouTube API key (optional) | [YOUTUBE_KEY.md](docs/YOUTUBE_KEY.md) | [CHAVE_YOUTUBE.md](docs/CHAVE_YOUTUBE.md) |
| What's new | [CHANGELOG.en.md](CHANGELOG.en.md) | [CHANGELOG.md](CHANGELOG.md) |

## Support the project

PDF → GP5 is free. If it saves you time, you can buy me a coffee:

[![Buy me a coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-PayPal-0070ba?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/F100Pilot)

Bug reports and ideas are welcome in [Issues](https://github.com/F100Pilot/PDF-to-GP5/issues). See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence and notices

- The code is under the [MIT licence](LICENSE). The bundled third-party components keep their own licences ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
- Use the app only with tabs and music you have the rights to use. YouTube's terms do not allow downloading outside YouTube's own features.
- Guitar Pro is a trademark of Arobas Music, and Rocksmith is a trademark of Ubisoft. This project is not affiliated with or endorsed by either.
