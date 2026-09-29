# alphaTab (vendored)

Files copied unchanged from the npm package `@coderline/alphatab` **1.8.4**
(https://github.com/CoderLine/alphaTab), so the app works offline and without npm.

| File | Source in the package | License |
|---|---|---|
| `alphaTab.min.js` | `dist/alphaTab.min.js` | MPL-2.0 (`LICENSE`) |
| `font/Bravura.woff2` | `dist/font/Bravura.woff2` | SIL OFL 1.1 (`font/Bravura-OFL.txt`) |
| `soundfont/sonivox.sf3` | `dist/soundfont/sonivox.sf3` | Apache-2.0 (`soundfont/LICENSE`) |

When upgrading, replace the files and update the style hashes in `app/security.py`
(`ALPHATAB_STYLE_HASHES`) and `ALPHATAB_SHA256` in `tests/test_security.py`.
