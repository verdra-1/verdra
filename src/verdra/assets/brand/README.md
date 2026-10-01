# Brand assets

- `tokens.json` is the only place colour values live (Master plan 5). Code reads tokens by name.
  It also holds the type scale, spacing, radii, borders, shadows, motion and layout sizes from
  section 6.
- Every `*.svg` here is **generated** by `tools/icons.py` from the master geometry in section 4.4
  and the tokens. Don't edit them by hand: change the tokens or the geometry and run
  `uv run python tools/icons.py`. CI fails when they're out of date.
- `generated/` holds the raster sizes from section 4.6 (ICO, ICNS, hicolor PNGs, tiles, favicon,
  tray PNGs). It is built with `uv run python tools/icons.py --raster` and isn't committed.

| File | Use |
| --- | --- |
| `symbol.svg`, `symbol-reversed.svg` | The Living V on light and dark surfaces |
| `symbol-mono-dark.svg`, `symbol-mono-light.svg` | Single-colour versions |
| `app-icon.svg` | App icon, favicon, avatars; below 24 px, use this instead of the symbol |
| `wordmark.svg`, `wordmark-reversed.svg` | "Verdra" outlined from the display face, with the node dot |
| `lockup-horizontal*.svg`, `lockup-stacked*.svg` | Symbol and wordmark together |
| `tray-<state>-light.svg`, `tray-<state>-dark.svg` | Windows and Linux tray, for light and dark taskbars |
| `tray-<state>-template.svg` | macOS menu bar template images (black with alpha) |

The geometry is a concept until a designer refines it (4.4); a refinement replaces the paths in
`tools/icons.py` and is logged in the plan's change log.
