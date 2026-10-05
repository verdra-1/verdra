# 0002. PySide6 (Qt 6, LGPL-3.0) for the interface

- **Status:** Accepted
- **Date:** 2026-10-01
- **Plan sections:** 3.4, 5.6, 8.1, 13.6

> **Current state (5 October 2026):** Windows is the only platform; Linux is paused, planned
> later, and macOS is deferred ([decision record 0018](0018-windows-only.md)). What this record
> says about Linux describes the time it was written.

## Context

Verdra needs one native-feeling desktop interface on Windows, macOS and Linux, with a tray icon,
SVG rendering, OpenGL mesh previews and audio playback, written in Python next to the proxy and
format code. The interface toolkit's licence must allow shipping inside an Apache-2.0 app.

## Decision

- Use PySide6 (Qt for Python) 6.11 or later, under LGPL-3.0.
- Import only these Qt modules: Core, Gui, Widgets, Network, OpenGL, OpenGLWidgets, Svg,
  Multimedia. GPL-only add-ons (Charts, Data Visualization, Graphs, Quick 3D, Virtual Keyboard and
  others) are never used. CI checks every `PySide6.Qt*` import (`tools/licenses.py`).
- The PySide6 Addons wheel installs those GPL-only modules alongside the allowed ones, so they
  are blocked three times: importing them fails CI, the PyInstaller build leaves them out
  (`packaging/verdra.spec`), and CI checks the built folder on every system and fails if any Qt
  library, plugin or QML file outside the allowed modules is present (`tools/check_build.py`).
  The check is an allowlist: Qt-internal libraries the allowed modules load (Qt Base and the
  Qt Wayland client) are named, with a reason, in `[tool.verdra.qt.build-support]`.
- Use the Fusion style on every platform, with a palette and one stylesheet generated from
  `tokens.json` (5.6), so controls look the same everywhere and follow the tokens exactly.
- Ship with PyInstaller in one-folder mode, so the Qt libraries stay separate, replaceable files.

## Consequences

- LGPL-3.0 obligations: Qt libraries ship as separate files; the LGPL-3.0 and GPL-3.0 texts are
  included; the app states where the Qt and PySide6 sources are available
  (THIRD_PARTY_NOTICES.md, About dialog).
- No single-file PyInstaller builds and no static linking of Qt.
- The Fusion style means we draw focus rings, switches and badges ourselves from tokens, rather
  than relying on each platform's native look.
