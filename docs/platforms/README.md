# Platform facts and how they are verified

Plan section 11 marks some facts about Roblox and Sober "(confirm at M1)". No code may depend on
such a fact until it is recorded in `docs/platforms/<os>.md` (plan 16.4). This folder holds:

- [`protocol.md`](protocol.md): the verification protocol, the steps the maintainer runs on each
  real machine, and what to record.
- [`windows.md`](windows.md), [`linux.md`](linux.md): one record per OS, filled in from the
  protocol. Each starts as a template with every fact `Unconfirmed`.
- [`macos.md`](macos.md): deferred until after 1.0 (decision record 0014); kept as reference and
  not run.
- Stage 2 checks run Verdra from source with `--diagnose-interception` (plan 16.2, S-11),
  which intercepts only the 10.2 hosts and changes nothing it passes on.

A fact is in one of four states:

| State | Meaning | Code may use it |
|---|---|---|
| Unconfirmed | Nobody has checked it on a real machine | No |
| Observed | Seen on a real machine (file, key or folder present as described) | For reading and listing only |
| Confirmed | Observed, and its effect checked (for example Roblox really uses that trust file) | Yes |
| Differs | The real machine doesn't match the plan | No; the maintainer decides the change first |

A `Differs` result stops work on the code that needs it: it is reported to the maintainer, the
plan is updated or a decision record written, and only then is the record changed.
