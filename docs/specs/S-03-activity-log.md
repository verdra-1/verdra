# S-03 Activity log

**Status:** Agreed
**Milestone:** M0
**Risk badge:** none
**Plan sections:** 7.7, 9.1, 10.6, 13.9, Reference R2 (`advanced.detailed_logging`)

## Purpose

One logging system for the app, readable in the Activity screen and safe to share.

## Behaviour

- Verdra uses Python's standard `logging`. Records go to:
  - a rotating file `verdra.log` in the logs folder (plan 9.1), at most 5 files of 2 MB each;
  - an in-memory ring buffer of the last 5,000 records, which backs the Activity screen.
- Levels: Debug, Info, Warning, Error. Debug records are kept only while Settings › Advanced ›
  "Detailed logging" is on; that setting turns itself off 24 hours after it was turned on (also
  across restarts).
- Every toast, dialog and notice (plan R5 kinds) is also written to Activity.
- Activity screen: list of records (time, level, message), level filter (Info, Warning, Error,
  Debug), search, "Copy" (selected records, or all visible), "Open log folder", "Export support
  bundle…".
- **Support bundle** (plan 13.9): one ZIP with the Verdra version and build, OS and architecture,
  routing mode and status, the last 2,000 log lines, settings and the change ledger (when it
  exists). Profile contents are included only when "Include my replacement profiles" is ticked.
  Nothing is uploaded; the user chooses where to save it. The toast M-LOG-01 offers "Show in
  folder".
- The keeper (M6) writes its own log; this spec doesn't cover it.

## Rules

1. The redaction filter `bark/veil` runs on every record **before** any handler sees it, so the
   file, the ring buffer, the Activity screen and the support bundle never hold a secret.
2. Redaction (plan 10.6): the values of the headers Cookie, Set-Cookie, Authorization,
   Proxy-Authorization, X-CSRF-TOKEN and rbx-authentication-ticket, and any value matching the
   Roblox login-token pattern anywhere in a message, its arguments or an exception, become
   `•••• (redacted)`. Matching is case-insensitive for header names.
3. Everything in the support bundle passes through the same filter, including settings and the
   ledger.
4. Logging never blocks the UI thread on disk: file writes happen off the Qt thread.

## Messages

- M-LOG-01 "Support bundle saved to <path>." Action "Show in folder".

## Acceptance tests

1. Every secret pattern logged at every level (in the message, in its arguments and in an
   exception) is redacted in the file, the ring buffer and the support bundle.
2. Rotation keeps at most 5 files of at most 2 MB each.
3. Activity search returns the matching records within 100 ms for 5,000 records.
4. Debug records are dropped unless "Detailed logging" is on, and the setting turns itself off
   after 24 hours.
5. The support bundle contains exactly the items in plan 13.9; profiles only when ticked.
6. Toasts, dialogs and notices appear in Activity.
7. The ring buffer holds at most 5,000 records, oldest dropped first.

## Lives in

`trunk/rings.py`, `bark/veil.py`, `canopy/screens/rings.py`.

## Refinements from the plan

- **Rotation size**: this spec (plan S-03) says 5 files × 2 MB; the R1 module tree line for
  `trunk/rings` says 5 × 5 MB. This spec keeps 5 × 2 MB; the R1 line needs the matching edit (the
  `trunk/rings.py` docstring follows this spec).
- Redaction also covers exception text and log arguments, not only the message.
