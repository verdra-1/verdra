# 0030. Option A approved and resumed

- **Status:** Accepted; supersedes the pause in 0028
- **Date:** 2026-10-23
- **Plan sections:** 10.1 to 10.3, 14 (M2 exit gate), 16.2; the plan's change log, entries of
  23 October 2026

## Context

Decision record 0028 chose option A as the direction: Verdra writes the user's replacements into
the saved-asset store the Roblox Player reads before it downloads. The store-swap test of
23 October 2026 showed A is viable. The same day 0028 paused A until the owner's legal review of
the terms of service question. Decision record 0029 records that review's favorable result.

## Decision

The owner approves building option A. 0028's pause is lifted, and the items 0028 lists as "Not
built yet" are actionable, in 0028's order.

The plan's change log (23 October 2026) records the conditions:

- stay inside the benign envelope: cosmetic, local to the user's own machine and files,
  reversible (Reset everything), writing only with Roblox closed, intercepting no traffic and
  presenting no certificate;
- never touch authentication, payments, moderation, anti-cheat or any security surface; never
  inject into the Player process or patch the client binary; pirate or redistribute nothing;
- no release before 1.0, and a proper legal review before 1.0;
- revisit if Roblox's terms or posture change materially.

0028 stays as written, its status pointing here.

## Consequences

- The work 0028 scopes proceeds, each step through its own pull request:
  - the two tool fixes (the layout guard for `sqlite_stat1`, the `store_swap` launch path);
  - the read-only key-formula and on-disk-format groundwork;
  - the saved-asset writer and the S-10 / S-11 / S-24 and plan 10.x changes.
- The key-formula and format groundwork needs a short read-only capture session on the owner's
  PC, because the build sandbox can't reach roblox.com.
- M2 (0.1.0) completes when a real-machine test shows a texture replacement, then a mesh
  replacement, written this way.
- The user notice of 0029 (spec S-29) is part of the same work.
