# Provenance

One entry per module under `src/verdra/`, as required by Master Build Plan section 3.1 (process
control 3): what the module was built from. Allowed inputs are the specs in `docs/specs/`, public
documentation, Roblox's observable behaviour captured with Verdra's own tools, and the libraries
in the licence allowlist. Each entry ends with the date it was written. No entry may cite another
asset-replacement tool's code.

`tools/check_docs.py` fails CI when a module has no entry or an entry has no date. Name a
module by its path relative to `src/` in backticks; a package's `__init__.py` may be named by its folder.

| Module | Built from | Libraries | Date |
| --- | --- | --- | --- |
| `verdra/` | Reference R1 (module tree) | Standard library (`importlib.metadata`) | 2026-10-01 |
| `verdra/__main__.py` | Reference R1, spec S-01 | Standard library | 2026-10-01 |
| `verdra/bark/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/bark/husk.py` | Master plan 9.1, 10.6, 16.2 (R-10 CA-key fallback), spec S-10, Reference R3; `keyring` documentation (backends, errors); POSIX file-mode documentation | keyring | 2026-10-03 |
| `verdra/bark/nectar.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/bark/pollinator.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/bark/rain.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/bark/resin.py` | Master plan 10.2, 10.3, spec S-10; RFC 5280 (4.2.1.1, 4.2.1.2, 4.2.1.3, 4.2.1.6, 4.2.1.9, 4.2.1.10, 4.2.1.12); `cryptography` X.509 and verification documentation | cryptography | 2026-10-03 |
| `verdra/bark/scar.py` | Master plan 9.1, 9.3, 9.4, spec S-10 (test 7); `msgspec` documentation | msgspec | 2026-10-03 |
| `verdra/bark/seal.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/bark/veil.py` | Master plan 10.6 (header list, login-token pattern), spec S-03; the token's public warning prefix as Roblox documents it to users | Standard library (`re`, `logging`) | 2026-10-01 |
| `verdra/canopy/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/crown/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/crown/about.py` | Master plan 3.2, 7.7, message catalogue (M-ABOUT-02), spec S-01 | PySide6 | 2026-10-01 |
| `verdra/canopy/crown/dew.py` | Master plan 6.6, 7.1, specs S-01, S-03, S-04 | PySide6 | 2026-10-01 |
| `verdra/canopy/crown/header.py` | Master plan 7.1, message catalogue (M-STATUS-03), spec S-01 | PySide6 | 2026-10-01 |
| `verdra/canopy/crown/seedling.py` | Master plan 7.9, message catalogue (M-ONB-01 to 04), spec S-01 | PySide6 | 2026-10-01 |
| `verdra/canopy/crown/shortcuts.py` | Master plan 7.1, spec S-01 | PySide6 | 2026-10-01 |
| `verdra/canopy/crown/sidebar.py` | Master plan 6.8, 7.1, spec S-01 | PySide6 | 2026-10-01 |
| `verdra/canopy/crown/splash.py` | Master plan 4.5, 6.6, spec S-01 | PySide6 (QtSvg) | 2026-10-01 |
| `verdra/canopy/crown/theme.py` | Master plan 5.6, 6.1 to 6.8, spec S-01 | PySide6 (QtCore, QtGui, QtSvg, QtWidgets) | 2026-10-01 |
| `verdra/canopy/crown/tray.py` | Master plan 4.6, 7.10, message catalogue (M-STATUS-02), spec S-01 | PySide6 | 2026-10-01 |
| `verdra/canopy/crown/window.py` | Master plan 7.1, spec S-01 | PySide6 | 2026-10-01 |
| `verdra/canopy/glade/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/glade/audio.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/glade/font.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/glade/image.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/glade/mesh.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/glade/model.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/glade/motion.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/leaves/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/leaves/badge.py` | Master plan 5.5, 7.1, message catalogue (M-RISK-02) | PySide6 | 2026-10-01 |
| `verdra/canopy/leaves/dialogs.py` | Master plan 4.3, 7.8, message catalogue (M-RISK-01) | PySide6 | 2026-10-01 |
| `verdra/canopy/leaves/drawer.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/leaves/empty.py` | Master plan 7.2, 7.3, message catalogue (M-SOON-01) | PySide6 | 2026-10-01 |
| `verdra/canopy/leaves/fields.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/leaves/notice.py` | Master plan 5.4, message catalogue (kind Notice) | PySide6 | 2026-10-01 |
| `verdra/canopy/leaves/progress.py` | Design system brand book ("UI language": progress), Master plan 5.4, 6.6 | PySide6 | 2026-10-01 |
| `verdra/canopy/leaves/switch.py` | Brand system UI language (switches), Master plan 6.6 | PySide6 | 2026-10-01 |
| `verdra/canopy/leaves/tables.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/screens/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/screens/garden.py` | Message catalogue (M-SOON-01); placeholder | PySide6 | 2026-10-01 |
| `verdra/canopy/screens/grafts/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/screens/grafts/editor.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/screens/grafts/imports.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/screens/grafts/presets.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/screens/grafts/preview.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/canopy/screens/grafts/screen.py` | Master plan 7.2 (empty state), message catalogue (M-EMPTY-01) | PySide6 | 2026-10-01 |
| `verdra/canopy/screens/hive.py` | Message catalogue (M-SOON-01); placeholder | PySide6 | 2026-10-01 |
| `verdra/canopy/screens/rings.py` | Master plan 7.7, 13.9, spec S-03, message catalogue (M-LOG-01) | PySide6 | 2026-10-01 |
| `verdra/canopy/screens/seedbank.py` | Master plan 7.3 (empty state), message catalogue (M-EMPTY-02) | PySide6 | 2026-10-01 |
| `verdra/canopy/screens/settings.py` | Master plan 7.7, Reference R2 (labels), spec S-02 | PySide6 | 2026-10-01 |
| `verdra/canopy/screens/streams.py` | Message catalogue (M-SOON-01); placeholder | PySide6 | 2026-10-01 |
| `verdra/roots/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/burrow.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/gardener.py` | Master plan 9.4, 10.3, 16.4, spec S-10 (rules 2 to 4, tests 2, 3, 4 and 7); Qt `QFileSystemWatcher` and `QTimer` documentation; Python `os.chmod`/`stat` and `hashlib` documentation | cryptography, PySide6 | 2026-10-03 |
| `verdra/roots/hyphae.py` | Master plan 8.3, 10.2, 10.3, 10.6, spec S-11 (rules 1, 3, 4 and 5, tests 3, 4 and 7); RFC 9110 (semantics, 100-continue), RFC 9112 (HTTP/1.1 framing, chunked coding); h11 documentation; Python `ssl`, `asyncio` streams (`start_tls`), `zlib` and `compression.zstd` documentation | h11, cryptography, PySide6 (translations) | 2026-10-03 |
| `verdra/roots/mycelium.py` | Master plan 8.3, 10.1, 10.2, spec S-11 (rules 1 and 2, tests 2, 6, 7; hand-off to interception); RFC 9110 9.3.6 (CONNECT); Python `asyncio` streams documentation | PySide6 (translations) | 2026-10-03 |
| `verdra/roots/owl.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/rules.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/symbionts/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/symbionts/climate.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/symbionts/forager.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/symbionts/grafter.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/symbionts/mimicry.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/symbionts/streams.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/symbionts/trailguard.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/roots/taproot.py` | Master plan 10.4, spec S-11 (tests 3 and 8), Reference R2 (`routing.upstream.*`); RFC 1928 (SOCKS5), RFC 1929 (SOCKS username/password), RFC 9110 9.3.6 (CONNECT) and 11.7.2 (Proxy-Authorization), RFC 7617 (Basic); `truststore`, Python `ssl` and `urllib.request.getproxies` documentation | truststore | 2026-10-03 |
| `verdra/seedbank/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/seedbank/harvest.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/seedbank/kinds.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/seedbank/sieve.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/seedbank/vault.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/atomic.py` | Master plan 9.7, decision record 0005, spec S-02; POSIX `rename`/`fsync` and Python `os.replace` documentation | Standard library | 2026-10-01 |
| `verdra/soil/humus.py` | Master plan 6.6 (reduced motion per OS) and 16.2 (macOS deferred; the Platform interface); Reference R1; Python `typing.Protocol` documentation | Standard library (`subprocess`) | 2026-10-03 |
| `verdra/soil/lichen.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/meadow/` | Reference R1; Master plan 6.6; Windows `SystemParametersInfo` (SPI_GETCLIENTAREAANIMATION) documentation; Win32 named pipe documentation (CreateNamedPipeW, ConnectNamedPipe, GetNamedPipeClientProcessId, WriteFile, FlushFileBuffers, DisconnectNamedPipe) | Standard library (`ctypes`) | 2026-10-03 |
| `verdra/soil/meadow/autostart.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/meadow/files.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/meadow/hotkeys.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/meadow/instances.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/meadow/keeper.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/meadow/keeper_client.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/meadow/launcher.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/meadow/watchdog.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/orchard/` | Reference R1; Master plan 16.2 (macOS deferred until after 1.0); decision record 0014 | — | 2026-10-03 |
| `verdra/soil/orchard/autostart.py` | Reference R1 (job line; returns "unsupported", decision record 0014) | — | 2026-10-03 |
| `verdra/soil/orchard/files.py` | Reference R1 (job line; returns "unsupported", decision record 0014) | — | 2026-10-03 |
| `verdra/soil/orchard/hotkeys.py` | Reference R1 (job line; returns "unsupported", decision record 0014) | — | 2026-10-03 |
| `verdra/soil/orchard/instances.py` | Reference R1 (job line; returns "unsupported", decision record 0014) | — | 2026-10-03 |
| `verdra/soil/orchard/keeper.py` | Reference R1 (job line; returns "unsupported", decision record 0014) | — | 2026-10-03 |
| `verdra/soil/orchard/keeper_client.py` | Reference R1 (job line; returns "unsupported", decision record 0014) | — | 2026-10-03 |
| `verdra/soil/orchard/launcher.py` | Reference R1 (job line; returns "unsupported", decision record 0014) | — | 2026-10-03 |
| `verdra/soil/orchard/watchdog.py` | Reference R1 (job line; returns "unsupported", decision record 0014) | — | 2026-10-03 |
| `verdra/soil/terrain.py` | Reference R3 (system identifiers), Master plan 9.1 (folders) | platformdirs | 2026-10-01 |
| `verdra/soil/tundra/` | Reference R1; Master plan 6.6; GNOME `org.gnome.desktop.interface enable-animations` documentation; Linux memfd_create(2) and proc(5) (/proc/self/fd) manual pages | Standard library | 2026-10-03 |
| `verdra/soil/tundra/autostart.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/tundra/files.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/tundra/hotkeys.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/tundra/instances.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/tundra/keeper.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/tundra/keeper_client.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/tundra/launcher.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/soil/tundra/watchdog.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/strata/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/strata/amber/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/strata/clay/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/strata/granite/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/strata/ochre/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/strata/sway/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/almanac/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/almanac/migrate.py` | Master plan 9.7, spec S-02 | Standard library | 2026-10-01 |
| `verdra/trunk/almanac/schema.py` | Reference R2, spec S-02 | msgspec | 2026-10-01 |
| `verdra/trunk/almanac/store.py` | Spec S-02, Master plan 9.2 and 9.7, message catalogue R5 (M-SET-01 to 03) | msgspec, PySide6 (QtCore) | 2026-10-01 |
| `verdra/trunk/branches/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/climate.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/cuttings.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/fallow.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/grafts.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/hive.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/mimicry.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/pollen.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/seedpods.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/sprout.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/trails.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/branches/transplant.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/budding.py` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/rings.py` | Spec S-03, Master plan 13.9 (support bundle), Reference R2 (`advanced.detailed_logging`) | Standard library (`logging.handlers`, `zipfile`), PySide6 (QtCore) | 2026-10-01 |
| `verdra/trunk/sapwood/` | Reference R1 (job line only; no code yet) | — | 2026-10-01 |
| `verdra/trunk/sapwood/cli.py` | Reference R1, spec S-01 | Standard library (`argparse`) | 2026-10-01 |
| `verdra/trunk/sapwood/shutdown.py` | Master plan 8.4, specs S-01, S-04 | Standard library | 2026-10-01 |
| `verdra/trunk/sapwood/single.py` | Reference R3 (channel name), spec S-01 | PySide6 (QtNetwork) | 2026-10-01 |
| `verdra/trunk/sapwood/startup.py` | Master plan 8.4, 12.4, spec S-01 | PySide6 | 2026-10-01 |
| `verdra/trunk/tendrils.py` | Spec S-04, Master plan 8.3 (one worker pool) and 12.4 (idle CPU) | Standard library (`threading`, `queue`), PySide6 (QtCore) | 2026-10-01 |

## Tools and build files

Not part of the app, but written under the same clean-room rules (review finding M15).

| File | Built from | Libraries | Date |
| --- | --- | --- | --- |
| `tools/check_build.py` | Master plan 8.1, 12.3, 12.4, 13.4, 13.6, risk R-07, decision records 0002 and 0010; PyInstaller one-folder layout as documented | Standard library | 2026-10-02 |
| `tools/check_colors.py` | Master plan 5.6, 12.3 | Standard library | 2026-10-01 |
| `tools/check_docs.py` | Master plan 3.1, 12.3, 12.6, Reference R1 | Standard library (`ast`) | 2026-10-01 |
| `tools/check_spelling.py` | Master plan 4.3, 16.2, decision record 0010; Qt Linguist `.ts` format documentation | Standard library | 2026-10-02 |
| `tools/check_strings.py` | Master plan 4.3, 12.3, Reference R5; Qt translation documentation | Standard library (`ast`) | 2026-10-01 |
| `tools/coverage_floors.py` | Master plan 12.1 | coverage.py JSON report format | 2026-10-01 |
| `tools/i18n.py` | Master plan 12.3, Reference R5; `pyside6-lupdate` documentation | PySide6 tools | 2026-10-01 |
| `tools/icons.py` | Master plan 4.4, 4.6, design system logo rules; SVG, ICO and ICNS file format documentation | fontTools, uharfbuzz, PySide6 (QtSvg, QtGui) | 2026-10-01 |
| `tools/licenses.py` | Master plan 8.1, 12.3, Reference R4, decision record 0010 | pip-licenses, packaging | 2026-10-01 |
| `packaging/verdra.spec` | Master plan 13.6, Reference R3, decision records 0002 and 0010; PyInstaller spec-file documentation | PyInstaller | 2026-10-02 |
