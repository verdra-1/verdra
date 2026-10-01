# 0006. Plain words for names on disk

- **Status:** Accepted
- **Date:** 2026-10-01
- **Plan sections:** 8.2, 9, Reference R6

## Context

The code uses a nature vocabulary (canopy, trunk, roots, seedbank, grafts, almanac…) that keeps
modules distinct and memorable. People see folder and file names when they share profiles,
attach support bundles or clean up their disk, and nature names there would be puzzling.

## Decision

Folder and file names on disk, setting keys, JSON format names and everything else people may
see use plain words: `Library`, `Logs`, `profiles/`, `settings.json`, `changes.json`,
`verdra.profile`. Nature names stay in the code. The glossary (`docs/glossary.md`) maps each code
name to the word shown to users, and the interface uses the plain word except in brand moments
(splash, empty states).

## Consequences

- A code module and the file it writes often have different names (`trunk/almanac` writes
  `settings.json`; `bark/scar` writes `changes.json`). The glossary is the bridge.
- Reviews check new disk names, setting keys and UI text against the glossary.
