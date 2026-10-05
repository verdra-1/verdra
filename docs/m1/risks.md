# M1 risks

> **Current state (5 October 2026):** Windows is the only platform; Linux is paused, planned
> later, and macOS is deferred ([decision record 0018](../decisions/0018-windows-only.md)). What this document says about Linux
> describes the time it was written.

The risks from plan section 15 that M1 touches, and what M1 does about each. Reviewed again at
the M1 exit gate (plan 15: "Reviewed at every milestone gate").

| Risk | Why M1 touches it | What M1 does | Evidence at the gate |
|---|---|---|---|
| R-01 Roblox changes an endpoint, response shape or file format | The proxy and launcher depend on Roblox's hosts, paths and behaviour | Platform facts recorded before use (protocol); passthrough is byte-exact and doesn't parse what it doesn't need; the status popover names the failing part (S-14) | Platform records dated; S-11 test 1; S-14 test 1 |
| R-03 Trust-file edit breaks the signed macOS app | **Inactive** (plan 16.2, decision record 0014): macOS is deferred until after 1.0 | Nothing at M1; no macOS trust-file code. The R-03 procedure stays in `docs/platforms/macos.md` as reference and runs first when macOS returns | None |
| R-04 Sober changes paths, trust handling or launch options | S-10 and S-12 on Linux | Facts L-01 to L-05 recorded with the Sober version; Sober version logged at launch so a change is visible in support bundles | `docs/platforms/linux.md` |
| R-05 Microsoft Store Roblox can't receive proxy settings | S-12 detection | Detected (W-04) and explained with M-LAUNCH-02; Hosts-file routing offered (built at M6) | S-12 test 7; W-04 record |
| R-07 A GPL-only Qt module or dependency slips in | New M1 dependencies (`cryptography` with no version cap since decision record 0014, `h11`, `truststore`, `keyring`, `python-socks` or similar, `watchdog` if used) | Each new dependency through the licence gate (all groups) before it's added; build scan unchanged | CI licence report on each M1 pull request |
| R-09 Antivirus flags Verdra | M1 is the first build with a proxy, a CA and trust-file edits | Nothing to do before M8 except: no UPX (already), plain readable code, no obfuscation. Noted so M1 test builds that get flagged are recorded rather than worked around | Any detection recorded in an issue |
| R-10 No secret store on a Linux desktop | S-10 stores the CA key in the secret store from M1 | Plan 16.2: the CA-key part moves to M1, the accounts part stays at M5. Built and tested at M1: with no Secret Service, exactly one key file, mode 0600, owned by the user, M-CA-03 shown, deleted by Reset everything (S-10 test 5) | S-10 test 5 on a runner without a Secret Service |
| R-17 A Roblox client rejects ECDSA certificates | S-10 leaves | S-10 test 8 on both clients (Windows Roblox and Sober) with `--diagnose-interception`, whose Activity lines name the leaf key type; RSA 3072 switch decided and recorded at M1 if any client rejects ECDSA | Platform records; decision record if RSA is needed | **Windows: closed 2026-10-04** (Stage 2: the Player 0.741 accepted the ECDSA P-256 leaf over TLS 1.3 on all 133 connections; no RSA fallback; plan 16.2). Sober: open until Linux stage 2 |
| R-18 The Python proxy is too slow | S-11 | Latency benchmark nightly from the first proxy pull request; profiling before any optimisation; no compiled extension unless 12.4 is missed | Nightly benchmark history |
| R-12 One-person project: scope creep | M1 is the largest milestone so far | Only the M1 specs (S-10, S-11, S-12, S-14, the per-app part of S-15, S-16); questions raised, not worked around | Spec list |

## Settled in plan 16.2 (M0 review round 2)

1. **R-10 timing:** the CA-key part is M1, the accounts part M5.
2. **Coexistence at M1:** S-15's per-app part is an M1 spec; its Hosts-file part stays at M6.
3. **Interception at M1:** `--diagnose-interception`, from source only, makes S-10 test 8 and
   protocol stage 2 possible on real clients.
4. **Linux key file:** S-10 test 5 allows the documented fallback.
5. **W-08:** the single-instance object name is confirmed at M5, with multi-instance.

## Settled in plan 16.2 (M0 review round 3)

1. **S-15 per-app signs (F17):** a running Roblox with a foreign proxy, and Roblox hostnames in
   the hosts file without Verdra's marker. A taken port 49443 is S-11's fallback (M-PROXY-03),
   not a sign; port 443 on loopback is a Hosts-file sign (M6).
2. **M-SHELL-01 (F12):** an OS tray notification, also written to Activity.
3. **Activity lines (F13):** every line written for the user has a message ID.

## Settled in plan 16.2 (macOS deferred until after 1.0)

1. **Platforms:** Windows and Linux with Sober; the real-machine checks run on the maintainer's
   Windows PC and in an Ubuntu 24.04 virtual machine on it.
2. **R-03:** inactive; the macOS trust-file test doesn't run at M1 (decision record 0014).

## Still open

Nothing.
