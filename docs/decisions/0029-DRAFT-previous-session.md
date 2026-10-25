# 0029. Writing replacements into Roblox's saved assets: the legal opinion

- **Status:** Accepted
- **Date:** 2026-10-23
- **Plan sections:** 3 (legal foundations), 10.1 to 10.3, 14 (M2 exit gate), 16.2 (autopilot:
  legal questions are the owner's)

## Context

Decision record 0028 made option A the direction: Verdra writes a replacement into the store
the Roblox Player reads before it downloads (`rbx-storage.db` and the `rbx-storage` folder),
with no TLS at all. The store-swap test of 23 October 2026 showed it is technically possible:
the Player draws whatever sits under a key and doesn't re-check it on a disk read.

On 23 October 2026 option A was paused until the owner's legal review. The question was whether
writing into the Player's local asset cache is allowed.

## The legal opinion (as the owner reported it, 23 October 2026)

The owner obtained a legal opinion covering German and EU law, and US and California law. Its
bottom line:

- **Lawful on every statutory theory examined:** building, distributing (free, open source,
  before 1.0 and at 1.0) and using Verdra with option A. The theories were copyright,
  anti-circumvention, computer misuse and trademark.
- **The certificate pinning of 21 October 2026 doesn't change the analysis.** Option A avoids
  the measure rather than circumventing it, so anti-circumvention law isn't engaged (US DMCA
  §1201; EU InfoSoc Directive Art. 6, §95a UrhG).
- **The soft spot is the user's own contract with Roblox.** Option A is probably outside the
  express words of Roblox's Terms of Service, so a user's use is a breach. Its only remedy is
  termination of the user's account. Verdra and its maker aren't parties to those Terms and are
  in breach of nothing.
- **Recommendation:** proceed.

**The caveat, kept intact:** this is not "no risk". The risk that a user's Roblox account is
suspended or terminated is real, and it falls on the user.

This record restates the opinion as reported; it isn't legal advice, and the opinion itself
isn't in the repository.

## Decision

- Option A is unpaused (the owner, 23 October 2026).
- **A new product requirement from the review:** Verdra shows the user a prominent,
  plain-language notice, in the app and in the README and docs, that using it may breach
  Roblox's Terms of Service and may lead to suspension or termination of their Roblox account,
  and that they use it at their own risk. The app shows it at first run and near where
  replacements are applied or turned on, and the user acknowledges it once (spec S-29, message
  M-TERMS-01). It gives users informed consent to the one risk the review identified.
- **The bounds the owner set:** Verdra writes only into the store on the user's own computer,
  only with every Roblox Player and Studio closed, only the user's selected replacements, and
  always reversibly (backup, ledger, Reset everything). It never patches the client binary and
  never injects into a process. It never touches Roblox's security, login or payment endpoints.
- The M8 checklist's lawyer review before the first public release (plan 3) still applies. This
  record is one of its inputs.

## Consequences

- The notice is a requirement for every build that applies replacements, not only for option A.
- Building A goes ahead step by step, each step that touches the owner's PC with its own guide.
- If Roblox's Terms or the store change, this record is amended.
