# S-03 Activity log

**Status:** Built
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
   `•••• (redacted)`. Matching is case-insensitive for header names. So do the secret parts of
   signed URLs (plan 16.2): the values of the query parameters `__token__`, `hdnts`, `hmac`,
   `sig`, `signature`, `token`, `ticket`, `Policy`, `Key-Pair-Id`, the S3 signature parameters
   and browser-tracker IDs, after `?`, `&`, `;` or `~`, also percent-encoded.
3. Everything in the support bundle passes through the same filter, including settings and the
   ledger. The bundle also replaces the user's name (the folder after `Users` or `home` in any
   path, and the account's login and home-folder names anywhere) with `<user>`, and numbers of
   seven digits or more (place, universe and user IDs) with `<id>` (plan 16.2). The log files on
   the user's own disk keep those.
4. Logging never blocks the UI thread on disk: file writes happen off the Qt thread.

## Messages

- M-LOG-01 "Support bundle saved to <path>." Action "Show in folder".
- M-LOG-02 (new, Dialog) "Export a support bundle?" / "The bundle holds Verdra's version, your
  system, the routing status, the last 2,000 log lines, your settings and the list of system
  changes. Secrets are removed. Nothing is uploaded; you decide where to send it." Checkbox
  "Include my replacement profiles"; buttons "Export…", "Cancel".
- M-LOG-03 (new, help text) "Debug records appear only while detailed logging is on."
- M-LOG-04 (new, kind Activity) "Detailed logging turned itself off after 24 hours."
- M-ERR-01 (new, Toast, kind Error) "Something went wrong. Details are in Activity." Action
  "Open Activity".
- M-ERR-02 (new, kind Activity) "Verdra ran into an error it didn't expect. Details follow."
  followed by the error's traceback.
- Every Info, Warning and Error line is written for the user and has a message ID; technical
  detail (Debug lines, exception text, values inside placeholders) has none (plan 16.2, M0 review
  round 3). `tests/test_activity_lines.py` enforces it.

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
8. Every signed-URL parameter, under every separator, spelling and percent-encoding, is redacted
   at every level; lines in the shape of the Stage 2 capture, rewritten with invented values,
   keep no secret in the file, the ring buffer or the bundle, and keep their host and path.
9. A support bundle holds no user name (Windows path with spaces, JSON-escaped path, Linux path,
   login name) and no long numeric ID; versions, ports and process IDs stay.

## Lives in

`trunk/rings.py`, `bark/veil.py`, `canopy/screens/rings.py`.

## Refinements from the plan

- **Rotation size**: 5 files × 2 MB (plan S-03; the R1 line for `trunk/rings` now matches;
  decision record 0008).
- Redaction also covers exception text and log arguments, not only the message.
- Rule 2's signed-URL parameters and rule 3's user names and IDs, with tests 8 and 9, carry out
  plan 16.2 ("Stage 2 on Windows"); the parameter names are those seen in the Stage 2 capture.
- **Unhandled errors (2026-10-05)**: an error no code handles, in a Qt slot, a timer or any
  thread, is never only printed to a console. `trunk/rings.ErrorHook` takes `sys.excepthook`
  (which PySide calls for exceptions in slots) and `threading.excepthook`. It writes M-ERR-02
  with the full traceback at Error level, anonymized as support bundles are (user names and long
  IDs replaced) besides the usual redaction, and the shell shows M-ERR-01 once per burst, with
  "Open Activity". M-ERR-01 can't name the action that failed, because the hook doesn't know it;
  refusals the user can act on (a full profile) are caught where they happen and shown in place.
  Found by the first-texture-swap test, where Save failed with a console-only traceback.
