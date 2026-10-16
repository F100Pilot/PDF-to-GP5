# Third-party components · Componentes de terceiros

The PDF → GP5 code is under the [MIT licence](LICENSE). The components below are included in this
repository, unchanged, under their own licences; each licence file sits next to the component.

O código do PDF → GP5 está sob a [licença MIT](LICENSE). Os componentes abaixo estão incluídos neste
repositório, sem alterações, sob as suas próprias licenças; cada ficheiro de licença está junto do componente.

| Component · Componente | Version · Versão | Licence · Licença | Folder · Pasta |
|---|---|---|---|
| [alphaTab](https://github.com/CoderLine/alphaTab) | 1.8.4 | MPL-2.0 | `app/static/vendor/alphatab/` (`LICENSE`) |
| Bravura font (SMuFL) | from alphaTab · do alphaTab | SIL Open Font License 1.1 | `app/static/vendor/alphatab/font/` (`Bravura-OFL.txt`) |
| Sonivox sound font | from alphaTab · do alphaTab | Apache-2.0 | `app/static/vendor/alphatab/soundfont/` (`LICENSE`) |
| [three.js](https://threejs.org) | 0.186.1 | MIT | `app/static/vendor/three/` (`LICENSE`) |
| [Sora](https://github.com/sora-xor/sora-font) font | — | SIL Open Font License 1.1 | `app/static/vendor/fonts/` (`OFL-Sora.txt`) |
| [IBM Plex Sans](https://github.com/IBM/plex) font | — | SIL Open Font License 1.1 | `app/static/vendor/fonts/` (`OFL-IBMPlexSans.txt`) |

The Python packages listed in `requirements.txt` and `requirements-ocr.txt` (PyGuitarPro, pdfplumber,
FastAPI, RapidOCR, OpenCV, yt-dlp, FFmpeg through imageio-ffmpeg, Deno, …) are not part of this
repository: pip downloads them when the app is installed, each under its own licence.

Os pacotes Python listados em `requirements.txt` e `requirements-ocr.txt` não fazem parte deste
repositório: o pip descarrega-os ao instalar a aplicação, cada um sob a sua própria licença.

## Windows program · Programa para Windows

The Windows program (`PDF-to-GP5-…-Setup.exe` and the portable zip, built by
`packaging/build_exe.py`) carries, besides the components above:

- Python 3.11 ([PSF License](https://docs.python.org/3/license.html)) and every Python package of
  `requirements.txt` and `requirements-ocr.txt`, with the RapidOCR models (Apache-2.0); the licence
  of each, with its full text, is in `THIRD_PARTY_LICENSES.txt` beside `PDF-to-GP5.exe`.
  [PyGuitarPro](https://github.com/Perlence/PyGuitarPro) (LGPL-3.0) is shipped as its source files
  (`_internal/guitarpro/`), which can be replaced by another version. mutagen (GPL), an optional
  part of yt-dlp the app does not use, is left out.
- [FFmpeg](https://ffmpeg.org), an LGPL build ([BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds)),
  unchanged: `_internal/ffmpeg/`, with its licence (`LICENSE.txt`, GNU LGPL 2.1 or later) and where
  the source of that exact version is (`SOURCE.txt`). The GPL build of imageio-ffmpeg is not included.
- [Deno](https://deno.com) (MIT), the JavaScript runtime yt-dlp needs for YouTube: `_internal/deno/`.
- The Microsoft Visual C++ runtime DLLs (`msvcp140.dll`, `vcruntime140.dll`, …), redistributed as
  Microsoft allows, so the OCR runs without installing the "Visual C++ Redistributable".
- The [PyInstaller](https://pyinstaller.org) bootloader (GPL-2.0 with an exception that allows
  distributing programs built with it under any licence).

O programa para Windows inclui também o Python 3.11, todos os pacotes Python (licenças completas em
`THIRD_PARTY_LICENSES.txt`, junto do `PDF-to-GP5.exe`), o FFmpeg numa versão LGPL (`_internal/ffmpeg/`,
com a licença e onde está o código-fonte), o Deno, as DLLs do Visual C++ da Microsoft e o carregador
do PyInstaller, cada um sob a sua licença.
