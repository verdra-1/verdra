# Linux platform facts

Filled in from [protocol.md](protocol.md). Until a row is `Confirmed`, no code may depend on it
(plan 16.4). States are defined in [README.md](README.md).

## Machine

| Field | Value |
|---|---|
| OS, version, build | |
| Architecture | |
| Sober version and commit; Flatpak runtime; desktop and session type | |
| Checked by, date | |
| Evidence folder | `evidence/linux/` |

## Facts

| ID | Plan says | Recorded value | State | Date | Evidence |
|---|---|---|---|---|---|
| L-01 | Sober is `org.vinegarhq.Sober`; launched with `flatpak run --env=…` | | Unconfirmed | | |
| L-02 | Where Sober reads its CA bundle | | Unconfirmed | | |
| L-03 | Asset overlay folder under `~/.var/app/org.vinegarhq.Sober/data/sober/` | | Unconfirmed | | |
| L-04 | `config.json` under `~/.var/app/org.vinegarhq.Sober/config/sober/`; FastFlags key | | Unconfirmed | | |
| L-05 | `xdg-mime` default for `x-scheme-handler/roblox-player` | | Unconfirmed | | |
| L-06 | A running Sober's proxy variables can be read (S-15) | | Unconfirmed | | |
| L-07 | `/etc/hosts` is readable, and from inside the Flatpak it shows the host's file (S-15) | | Unconfirmed | | |
| V0 | Sober honors `HTTPS_PROXY` / `HTTP_PROXY` passed with `--env` | | Unconfirmed | | |

## Differences from the plan

None recorded.
