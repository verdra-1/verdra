# Decision records

One short record per architecture decision (Master Build Plan 13.3): context, decision,
consequences. Records are numbered and never renumbered. A decision that changes later gets a
new record that supersedes the old one; the old record stays, with its status updated.

| No. | Decision | Status |
| --- | --- | --- |
| [0001](0001-licence.md) | Apache License 2.0 with a NOTICE file | Accepted |
| [0002](0002-pyside6.md) | PySide6 (Qt 6, LGPL-3.0) for the interface | Accepted |
| [0003](0003-clean-room.md) | Clean-room development | Accepted |
| [0004](0004-app-ids.md) | Application identifiers | Accepted |
| [0005](0005-data-layout.md) | Data layout on disk | Accepted |
| [0006](0006-plain-disk-names.md) | Plain words for names on disk | Accepted |
| [0007](0007-wheel-check.md) | Wheel check for Python 3.14 (risk R-08) | Accepted |
| [0008](0008-m0-contradictions.md) | Values settled where the plan contradicted itself at M0 | Accepted |
| [0009](0009-macos-15-runner.md) | macos-15 for Apple silicon in CI | Superseded by 0014 |
| [0010](0010-m0-review-decisions.md) | Decisions from the M0 review: US spelling, one copy of each legal text, Qt support libraries, licence gate over every group | Accepted |
| [0011](0011-m0-review-round-2.md) | Decisions from the second M0 review round: US spelling in code, message IDs, focus ring, widgets-only UI, layering checks | Accepted |
| [0012](0012-ci-minutes.md) | What CI runs: every gate and the full matrix on every pull request and on main; "All gates green" only for runs against main | Accepted |
| [0013](0013-m0-review-round-3.md) | Decisions from the third M0 review round: M-SHELL-01 as a tray notification, message IDs for Activity lines, S-15 per-app signs, public repository | Accepted |
| [0014](0014-macos-deferred.md) | macOS deferred until after 1.0: Windows and Linux only, orchard reports "unsupported", no macOS runners | Accepted |
| [0015](0015-diagnostic-interception-module.md) | Diagnostic interception in a source-only module, roots/litmus.py; frozen builds refuse the flag and the build check proves it's absent | Accepted |

New records copy [template.md](template.md).
