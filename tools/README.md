# Build tools (optional)

Nothing in this folder is needed for the profile to display. The README only uses `assets/`.
Keep this folder if you want to regenerate the SVGs later.

```bash
pip install pillow fonttools brotli pyoxipng   # pyoxipng is optional (smaller PNGs)
python3 tools/build.py                         # rewrites assets/*.svg
node tools/verify.mjs .verify                  # needs Playwright + Chromium
```

- `src/`: your original photos (`id.png`, `right_pointing.png`), converted losslessly from the upload.
- `vendor/fonts/`: Bricolage Grotesque and JetBrains Mono WOFF2 files (SIL OFL 1.1, see `assets/licenses/`).
- `vendor/simple-icons.json`: the brand-icon paths used, with their Simple Icons version and official source.
- `data/github-snapshot.json`: the public GitHub data behind the dashboard, retrieved 2026-11-05.
  Refresh it and rebuild to update the numbers, then bump `?v=1` to `?v=2` in README.md so GitHub's image cache refreshes.

`verify.mjs` renders every SVG at 0, 2, 5, 9 and 13 s, with all animation removed, under
prefers-reduced-motion and inside an `<img>`. It fails the run on external requests, unloaded
fonts, un-namespaced or duplicate IDs, SMIL that doesn't begin at 0s, scripts or
foreignObject, text running off the canvas, or corners that aren't transparent.
