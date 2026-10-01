# Changelog

All notable changes to Verdra are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Verdra uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Repository foundations: licence, notice, README, security policy, privacy statement,
  contribution guide and code of conduct.
- Project tooling: `pyproject.toml` with dependency floors, `uv.lock`, Python 3.14 pin,
  licence allowlist with its gate (`tools/licences.py`), colour-literal gate
  (`tools/check_colours.py`) and pre-commit hooks.
- CI on Windows, macOS (Apple silicon and Intel) and Linux with every gate from the build plan:
  format, lint, types, layering, tests, coverage floors, licences, vulnerabilities, secrets,
  colours, translatable strings and docs. Nightly fuzzing, benchmarks and audit; release stub.
