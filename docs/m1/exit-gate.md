# M1 exit gate (Root: routing)

Each item of plan section 14 (M1) is checked here with its evidence, as of 2026-10-04.

**Result: M1 is done on Windows.** Linux has CI evidence. Its real-machine confirmation is open
until a tester with a Linux PC runs Stage 2 (maintainer's decision, 2026-10-04; see
[linux.md](../platforms/linux.md)). macOS is deferred until after 1.0 (decision record 0014).

States: **Done** (with evidence), **Open** (with what it waits for), **Not M1** (plan 16.2
moves it to a later milestone).

## Deliverables

| # | Plan 14, M1 | State | Evidence |
|---|---|---|---|
| 1 | Verify and record every "(confirm at M1)" item from section 11 in `docs/platforms/` | Windows: Done, except Store behavior (W-04) and the cache file list (W-06), which have no install or test to settle them yet. Linux: Open | [windows.md](../platforms/windows.md): W-01 to W-03, W-05, W-07 (absence), W-09, W-10 and V0 confirmed on the maintainer's PC; W-08 is M5 (plan 16.2). [linux.md](../platforms/linux.md): L-01, L-05 and L-07 from the CI runner; L-02, L-03, L-04 and L-06 need Sober started once (Stage 2 on Linux) |
| 2 | macOS trust-file test (R-03) | Not M1 | Deferred with macOS (decision record 0014) |
| 3 | Specs S-10, S-11, S-12, S-14, S-16 and S-15's per-app part merged; diagnostic interception from source | Done | `docs/specs/`, all six now **Built**, so `tools/check_docs.py` fails if any automatable acceptance test has no test. Marking them Built found five missing tests: S-14 test 1 and S-16 test 5 were added, S-12 test 4 (cache clearing) is carried to M2 with Apply now, and S-15 tests 8 and 9 belong to M6 ([verdra-1/verdra#72](https://github.com/verdra-1/verdra/pull/72)) |
| 4 | `bark/resin`: CA with Name Constraints; ECDSA accepted by the Windows client and Sober | Windows: Done. Sober: Open | `tests/bark/test_resin.py`; Stage 2: on all 133 intercepted connections the Player accepted the ECDSA P-256 leaf over TLS 1.3 (`evidence/windows/stage2-2026-10-04.txt`). R-17 is closed for Windows ([risks.md](risks.md)) |
| 5 | `roots/mycelium`, `hyphae`, `taproot`: TLS server, h11, tunnels, verified upstream TLS, direct, system, HTTP and SOCKS5 transports | Done | S-11 tests 1 to 10 and 11 to 12 (`tests/roots/`) on both CI runners; Stage 2: 133 of 133 upstream certificates verified |
| 6 | `roots/gardener`, `trunk/branches/sprout`: per-app launch on Windows and Linux; `roblox-player:` links; Microsoft Store detection | Windows launch and links: Done. Linux: Open. Store detection: Open | Stage 2 steps 5 to 7 ([windows.md](../platforms/windows.md)); `tests/trunk/branches/test_sprout.py`, `tests/soil/meadow/`, `tests/soil/tundra/`. Linux launching is built and tested against a fake `flatpak`, but blocked with M-LAUNCH-04 until L-02 is confirmed. Store detection: see the proposal below |
| 7 | Status pill with reasons and fixes; ledger; Reset everything | Done | S-14 and S-16 tests, including S-14 test 1 end to end through the real proxy (which found that Degraded (c), a new Roblox version without the certificate, was never raised; now it is, with "Repair certificate"); Stage 2 steps 5, 8 and 9 |
| 8 | `tools/fake_roblox.py` and anonymised fixtures; coexistence check | Done | S-11 test 1 (1,000 replayed responses); S-15 tests 1 to 6; W-09 confirmed in Stage 2 step 8 |

## Exit gate

| Part | State | Evidence |
|---|---|---|
| Roblox runs through Verdra on **Windows** with verified TLS and byte-exact passthrough | Done | Stage 2 on the maintainer's PC: two games joined through Verdra, 133 of 133 connections TLS 1.3 with verified upstream certificates, no Roblox error. Byte-exact passthrough: S-11 tests 1 and 9 (1,000 responses, identity, gzip, zstd, chunked) on the Windows and Linux runners |
| Roblox runs through Verdra on **Linux** | Open | CI evidence only: Sober installs, its facts L-01, L-05 and L-07 are recorded, and every routing test passes on `ubuntu-24.04`. Sober has never been started with Verdra: that waits for a tester with a Linux PC (M2 or later) |
| Every 12.2 negative test that applies passes | Done | Below |
| Reset everything leaves zero entries | Done | `tests/trunk/branches/test_reset.py` (including a crash halfway through); Stage 2 step 9: "Removed 2 changes. Verdra left nothing behind." |

### Plan 12.2 negative tests

| Negative test | Applies at M1 | Evidence |
|---|---|---|
| Upstream with a self-signed or wrong-host certificate: the request fails and the status turns Degraded | Yes | `test_an_upstream_that_fails_verification_gives_502` (both certificates, 502, M-PROXY-02); `test_an_upstream_certificate_failure_turns_routing_degraded` (Degraded (b), reported from the proxy's thread) |
| Every 10.6 secret pattern through logs, Traffic, HAR export, saved traffic and support bundles: none survives | Logs and support bundles (Traffic, HAR and saved traffic don't exist yet) | S-03 tests 1, 8 and 9: every pattern, and signed-URL secrets, at every level in the file, the ring buffer and the bundle; bundles also replace user names and long IDs |
| Packs with `..` paths, absolute paths, symlinks, hash mismatches, over 10,000 files, decompression bombs | No: packs arrive at M7 | |
| Catalogue with a bad or missing signature | No: the catalogue arrives at M7 | |
| Keeper given a bad hostname, address, token or protocol version | No: the keeper arrives at M6 | |
| Process killed during a settings, profile or ledger write | Settings and ledger (profiles arrive at M2) | `test_kill_during_write_leaves_a_valid_file` (settings) and `test_kill_during_a_ledger_write_leaves_a_readable_ledger`, each killed 8 times at random mid-write |
| Process killed while routing in Hosts-file mode | No: Hosts-file mode arrives at M6 | |

## Open items

1. **Linux real-machine confirmation**: Stage 2 on a Linux PC with Sober confirms L-02, L-03,
   L-04 and L-06, ECDSA acceptance by Sober (R-17 for Linux), and routing through Verdra. Until
   then, routing Sober stays blocked with M-LAUNCH-04, which is a plain message.
2. **Microsoft Store detection (W-04)**: no Store install has been observed, so plan 16.4 (no code
   before the fact is recorded) leaves nothing to build on. Its only action, M-LAUNCH-02, sends
   the user to Hosts-file routing, which arrives at M6.
3. **Cache file list (W-06)**: needed by cache clearing (S-12 test 4), which is first used by
   Apply now at M2. A listing doesn't settle which files are cache.

## Proposed plan wording

Plan 14's M1 exit gate says "Roblox runs through Verdra on Windows and Linux". With Linux
deferred, that sentence can't be met, and plan 16.2 says a milestone is done only when its
real-machine tests pass. Proposed text:

> **Exit gate:** Roblox runs through Verdra on Windows (real machine) with verified TLS and
> byte-exact passthrough, and on Linux with CI evidence; Linux real-machine confirmation stays
> open until a Linux tester runs Stage 2 (M2 or later). Every negative test in 12.2 that applies
> passes; Reset everything leaves zero entries. Microsoft Store detection moves to M6, with the
> Hosts-file routing that M-LAUNCH-02 points to.

The same pattern fits M2's exit gate ("visible in game on Windows and Linux") while Linux stays
deferred.
