## Brill Font Setup

This repository does not ship the Brill font files. The deployed version uses Brill font files under non-commercial EULA.

If you have your own licensed copy of Brill and want to use it locally:

1. Place the font files in this directory.
2. Use these filenames:
   - `Brill-Roman.ttf`
   - `Brill-Italic.ttf`
   - `Brill-Bold.ttf`
   - `Brill-BoldItalic.ttf`
3. If you want the browser to load those files as webfonts, add matching `@font-face` rules back to [`frontend/src/index.css`](../../src/index.css).

The app already falls back to `Gentium Plus` and `Noto Serif` when Brill is unavailable.

You are responsible for obtaining Brill directly from Brill and complying with its license terms. The MIT license for this repository does not apply to the Brill font.
