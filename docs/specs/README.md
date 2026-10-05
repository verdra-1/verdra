# Specs

Behaviour specs for Verdra, copied from the Feature specs tab of the Master Build Plan at the
start of each milestone, refined, and merged **before** any code for them (plan 3.1). They describe
behaviour only and contain no code and no wording from any other program.

Each spec has: Purpose, Behaviour, Rules, Messages (IDs from the message catalogue, Reference R5),
Risk badge (plan 5.5), numbered Acceptance tests (automatable unless marked "(manual)") and Lives
in (main modules).

**Status** moves Draft → Agreed (spec merged) → Built (code merged) → Verified (milestone gate
passed). Once a spec is Built, CI requires a test marked `@pytest.mark.spec("S-xx", n)` for every
automatable acceptance test `n` (`tools/check_docs.py`).

| Spec | Title | Milestone | Status |
| --- | --- | --- | --- |
| [S-01](S-01-app-shell.md) | App shell | M0 | Built |
| [S-02](S-02-settings-store.md) | Settings store | M0 | Built |
| [S-03](S-03-activity-log.md) | Activity log | M0 | Built |
| [S-04](S-04-background-jobs.md) | Background jobs | M0 | Built |
| [S-10](S-10-local-certificate-authority.md) | Local certificate authority | M1 | Built |
| [S-11](S-11-proxy-core.md) | Proxy core | M1 | Built |
| [S-12](S-12-per-app-routing-and-launching.md) | Per-app routing and launching | M1 | Built |
| [S-14](S-14-routing-status.md) | Routing status | M1 | Built |
| [S-15](S-15-coexistence.md) | Coexistence (per-app part; Hosts-file part M6) | M1 | Built |
| [S-16](S-16-reset-everything.md) | Reset everything | M1 | Built |
| [S-20](S-20-replacement-profiles.md) | Replacement profiles | M2 | Agreed |
| [S-21](S-21-replacement-engine.md) | Replacement engine | M2 | Agreed |
| [S-22](S-22-replacement-editor.md) | Replacement editor | M2 | Agreed |
| [S-23](S-23-preview-changes.md) | Preview changes | M2 | Agreed |
| [S-24](S-24-apply-now.md) | Apply now | M2 | Agreed |

Windows is the only platform (decision record 0018). Linux is paused and macOS is deferred until
after 1.0 (decision record 0014): their parts of the specs stay as reference only, and nothing
Linux- or macOS-specific is built or tested.
