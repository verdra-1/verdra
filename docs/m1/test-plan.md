# M1 test plan

How the M1 specs (S-10, S-11, S-12, S-14, S-15 per-app part, S-16) are tested, in the layers of plan 12.1, and how
each required negative test in plan 12.2 that applies at M1 is covered. Every acceptance test
named here gets a `@pytest.mark.spec("S-xx", n)` marker, so `tools/check_docs.py` fails the
build when a Built spec has an untested acceptance test.

## Layers

| Layer | Runs | What it covers at M1 |
|---|---|---|
| Unit | Every pull request, Windows and Linux | `bark/resin` (CA and leaf profiles), `bark/scar` (ledger), `bark/husk` (secret store with a fake keyring backend), `roots/rules` (snapshot swap), `roots/gardener` status machine (fake clock), `trunk/branches/fallow` undo actions on fixture folders, `trunk/branches/sprout` launch arguments and environment, `soil/*/files.py` and `launcher.py` on their own OS |
| Property (Hypothesis) | Every pull request short, nightly long | Trust-file block add and remove round trip on random PEM bundles (byte-identical); link forwarding byte-identical for random `roblox-player:` links; ledger read, write, read round trip; HTTP/1.1 framing through `hyphae` (random chunk sizes, keep-alive sequences) |
| Proxy integration | Every pull request, Windows and Linux | `tools/fake_roblox.py` over real TLS on loopback: passthrough, tunnelling, upstream verification, transports, limits, symbiont errors |
| UI (pytest-qt, offscreen) | Every pull request | Status pill, popover and tray in every state; System changes list; Reset everything dialog, progress and summary; keyboard reach and accessible names |
| Benchmark | Nightly | S-11 test 5 (latency), idle CPU with routing on (S-04 test 3, plan 12.4) |
| Platform smoke | M1 gate, manual | [`docs/platforms/protocol.md`](../platforms/protocol.md), S-10 test 8, S-12 tests 1 and 2 (Windows and Linux; macOS is deferred, decision record 0014) |

## `tools/fake_roblox.py`

A test tool, not shipped. Written from the plan and the public HTTP and TLS specifications only.

- An HTTPS server on loopback with a test CA made per test session (never a real certificate),
  serving hosts from plan 10.2 by SNI. Additional modes: a self-signed certificate, a
  certificate for the wrong host, TLS 1.1 only (must be refused), an HTTP CONNECT upstream proxy
  and a SOCKS5 upstream proxy (with and without credentials) for S-11 test 8 (see below).
- Responses come from fixture files in `tests/fixtures/roblox/`: status, headers and body,
  replayed byte for byte, with variants for `Content-Encoding` (none, gzip, br, zstd as the plan's
  dependencies support) and chunked transfer.
- The HTTP CONNECT and SOCKS5 upstream proxies for S-11 test 8 live with that test, in
  `tests/roots/test_taproot.py`.
- A fake client (`tests/support/client.py`) that connects through Verdra's proxy with `CONNECT`,
  verifies against Verdra's CA, and records the bytes it receives.
- **Fixtures:** plan 12.1 says "recorded, anonymised". At M1 there's no capture feature yet, so
  the first fixtures are written by hand from public descriptions of the response shapes, with
  invented IDs and no real user data. Recorded fixtures replace them from M2, through the
  capture path with the redaction filter, reviewed by the maintainer before they're committed.
  Each fixture file states its origin in a header line.

## Acceptance tests by layer

| Spec | Test | Layer | Notes |
|---|---|---|---|
| S-10 | 1 CA profile, Name Constraints | Unit | `cryptography` path validation with `example.com` and `assetdelivery.roblox.com` leaves |
| S-10 | 2 Block added once, removed byte-identical | Unit + property | Fixtures of each recorded trust file; read-only flag on Windows and Linux |
| S-10 | 3 New version folder gets the block | Integration | Fixture install folder; folder watch through `QFileSystemWatcher`; 10 s limit |
| S-10 | 4 Rotation | Unit | Fake clock; fake secret store |
| S-10 | 5 No key on disk, except the Linux fallback | Integration | Scan config, cache, log, temp folders for PEM, DER and the raw scalar; with no Secret Service (fake keyring backend), exactly one key file, mode 0600, owned by the user, M-CA-03 shown, deleted by Reset everything |
| S-10 | 6 Leaves in memory only | Unit + integration | Same scan after leaves are made |
| S-10 | 7 Write-ahead ledger | Unit | Crash injected between ledger write and file change |
| S-10 | 8 Roblox accepts the leaf | Manual | Platform smoke |
| S-11 | 1 Byte-identical passthrough of 1,000 responses | Integration | Intercepted and tunnelled, all encodings |
| S-11 | 2 Tunnelling | Integration | Fake server sees the client's own ClientHello |
| S-11 | 3 Upstream certificate failures | Integration | Self-signed and wrong host → 502, M-PROXY-02, Degraded |
| S-11 | 4 Symbiont exception | Integration | Test symbiont that raises; Activity record redacted |
| S-11 | 5 Latency | Benchmark | Nightly; 20 % regression fails |
| S-11 | 6 Loopback only, port fallback | Integration | Port held by a test socket; every port refused by a fake binder |
| S-11 | 7 Limits | Integration | 257 connections, 30 s idle (fake clock), 65 MB body |
| S-11 | 8 Transports | Integration | Direct, system (fake system proxy setting), HTTP CONNECT, SOCKS5 |
| S-11 | 9 Diagnostic interception from source | Integration | Every 10.2 host intercepted, byte-identical, TLS details in Activity, M-DIAG-01 shown |
| S-11 | 10 Flag absent from frozen builds | Build job | The frozen app rejects the flag; `tools/check_build.py` finds no diagnostic code path |
| S-12 | 1, 2 Real launches | Manual | Platform smoke |
| S-12 | 3 Handler restore | Unit (per OS) | Windows: a test registry key under HKCU in a scratch subkey; Linux: the handler query functions behind a fake, plus one real round trip on the CI runner where the API is user-level |
| S-12 | 4 Cache clearing | Unit | Fixture folder with lookalike names; fake process list |
| S-12 | 5 Environment | Unit | Fake launcher records the environment |
| S-12 | 6 Link forwarded unchanged | Property | Random links |
| S-12 | 7 Not found, Microsoft Store | Unit | Fixture install layouts |
| S-14 | 1 Each trigger within 2 s | Integration | Fake client and `fake_roblox.py` |
| S-14 | 2 Pill, tray icon and line agree | UI | All states and reasons |
| S-14 | 3 Priority | Unit | Status machine |
| S-14 | 4 One log record per change | Unit | Fake clock |
| S-14 | 5 Fix buttons | UI | Keyboard and accessible names |
| S-14 | 6 No polling | Unit | Timer inspection |
| S-15 | 1 Foreign proxy blocks start | Integration | Fake Roblox client process with another proxy; Verdra's own or none passes |
| S-15 | 2 Try again | Integration | After the fake client exits |
| S-15 | 3 Foreign hosts-file mapping blocks start | Unit | Test copy of a hosts file at a temporary path; the real hosts file is never read in tests |
| S-15 | 4 Own port taken is not a sign | Integration | Another loopback listener on 49443; start goes ahead on another port, M-PROXY-03 |
| S-15 | 5 Other processes ignored | Unit | Fake process list |
| S-15 | 6 Unreadable environment | Unit | Simulated access error; start goes ahead, Activity notes it |
| S-15 | 7 Off the UI thread, within 2 s | Unit | 200 fake processes, 2,000-line hosts file |
| S-15 | 8, 9 Hosts-file part | M6 | Built with S-13 |
| S-16 | 1 Snapshot equals pre-install | Integration (per OS) | M1 entry kinds on a test home folder |
| S-16 | 2 Crash mid-change | Unit | Crash at each point, per kind |
| S-16 | 3 Second reset | Unit | Nothing changed (hashes) |
| S-16 | 4 Failed item, retry | Unit | Read-only fixture |
| S-16 | 5 Works when routing is broken | Integration | Port taken |
| S-16 | 6 Command line | Integration | Runs `verdra --reset-everything [--quiet]` as a subprocess |
| S-16 | 7 Foreign content untouched | Unit | Trust file with a foreign block |
| S-16 | 8 Dialog keyboard and Activity | UI | |

## Required negative tests (plan 12.2) at M1

| Negative test | Applies at M1 | Covered by |
|---|---|---|
| Upstream self-signed or wrong-host certificate: request fails, status Degraded | Yes | S-11 test 3, S-14 test 1 |
| Every secret pattern through logs, Traffic, HAR, saved traffic, support bundles | Logs and support bundles (Traffic and HAR are M3) | S-03 test 1 (M0) extended with the proxy's own log lines: S-11 rule 4, tested by feeding every 10.6 pattern through request and response headers and bodies of `fake_roblox.py` and scanning file, ring buffer and bundle |
| Packs with bad paths, symlinks, hash mismatch, too many files, bombs | No (packs are M7) | |
| Catalogue with a bad or missing signature | No (M7) | |
| Keeper given bad input | No (keeper is M6) | |
| Process killed during a settings, profile or ledger write | Settings: yes (M0, S-02 test 1); ledger: yes, new at M1 | New ledger kill test, same method as S-02 test 1 (child process killed during repeated writes; file valid or restored from `.bak`); S-16 test 2 |
| Process killed while routing in Hosts-file mode | No (M6) | |

## Coverage

Plan 12.1 floors apply from M1 to the new areas: `roots` and `bark` at least 85 %, `soil` at
least 70 % on its own platform, changed lines at least 80 %. `tools/coverage_floors.py` already
enforces them; the M1 pull requests must not lower any floor.

## Not covered automatically

- Real Roblox and Sober behaviour (S-10 test 8, S-12 tests 1 and 2, V0): manual in the first
  real-machine test session (the Windows PC, and Ubuntu in a virtual machine on it), with Verdra run from source with `--diagnose-interception`; results
  recorded in `docs/platforms/`.
- Linux `xdg-mime` changes on the user's real profile: CI tests them
  on throwaway runner profiles only.
- Microsoft Store Roblox: needs a Windows machine with that version installed.
