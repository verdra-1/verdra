# 0018. Windows only: Linux paused

- **Status:** Accepted
- **Date:** 2026-10-05
- **Plan sections:** 2, 11.3, 13.5, 13.6, 16.2 ("Windows only, owner name, first swap test (5
  October 2026)"), Reference R1, R3; amends 0012 and 0014

## Context

The maintainer decided on 5 October 2026 (plan 16.2) that Windows is the only platform until
further notice and that Linux (Sober) is paused like macOS. Linux had never been tested on a real
machine: its facts came from a CI runner, and routing Sober stayed blocked (M-LAUNCH-04) because
where Sober reads its certificates (L-02) was never confirmed. Meanwhile every pull request paid
for a second test and build job on `ubuntu-24.04`, and the first real texture-swap test, on
Windows, is where M2 now stands or falls.

## Decision

- **Platform:** Windows only. No Linux code beyond the "unsupported on this system" adapter, no
  Linux CI jobs, no Linux packaging, and no text (README, docs, specs, About, installer,
  CLAUDE.md, the plan's current sections) may say Verdra runs on Linux or macOS; they may be
  mentioned only as "paused, planned later" (or "deferred" for macOS, decision record 0014).
- **Code:** `soil/tundra/` becomes the same kind of adapter as `soil/orchard/`: `PLATFORM.support()`
  and every module's `support()` return `Unsupported(system="linux", reason="paused")` (a new
  reason), and every job is refused. Linux-only paths outside `soil/` are removed: the CA key's
  Linux fallback file in `bark/husk` (with M-CA-03 and the platform's `key_file_fallback`), the
  Sober refusal M-LAUNCH-04 in `trunk/branches/sprout`, the Flatpak scope and "package" discovery
  in `soil/humus`, and the Linux desktop-file name at startup. The Linux and Sober identifiers in
  `soil/terrain` stay as reference (Reference R3), like the macOS ones.
- **CI:** every job of `ci.yml`, `nightly.yml`, `release.yml` and `platform-facts.yml` runs on
  `windows-latest`; the Linux test, build, fuzz, repeat and newest-Python jobs, the Sober facts
  job and `tools/platforms/facts-linux.sh` are removed. Every gate stays: the static gates, the
  secrets scan (gitleaks' Windows archive, checksum from its release), the combined and
  changed-lines coverage floors and the build check all run on Windows. `tests/test_workflows.py`
  fails if any workflow names a non-Windows runner.
- **Texts:** `tests/test_platform_claims.py` fails if user-facing text (README, PRIVACY, SECURITY,
  CONTRIBUTING, CODE_OF_CONDUCT, CLAUDE.md, the CHANGELOG's Unreleased section, guides, specs,
  platform records, issue and pull request templates, and the message catalogue) names Linux,
  macOS, Sober or Ubuntu without saying it is paused, deferred, planned later or not supported.
- **Development machines:** the lock still resolves for Linux, so a contributor or an automated
  session on Linux can run the gates. There, the Windows-only tests skip with "Linux paused (plan
  16.2)", the coverage floor leaves `soil/meadow` out, and a test-only plugin
  (`tests/support/dev_machine.py`) lets the paused platform load test certificates from a private
  temporary folder so the proxy's own logic stays testable. None of this ships, and only Windows
  CI counts as evidence.

## Consequences

- One CI platform: each pull request runs one test job and one build job, and every result is
  about the system Verdra ships on.
- Historical records (decision records 0002 to 0017, the M0 and M1 documents) keep what they said
  at the time, with a current-state note at the top; `docs/platforms/linux.md` and the Linux
  steps in `docs/platforms/protocol.md` are kept as reference, so Linux can return without
  starting over.
- The nightly benchmark's baseline was measured on Linux; it is measured again on Windows and
  committed after this change.
- Lifting the pause needs a new decision record, a Linux machine for the real-machine tests, and
  L-02 confirmed before any routing code depends on it.
