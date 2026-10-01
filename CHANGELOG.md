# Changelog

All notable changes to Verdra are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Verdra uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Repository foundations: licence, notice, README, security policy, privacy statement,
  contribution guide and code of conduct, with the project's support contact.
- Project tooling: `pyproject.toml` with dependency floors, `uv.lock`, Python 3.14 pin,
  licence allowlist with its gate (`tools/licenses.py`), colour-literal gate
  (`tools/check_colors.py`) and pre-commit hooks.
- CI on Windows, macOS (Apple silicon and Intel) and Linux with every gate from the build plan:
  format, lint, types, layering, tests, coverage floors, licences, vulnerabilities, secrets,
  colours, translatable strings, US spelling in user-facing text and code, SPDX headers and docs; the licence gate
  covers the runtime, dev and build dependency groups; every gate and all four runners on every
  pull request and on main. Nightly fuzzing, benchmarks and audit; release stub.
