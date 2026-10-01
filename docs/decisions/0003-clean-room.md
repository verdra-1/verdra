# 0003. Clean-room development

- **Status:** Accepted
- **Date:** 2026-10-01
- **Plan sections:** 3.1, 15 (R-06)

## Context

Earlier tools for local asset replacement exist, and Verdra offers similar features. Verdra must
be an independent work: the idea of local asset replacement and the feature list are free to
use, but another program's code and other creative expression are not.

## Decision

Verdra is written from scratch under these controls:

1. Every feature's spec is written and merged in `docs/specs/` before its code.
2. Building happens only in sessions connected to verdra-1/verdra, with no copy of the old
   archive present.
3. `docs/provenance.md` records, per module, what it was built from (spec IDs, public documents,
   libraries). CI fails when a module has no entry.
4. Before every release, the maintainer runs the similarity check on their own machine:
   copydetect over `src/` against the archive (threshold 0.15 token overlap per file pair) and a
   scan for the old tool's distinctive strings. Every hit is reviewed and rewritten.
5. The report from step 4 is stored privately with the release.

Allowed inputs: the specs, Roblox's observable behaviour captured with Verdra's own tools, public
documentation (rbx-dom binary format, FileMesh, KTX 2.0, Roblox creator docs, OS vendor docs),
allowlisted libraries, our own plans and brand system, and sample profile files exported by users
for the import feature. Forbidden inputs: any source file, comment, UI text, message, test,
implementation-specific name or bundled file of the old tool, and a one-to-one copy of its window
layout.

## Consequences

- `tools/similarity.py` takes the archive path as an argument; the archive never enters the
  repository (`/archive/` is ignored by Git).
- Specs describe behaviour only and contain no wording from any other program.
- Contributors agree to the clean-room rule in CONTRIBUTING.md.
