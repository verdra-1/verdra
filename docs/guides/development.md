# Developing Verdra

A plain, end-to-end guide for working on Verdra's non-engine parts: get the code, set it up, run
it, run the checks, and understand how it is put together. It gathers what is spread across
[CONTRIBUTING.md](../../CONTRIBUTING.md), [architecture.md](../architecture.md) and
[run-from-source.md](run-from-source.md); read those for the detail.

Verdra targets **Windows only** for now (decision record 0018). A session's own machine may be
Linux — the checks still run there, with the Windows-only tests skipped — but only Windows CI
counts, and the app is run and tested for real on Windows.

## How Verdra is put together (the non-engine parts)

Verdra is one desktop app, divided into seven nature-named areas. Imports flow one way, so a
change in one layer can't reach back into the ones above it:

```
canopy → trunk → {roots, seedbank, strata, bark} → soil
```

The parts you'll meet most outside the replacement engine:

- **`canopy`** — everything the user sees: the window and shell (`canopy/crown`), the reusable
  widgets built only from tokens (`canopy/leaves`, e.g. the dialogs, the status leaf), and one
  package per screen (`canopy/screens`). It talks only to `trunk`, never to the OS or the network.
- **`trunk`** — the app's services and state: settings, the Activity log, the profile store, and
  the startup sequence. The screens read and drive the app through it.
- **`soil`** — the platform adapters and shared foundations. Every OS-specific path goes through
  the `Platform` interface in `soil/humus.py`; nothing above `soil` checks the operating system.
  The Windows adapter lives in `soil/tundra`; the paused Linux and macOS adapters (`soil/orchard`,
  `soil/meadow`) return "unsupported on this system".
- **`strata`** — the file-format codecs (pictures, meshes), used when a replacement is prepared.
- **`bark`** and **`seedbank`** — trust/protection and the asset store.

The **design system** lives in `src/verdra/assets/brand/` (`tokens.json` is the only place colour
values exist) and is generated into SVGs by `tools/icons.py`. Screens are specified in
`docs/specs/`, decisions recorded in `docs/decisions/`, and the design pass in `docs/design/`.
See [architecture.md](../architecture.md) for the full module tree and
[glossary.md](../glossary.md) for the nature names.

## Get the code

Verdra is developed only in sessions connected to `verdra-1/verdra`, with no copy of any other
asset-replacement tool present (the clean-room rule, decision record 0003).

```sh
git clone https://github.com/verdra-1/verdra.git
cd verdra
```

## Set up

You need **Python 3.14** and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
uv run pre-commit install
```

## Run it from source

```sh
uv run python -m verdra
```

On a headless machine, render off-screen with `QT_QPA_PLATFORM=offscreen`. On the maintainer's
Windows PC, the real-machine tests run Verdra from source through `tools/run-latest.ps1`; see
[run-from-source.md](run-from-source.md) for that checklist. On Linux the app starts but does not
route (Roblox support is Windows-only while Linux is paused).

## Run the checks

One command runs every gate, each with the exact dependency groups and Python version its CI job
uses:

```sh
uv run python tools/gates.py
```

The individual gates (also listed in CLAUDE.md) are:

```sh
uv run ruff format --check . && uv run ruff check .   # format and lint
uv run pyright                                         # types
uv run lint-imports                                    # one-way layering
uv run pytest                                          # tests (QT_QPA_PLATFORM=offscreen if headless)
uv run python tools/licenses.py                        # licence allowlist and Qt modules
uv run python tools/check_colors.py                    # no colour literals outside tokens.json
uv run python tools/check_strings.py                   # UI strings wrapped for translation
uv run python tools/check_spelling.py                  # US spelling in user-facing text
uv run python tools/check_docs.py                      # module tree, provenance, spec tests
```

## Build the app

The Windows build and its launch check (needed before any change to startup, the shell, the
splash, the tray, packaging or the build check):

```sh
uv run python tools/gates.py --jobs build              # PyInstaller build, Qt-module scan, launch
```

## How CI works

`.github/workflows/ci.yml` is the full list of gates. Every run is a full run on
**`windows-latest`** only (decision records 0012, 0018); the required check **"All gates green"**
comes from runs against `main`. There is one completed run per pull-request head. Nothing is
published before 1.0 (decision record 0026): no version tag and no GitHub release.

## Opening a change

Most changes start as a spec in `docs/specs/`. Branch with a `spec/`, `fix/`, `chore/` or `docs/`
prefix, keep each pull request small, sign off every commit (DCO), add a `CHANGELOG.md` entry, and
follow the [definition of done](../../CONTRIBUTING.md#definition-of-done).
