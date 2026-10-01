# 0008. Values settled where the plan contradicted itself at M0

- **Status:** Accepted
- **Date:** 2026-10-01
- **Plan sections:** 6.2, 6.3, 7.7, S-03, S-04, Reference R1, R2, 16.2

## Context

While writing specs S-01 to S-04, we found five places where two parts of the plan gave
different values. Building either value would have silently broken the other part, so we asked
the maintainer. The plan has since been updated to match (Master plan 16.2, "M0 decisions";
Reference R1 and R2).

## Decision

| Topic | Disagreement | Settled value |
| --- | --- | --- |
| Table row height | 6.3 said 36 px (compact 28 px); R2 `appearance.density` said 40 px (compact 32 px) | 36 px, compact 28 px (6.3) |
| Log rotation | S-03 said 5 files × 2 MB; the R1 line for `trunk/rings` said 5 × 5 MB | 5 files × 2 MB (S-03) |
| Background workers | S-04 said 2 to 8; R2 `advanced.worker_threads` said 1 to 16 | 2 to 8, default 4 (S-04) |
| Text size | 6.2 offered 90, 100, 115 and 130 %; R2 `appearance.text_scale` said 90 to 130 in steps of 10 | 90, 100, 115 and 130 % (6.2) |
| About button | 7.7 said "Licence" | "License": the UI uses US spelling (4.3) |

## Consequences

- `trunk/almanac/schema.py` accepts exactly these ranges and values; anything else falls back
  to the default (spec S-02). The Settings screen offers the same ranges.
- The density tokens (`row-height`, `row-height-compact`) carry 36 and 28 px.
- Files and identifiers keep British spelling where the plan uses it (`LICENSE` is the file
  name; code may say "license"); only text shown in the app follows US spelling.
