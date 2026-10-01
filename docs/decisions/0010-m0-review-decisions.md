# 0010. Decisions from the M0 review

- **Status:** Accepted
- **Date:** 2026-10-02
- **Plan sections:** 3.2, 4.3, 8.1, 12.3, 13.6, 16.2 ("M0 review decisions"), Reference R4, R5

## Context

The maintainer's review of the M0 pull requests answered four open points. The plan was updated
the same day (16.2, "M0 review decisions"; 12.3; R5).

## Decision

### 1. US spelling in everything the user sees

- Every string the user sees uses US spelling, including names taken from the plan. The risk
  badge reads "Client behavior", M-JOB-01 reads "canceled" and M-IMP-02 "recognizes". The
  plan's own prose, code identifiers and file names keep their spelling.
- The audit covered the message catalogue (every string the app shows), the widgets, dialogs,
  tray and onboarding that feed it, and the user-facing documents. It found and fixed
  "Client behaviour" (badge and README), "canceled" (M-JOB-01 and its log line), "Licence"
  and "license" (README) and "catalogue" (PRIVACY.md).
- `tools/check_spelling.py` runs in CI. It fails on common British spellings (behaviour,
  colour, licence, cancelled, recognise, organise, minimise, favourite, centre, analyse,
  catalogue and others) in the catalogue and in the prose of `README.md` and `PRIVACY.md`.
  Code spans, code blocks and link targets are skipped; any word that must stay goes in
  `[tool.verdra.spelling] allow` with a reason (the list is empty).

### 2. One copy of each legal text

`LICENSE`, `NOTICE` and `PRIVACY.md` exist once, at the repository root. The source tree holds
no copy. `packaging/verdra.spec` copies them into the built app's `assets/legal/`;
`soil/terrain.legal_dir()` returns that folder in a build and the repository root in a source
checkout. Tests check that the About dialog's Privacy text equals the root file, and
`tools/check_build.py` checks that the build carries all three byte for byte.

### 3. Qt libraries allowed in the build scan

Besides the eight modules of plan 8.1, the build scan allows six Qt-internal libraries. Each
was checked against Qt's public source at the `6.11` branch (qtbase commit
`44b6f67476c34716061e9eddcbffcbfcb4cb7842`, qtwayland commit
`35bfd4e8e146fb49fa95f4d58028661a910b2705`), reading the SPDX header of every `.cpp`, `.h`,
`.c` and `.mm` file in the library's source folder:

| Library | Source (github.com/qt/…) | CMake target | SPDX header seen |
| --- | --- | --- | --- |
| DBus | `qtbase/src/dbus` | `qt_internal_add_module(DBus` | 67 files: `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`; 10 documentation snippets: `LicenseRef-Qt-Commercial OR BSD-3-Clause`; 1 file: `AFL-2.1 OR GPL-2.0-or-later` (see below) |
| XcbQpa | `qtbase/src/plugins/platforms/xcb` | `qt_internal_add_module(XcbQpaPrivate` | 79 of 79 files: `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` |
| EglFSDeviceIntegration | `qtbase/src/plugins/platforms/eglfs/api` | `qt_internal_add_module(EglFSDeviceIntegrationPrivate` | 17 of 17 files: same LGPL-3.0 header |
| EglFsKmsSupport | `qtbase/src/plugins/platforms/eglfs/deviceintegration/eglfs_kms_support` | `qt_internal_add_module(EglFsKmsSupportPrivate` | 9 of 9 files: same LGPL-3.0 header |
| WaylandClient | `qtbase/src/plugins/platforms/wayland` (without `plugins/`) | `qt_internal_add_module(WaylandClient` | 123 of 123 files: same LGPL-3.0 header |
| WlShellIntegration | `qtbase/src/plugins/platforms/wayland/plugins/shellintegration/wl-shell` | `qt_internal_add_module(WlShellIntegrationPrivate` | 5 of 5 files: same LGPL-3.0 header |
| WaylandCompositor (rejected) | `qtwayland/src/compositor` | `qt_internal_add_module(WaylandCompositor` | 180 of 180 files: `LicenseRef-Qt-Commercial OR GPL-3.0-only` |

In Qt 6.11 the Wayland client libraries are built from **qtbase**, not qtwayland: qtwayland's
`src/client` only holds a header-only `WaylandClientFeaturesPrivate` target. The client-side
graphics plugins in qtbase (`wayland/plugins/hardwareintegration/*`) carry the same LGPL-3.0
header.

`tools/check_build.py` fails by name on anything from Qt Wayland Compositor: any path part
containing "compositor" (the PySide6 wheel ships `libQt6WaylandCompositor`,
`libQt6WaylandEglCompositorHwIntegration` and QML plugins under `QtWayland/Compositor`) and the
`wayland-graphics-integration-server` plugin folder. That check runs before the allowlist, so
adding the compositor to `[tool.verdra.qt.build-support]` cannot let it through.

Correction found in the self-review: the first version of the scan built its list of "other"
Qt modules from PySide6's Python bindings only. Qt Virtual Keyboard (GPL-only) has no binding,
so its input-method plugin `platforminputcontexts/libqtvirtualkeyboardplugin.so` passed the
scan and shipped in the Linux build. The module list now also comes from every Qt library in
the wheel and from the wheel's own module manifests (`PySide6_*.json`), so the plugin is
rejected and the build leaves it out; a test pins this exact path.

### 4. Licence gate over every dependency group

- 0BSD is on the allowlist (12.3); it is more permissive than MIT.
- `tools/licenses.py` checks every dependency group: runtime, dev and build. CI installs all
  groups first (`uv sync --all-groups`). The gate reads the locked package list for the
  system from `uv export --all-groups` and fails if any of those packages isn't installed, so
  it cannot pass on a partial environment. It now includes pip, setuptools and pip-licenses'
  own dependencies (`--with-system`).
- `--report` prints every package and licence; CI prints it on every run.

### 5. Co-Authored-By trailer

Commits keep the `Co-Authored-By: Claude` trailer for transparency.

## Open questions, settled in round 2

These came up while doing the above; the maintainer settled them in the second review round
(plan 16.2, decision record 0011).

1. **AFL-2.1 inside Qt D-Bus.** `qtbase/src/dbus/dbus_minimal_p.h` holds constants and typedefs
   from the libdbus-1 headers. Checked again in Qt's source at the commit above: its header
   reads `SPDX-License-Identifier: AFL-2.1 OR GPL-2.0-or-later`, and
   `src/dbus/qt_attribution.json` records the "libdbus-1 headers" under the same expression. It
   is compiled into `libQt6DBus`, which the build ships on Linux. **Settled:** AFL-2.1 is a named
   exception, recorded with its reason in `[tool.verdra.licenses.qt-exceptions]` and printed by
   `tools/licenses.py --report`.
2. **"catalogue" in R5.** **Settled:** the UI says "catalog" (R5 M-CAT-01 and M-PACK-02 now read
   "preset catalog"); "catalogue" stays only in format IDs such as `verdra.catalogue`.
3. **NumPy's exception.** NumPy's licence metadata is
   `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`. **Settled:** the exception's reason
   reads "GPL-3.0 with GCC Runtime Library Exception 3.1, which permits distribution inside
   non-GPL programs."

## Licences found by the extended gate (Linux, run 2026-10-01 22:00 UTC)

| Licence | Packages |
| --- | --- |
| 0BSD | chardet |
| Apache-2.0 (any spelling) | uharfbuzz, arrow, cyclonedx-bom, cyclonedx-python-lib, pip-api, pip-audit, py-serializable, requests, sortedcontainers, CacheControl, coverage, DracoPy, license-expression, msgpack, tzdata |
| Apache-2.0 OR BSD | python-dateutil, packaging, cryptography |
| BSD-2/3-Clause | grimp, httpx, import-linter, jsonpointer, lz4, nodeenv, webcolors, boolean.py, Pygments, click, httpcore, idna, lxml, msgspec, prettytable, psutil, pycparser, SecretStorage, zstandard |
| BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | numpy (named exception) |
| GPL-2.0 with the bootloader exception | pyinstaller, pyinstaller-hooks-contrib (build only; named exceptions) |
| ISC | dnspython, isoduration |
| LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only | PySide6, PySide6_Addons, PySide6_Essentials, shiboken6 |
| MIT (any spelling) | anyio, attrs, cfgv, charset-normalizer, filelock, fonttools, identify, iniconfig, jaraco.context, jaraco.functools, jaraco.classes, jeepney, jsonschema, jsonschema-specifications, keyring, more-itertools, pip, pip-licenses, pip-requirements-parser, platformdirs, pre-commit, pyparsing, pyright, pytest, pytest-cov, referencing, rfc3987-syntax, rpds-py, ruff, setuptools, tomli, truststore, urllib3, virtualenv, altgraph, h11, lark, markdown-it-py, mdurl, packageurl-python, pluggy, pytest-qt, python-discovery, PyYAML, rfc3339-validator, rfc3986-validator, rich, six, texture2ddecoder, tomli-w, uri-template, wcwidth |
| MIT-0 | cffi |
| MIT-CMU | pillow |
| MPL-2.0 | certifi, fqdn, hypothesis |
| PSF-2.0 | typing_extensions, defusedxml, distlib |

## Consequences

- New UI text must pass the spelling gate. Plan names with British spelling are written in
  US spelling in the app.
- A Qt update must re-check the six support libraries against this record before the build
  scan's allowlist is trusted again.
- The licence gate takes longer in CI (it installs the build group) and covers every package
  that is ever installed.
