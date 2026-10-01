# 0007. Wheel check for Python 3.14 (risk R-08)

- **Status:** Accepted
- **Date:** 2026-10-01
- **Plan sections:** 8.1, 11.1 (ARM64), 15 (R-08), Reference R4

## Context

Plan R-08: a required wheel may be missing for Python 3.14 on one of the target platforms. At M0
we checked every runtime dependency on PyPI for wheels for CPython 3.14 on Windows x64 and ARM64,
macOS arm64 and x86-64, and Linux x86-64.

## Findings

| Package | Missing | Since |
| --- | --- | --- |
| cryptography | macOS x86-64 | 49.0.0 (48.0.1 is the last release with an Intel macOS wheel) |
| cryptography | Windows ARM64 | 46.0.4 |
| DracoPy | Windows ARM64 | every release |

Every other runtime dependency has wheels for all five targets (or is pure Python).

## Decision

- `pyproject.toml` requires `cryptography>=45,<49` on Intel macOS only, and `cryptography>=45`
  elsewhere. uv locks 48.0.1 for Intel macOS and the current release everywhere else.
- `[tool.uv] required-environments` lists Windows x64, macOS arm64, macOS x86-64 and Linux x86-64,
  so `uv lock` fails if any of them loses a wheel. This automates the R-08 check.
- Windows ARM64 runs the x64 build under emulation (plan 11.1). We revisit when cryptography and
  DracoPy publish ARM64 wheels.

## Consequences

- Intel macOS lags behind on cryptography updates. pip-audit runs in CI and nightly; if a
  vulnerability lands in the 48 series, we either build cryptography from source for the Intel
  release or drop the Intel build early, with a new decision record (plan 16.4 already expects the
  Intel build to end when GitHub's Intel runners do).
- Dependabot can't move cryptography past 48 on Intel macOS; that's intended.
