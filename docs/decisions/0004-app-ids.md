# 0004. Application identifiers

- **Status:** Accepted
- **Date:** 2026-10-01
- **Plan sections:** Reference R3, 11

## Context

Verdra registers names with each operating system: bundle and app IDs, a secret-store service,
service and task names, a URL handler, file associations, Polkit actions and more. Changing any of
them after release would orphan users' system changes (Reset everything couldn't find them).
Verdra doesn't own a domain yet.

## Decision

- The reverse-DNS base is `io.github.verdra-1.verdra`, derived from the GitHub organisation.
- Where a system forbids a hyphen in that position (Flatpak and desktop-entry IDs), the hyphen
  becomes an underscore: `io.github.verdra_1.verdra`. Polkit action IDs allow `[a-z0-9.-]` and keep
  the hyphen.
- Every identifier is defined once, in `src/verdra/soil/terrain.py`. A test checks that no other
  module spells them.
- The Windows installer's Inno Setup `AppId` is fixed now and never changes:

  ```
  {8F770622-386C-4265-AF56-B019A81EA7BE}
  ```

  (In the `.iss` file the opening brace is doubled: `AppId={{8F770622-386C-4265-AF56-B019A81EA7BE}`.)

## Consequences

- If Verdra later moves to its own domain, these identifiers stay as they are.
- The full list (Reference R3) lives in `soil/terrain.py`; adding an identifier means adding it
  there and to R3.
