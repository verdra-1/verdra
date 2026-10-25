# The saved-asset writer

The rules, transcribed from decision record 0028 ("New spec 'saved-asset writer' (S-24's
sibling)" and the bullets around it). The spec is [S-28](../specs/S-28-saved-asset-writer.md),
a draft. Not built.

## Rules

- It writes only while no Player or Studio runs, as the move does today.
- Before each write, the bytes it replaces go into Verdra's backup, and the write is in the
  ledger. Reset everything restores them.
- It writes only a store format it recognizes (a schema check). An unknown format stops it with
  a plain message, never a guess.
- It checks each write by reading it back.
- Roblox may later replace or drop an entry. Verdra then writes it again at the next Apply now,
  and says so.

## Around it

- **S-24 (Apply now):** the flow may need two steps: join once so Roblox saves the original,
  then Apply now writes the replacement. Whether that is needed depends on the answer to
  [the key formula](key-formula.md). The interface text for it needs new message IDs.
- **Plan 10.1 to 10.3, specs S-10 and S-11:**
  - Replacements stop depending on decryption.
  - The local authority and the Player's certificate file are left alone unless a diagnostic
    needs them, so there are fewer changes to the user's system.
  - S-11's proxy stays for the diagnostics and for features that only read.
- **Consequence, from 0028:** A depends on an undocumented store that any Roblox update can
  change. The schema check and a plain message keep that from failing silently.
