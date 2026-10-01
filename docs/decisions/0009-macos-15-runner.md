# 0009. macos-15 for Apple silicon in CI

- **Status:** Accepted
- **Date:** 2026-10-01
- **Plan sections:** 13.5, 16.2

## Context

Plan 13.5 listed `macos-latest` as the Apple silicon runner. In this repository, jobs on the
`macos-latest` label stayed queued and were never assigned a runner, so no pull request could
turn green. `macos-15` is an explicit, currently supported GitHub-hosted image on Apple silicon
(arm64), and `macos-15-intel` is the Intel image the plan already uses.

## Decision

`ci.yml` and `nightly.yml` run the Apple silicon jobs on `macos-15` instead of `macos-latest`.
Plan 13.5 has been updated to match.

## Consequences

- The image no longer moves on its own when GitHub changes what `macos-latest` points to. When
  GitHub retires `macos-15`, we move to the next explicit label with a new decision record.
- The Intel job stays on `macos-15-intel` (plan 16.4 expects the Intel build to end when
  GitHub's Intel runners do).
