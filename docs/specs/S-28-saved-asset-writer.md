# S-28 Saved-asset writer

**Status:** Draft
**Milestone:** M2
**Risk badge:** none (to be settled when the spec is agreed)
**Plan sections:** 10.1 to 10.3, 14 (M2 exit gate), 16.2; decision records 0028 (option A, "New
spec 'saved-asset writer' (S-24's sibling)"), 0029, 0030

## Purpose

Put the user's replacements where the Roblox Player looks before it downloads: its saved-asset
store (`rbx-storage.db` and the `rbx-storage` folder in `%LOCALAPPDATA%\Roblox`), with no TLS at
all. It replaces decryption as the way replacements reach the game (decision record 0028, option
A; approved by 0030). This is S-24's sibling.

## Behaviour

Transcribed from 0028. Open points are marked; nothing here is decided beyond 0028's text.

1. Apply now (S-24) writes the user's selected replacements into the store.
2. The flow may need two steps: join once so Roblox saves the original, then Apply now writes the
   replacement. Whether that is needed depends on the answer to the key formula
   (`docs/engine/key-formula.md`). **Open.**
3. Roblox may later replace or drop an entry. Verdra then writes it again at the next Apply now,
   and says so.

## Rules

1. It writes only while no Roblox Player or Studio runs, as the move of S-24 rule 4 does today.
2. Before each write, the bytes it replaces go into Verdra's backup, and the write is in the
   ledger. Reset everything restores them (S-16).
3. It writes only a store format it recognizes (a schema check). An unknown format stops it with
   a plain message, never a guess. The store's own SQLite tables (`sqlite_stat1`) don't make a
   store unknown.
4. It checks each write by reading it back.
5. It writes only the replaced assets: the user's selected replacements, nothing else.
6. Within 0030's conditions: cosmetic, local to the user's own machine and files, reversible. It
   intercepts no traffic, presents no certificate, never injects into the Player and never
   patches the client binary.

## Messages

New message IDs are needed for the interface text (0028: "The interface text for it needs new
message IDs"). **Not yet assigned; to be added when the spec is agreed.**

## Acceptance tests

To be written when the spec is agreed, one or more per rule above. **Open.**

## Lives in

To be decided when the spec is agreed.

## Changes it brings elsewhere (from 0028, proposals)

- **Plan 10.1 to 10.3, specs S-10 and S-11:**
  - Replacements stop depending on decryption.
  - The local authority and the Player's certificate file are left alone unless a diagnostic
    needs them, so there are fewer changes to the user's system.
  - S-11's proxy stays for the diagnostics and for features that only read.
- **S-24 (Apply now):** the two-step flow above, if the key formula needs it.
- **Plan 16.2 / legal:** settled by decision record 0029.

## Depends on

- The key formula and the on-disk format, read-only groundwork not yet done
  (`docs/engine/key-formula.md`, `docs/engine/store-format.md`).
- The user notice, spec S-29 (decision record 0029).
