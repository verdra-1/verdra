# Linux platform facts

Filled in from [protocol.md](protocol.md). Until a row is `Confirmed`, no code may depend on it
(plan 16.4). States are defined in [README.md](README.md).

## Machine

| Field | Value |
|---|---|
| OS, version, build | CI runner: Ubuntu 24.04.5 LTS (no desktop session) |
| Architecture | CI runner: x86_64 |
| Sober version and commit; Flatpak runtime; desktop and session type | CI runner: Sober 1.8.0, commit a985be6b…b6a1; runtime org.gnome.Platform/x86_64/51; Flatpak 1.14.6; no desktop |
| Checked by, date | Platform facts workflow on a CI runner, 2026-10-03 (maintainer's VM: not yet) |
| Evidence folder | `evidence/linux/` |

## Facts

| ID | Plan says | Recorded value | State | Date | Evidence |
|---|---|---|---|---|---|
| L-01 | Sober is `org.vinegarhq.Sober`; launched with `flatpak run --env=…` | `org.vinegarhq.Sober` 1.8.0 from Flathub, command `sober`; permissions network, ipc, wayland, pulseaudio, fallback-x11, dri. Launch with `--env` is V0 (stage 2) | Observed, confirmed on CI runner (Sober 1.8.0) | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37162568047/job/111318887372), `evidence/linux/ci-run-37162568047.txt` |
| L-02 | Where Sober reads its CA bundle | Sober's installed files hold no `.pem`, `.crt` or CA bundle; runtime org.gnome.Platform 51. Its per-user folder only exists after a first start, so the bundle it reads can't be seen without running it: stage 2 | Unconfirmed (narrowed on CI runner) | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37162568047/job/111318887372), `evidence/linux/ci-run-37162568047.txt` |
| L-03 | Asset overlay folder under `~/.var/app/org.vinegarhq.Sober/data/sober/` | `~/.var/app/org.vinegarhq.Sober` doesn't exist before Sober's first start: needs a start (stage 2, or Sober's documentation) | Unconfirmed | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37162568047/job/111318887372), `evidence/linux/ci-run-37162568047.txt` |
| L-04 | `config.json` under `~/.var/app/org.vinegarhq.Sober/config/sober/`; FastFlags key | As L-03: created on first start, not shipped | Unconfirmed | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37162568047/job/111318887372), `evidence/linux/ci-run-37162568047.txt` |
| L-05 | `xdg-mime` default for `x-scheme-handler/roblox-player` | `org.vinegarhq.Sober.desktop` (exported to `/var/lib/flatpak/exports/share/applications/`; `MimeType=x-scheme-handler/roblox;x-scheme-handler/roblox-player;`; `Exec=… --command=sober --file-forwarding org.vinegarhq.Sober -- @@u %u @@`) on a system with no other handler | Observed, confirmed on CI runner (Sober 1.8.0) | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37162568047/job/111318887372), `evidence/linux/ci-run-37162568047.txt` |
| L-06 | A running Sober's proxy variables can be read (S-15) | | Unconfirmed | | |
| L-07 | `/etc/hosts` is readable, and from inside the Flatpak it shows the host's file (S-15) | Same SHA-256 on the host and inside Sober's sandbox (`82f94686…3a1f`) | Confirmed on CI runner (Sober 1.8.0); Verdra's own Flatpak re-checks it | 2026-10-03 | [CI run](https://github.com/verdra-1/verdra/actions/runs/37162568047/job/111318887372), `evidence/linux/ci-run-37162568047.txt` |
| V0 | Sober honors `HTTPS_PROXY` / `HTTP_PROXY` passed with `--env` | | Unconfirmed | | |

## Differences from the plan

None recorded.
