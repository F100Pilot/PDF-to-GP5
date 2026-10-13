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
