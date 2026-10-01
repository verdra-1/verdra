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
| `verdra/__main__.py` | Reference R1 | Standard library | 2026-10-01 |
