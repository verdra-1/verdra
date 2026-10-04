# S-23 Preview changes

**Status:** Agreed
**Milestone:** M2
**Risk badge:** Cosmetic
**Plan sections:** 7.2 (Preview changes), 14 (M2), Feature specs S-23, Reference R1
(`trunk/branches/grafts`, `canopy/screens/grafts/preview`), R5 (M-PREV-01)

## Purpose

Show exactly what will change before it changes.

## Behaviour

- "Preview changes" lists every original asset affected by the enabled profiles, grouped by
  type, with the winning replacement, the profile it comes from, and every conflicting
  replacement it overrides.
- Totals at the top: M-PREV-01 ("38 assets will change; 2 conflicts").

## Rules

1. Computed from the same rule snapshot the proxy uses (S-21), so preview and reality can't
   differ.
2. A conflict is an original (asset ID and slot) that more than one enabled replacement names;
   the count is of such originals, not of the overridden replacements.

## Messages

- M-PREV-01 "<n> assets will change; <m> conflicts." (with plural forms)

## Acceptance tests

1. The preview equals the snapshot for fixture profiles with deliberate conflicts: same winners,
   same overridden replacements, same totals.

## Lives in

`trunk/branches/grafts.py`, `canopy/screens/grafts/preview.py`.

## Refinements from the plan

- Rule 2 defines what a conflict counts, which the plan's example leaves open.
- M-PREV-01 has two counts, so it is two plural entries in the catalogue ("<n> assets will change;"
  and "<n> conflicts.", each with its own count) joined by a space; each gets its own singular and plural form.
- Each replacement carries its original's asset type into the snapshot, so the preview groups
  by the same snapshot the proxy uses.
