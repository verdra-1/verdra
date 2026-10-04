# S-11 Proxy core

**Status:** Agreed
**Milestone:** M1
**Risk badge:** none
**Plan sections:** 8.3, 10.1, 10.2, 10.4, 10.6, 12.1, 12.2, 12.4, 15 (R-01, R-18), Reference R2
(`routing.proxy_port`, `routing.upstream.*`), R3 (proxy address), R5 (M-PROXY-01 to M-PROXY-05)

## Purpose

Accept Roblox's connections, decrypt only what features need, and pass everything else through
untouched.

## Behaviour

- **Listener.** One listener on `127.0.0.1`, port `routing.proxy_port` (default 49443). If that
  port is taken, Verdra uses any free loopback port for this session and writes M-PROXY-03 to
  Activity; if none is free, routing doesn't start and M-PROXY-01 is shown. Verdra never listens
  on any other interface.
- **Interception decision.** For each `CONNECT host:port`: if the host is in the active
  interception set (plan 10.2, built from the features that are on), Verdra terminates TLS with a
  leaf certificate from S-10 (TLS 1.2 and 1.3, ALPN http/1.1), parses HTTP/1.1 with keep-alive and
  chunked transfer through h11, runs the symbiont pipeline and forwards upstream. Any other host
  gets a blind tunnel: bytes are copied both ways without TLS termination.
- **Upstream.** `roots/taproot` connects to the real server through the transport in
  `routing.upstream.kind` (system proxy, direct, HTTP CONNECT, SOCKS5 with optional username and
  password from the secret store). TLS towards the server verifies the certificate against the OS
  trust store (truststore), checks the hostname, requires TLS 1.2 or newer and sends the right SNI
  even when connecting to a pre-resolved address (plan 10.4). There is no option to turn
  verification off.
- **Verification failure.** The request fails with HTTP 502 to the client, M-PROXY-02 is shown,
  the routing status turns Degraded with the reason (S-14), and the event is logged.
- **Bodies.** A body is buffered only when a symbiont asks for it; otherwise it is streamed.
  Unmodified responses are forwarded byte for byte, including their content encoding. Modified
  responses are sent decoded, with a correct Content-Length.
- **Symbiont pipeline.** Request order: trail guard → grafter → forager. Response order: forager →
  grafter → climate → mimicry. The forager always sees the original upstream content and the
  original asset IDs. At M1 no symbiont is active yet (they arrive with S-21, S-30, S-41, S-52,
  S-53); the pipeline and its error handling are built and tested with test symbionts.
- **Diagnostic interception (M1 testing only).** The command-line flag
  `--diagnose-interception`, available only when Verdra runs from source, makes every host in
  plan 10.2 intercepted: Verdra terminates TLS with its leaf certificate, passes every request
  and response through byte for byte unchanged (no symbiont runs), and logs the TLS details of
  both sides (protocol version, cipher, whether the upstream chain verified, the leaf's key
  type). While it is on, a persistent Notice says so (M-DIAG-01). The flag doesn't exist in
  frozen builds: the frozen app rejects it as an unknown argument, and `tools/check_build.py`
  proves that the built folder holds no code path for it.
- **Rules from services.** Symbionts read an immutable rule snapshot that services swap in with
  one reference assignment (plan 8.3); the proxy never takes a lock to read it.

## Rules

1. Limits: 256 concurrent connections, 30 s idle timeout, 64 MB buffered body. Beyond them the
   connection is closed (or the body streamed unbuffered) and the event is logged.
2. The proxy runs on its own asyncio thread and never blocks on disk, the UI or the network
   beyond the request it is forwarding (plan 8.3).
3. An exception in a symbiont is logged (redacted) and that symbiont is skipped for that request;
   the request still completes.
4. Every log line from the proxy passes through `bark/veil`; headers and bodies are redacted per
   plan 10.6 before they reach any output.
5. The proxy decrypts only hosts in the active interception set; with no feature on, nothing is
   decrypted. The one exception is `--diagnose-interception` when running from source, which
   changes nothing it passes on.
6. Roblox's integrity and safety endpoints (`PROTECTED_PATHS` in `roots/rules`, from the Stage 2
   capture: `/validate-machine`, `/rm3-evidence-filter`, `/realtime-replay-api`,
   `/account-security-service`, `/browser-tracker-api` on `apis.roblox.com`, and everything
   below them) pass through byte-for-byte: no symbiont is called for them, whatever the path's
   spelling (case, percent-escapes, repeated slashes, dot segments, path parameters). Every rule
   a feature makes goes through `rules.refuse_protected`, which refuses these paths (plan 16.2).

## Messages

- M-PROXY-01 (Notice) "Verdra couldn't start routing: port <port> is in use and no other port was
  free."
- M-PROXY-02 (Toast) "A Roblox server's certificate couldn't be verified (<host>). That request was
  blocked."
- M-PROXY-03 (Activity, new) "Port <port> was in use, so Verdra is using port <other> this
  session."
- M-PROXY-04 (Activity, new) "Part of a feature failed on <host>, so it was skipped for that
  request (<error>)." The error text is redacted (rule 4).
- M-PROXY-05 (Activity, new) "A request or response for <host> was over 64 MB, so Verdra passed
  it on without changing it."
- M-DIAG-01 (Notice, new) "Diagnostic interception is on. Verdra is reading Roblox's traffic to
  check it, and changes nothing. Restart Verdra without --diagnose-interception to turn it off."
- M-DIAG-02 (Activity, new) "Diagnostic interception, <host> (<where>): <version>, <cipher>,
  <detail>." <where> is "Roblox to Verdra" or "Verdra to the server"; <detail> is "Verdra's
  certificate, key <key>", "the server's certificate verified" or "the server's certificate not
  verified".

## Acceptance tests

1. Passthrough of 1,000 recorded, anonymised responses (fixtures replayed by
   `tools/fake_roblox.py` over real TLS) is byte-identical, for both intercepted and tunnelled
   hosts, with and without content encoding and chunked transfer.
2. Non-intercepted hosts are tunnelled: the fake server sees the client's own TLS handshake (no
   TLS termination by Verdra), and Verdra's log has no request line for them.
3. An upstream with a self-signed certificate, and one with a certificate for the wrong host, both
   give HTTP 502 to the client, M-PROXY-02, and status Degraded with the reason.
4. A symbiont that raises doesn't fail the request: the response arrives intact and the error is
   in Activity, redacted.
5. Latency budget from plan 12.4: added latency per intercepted request has a median of at most
   5 ms and a 95th percentile of at most 20 ms in the proxy benchmark (nightly; a regression above
   20 % fails it).
6. The listener binds only to 127.0.0.1; with the default port taken it uses another loopback port
   and writes M-PROXY-03; with every port refused it shows M-PROXY-01.
7. The limits hold: the 257th concurrent connection is refused, an idle connection closes after
   30 s, and a 65 MB body is streamed rather than buffered.
8. Each upstream transport (direct, system, HTTP CONNECT, SOCKS5 with and without credentials)
   carries a request to the fake server, with SNI and hostname verification intact.
9. With `--diagnose-interception` from source, every 10.2 host is intercepted, 1,000 replayed
   responses arrive byte-identical, each connection's TLS details are in Activity, and M-DIAG-01
   shows for as long as it is on.
10. The frozen build rejects `--diagnose-interception` (it exits with an error and routing never
    starts), and `tools/check_build.py` fails if the built folder contains the diagnostic code
    path (a marker that only the source-only module carries).
11. A symbiont that changes every request and response, and one that answers every request
    itself, leave a protected endpoint untouched: the server receives the client's bytes and the
    client receives the server's, under every spelling of the path; neither symbiont is called.
12. A rule for any protected path, under any spelling, is refused with `ProtectedEndpointError`;
    a rule for a neighboring path (`/validate-machines`, `/v1/validate-machine`) is allowed.

## Lives in

`roots/mycelium.py`, `roots/hyphae.py`, `roots/taproot.py`, `roots/rules.py`,
`roots/symbionts/*`.

## Refinements from the plan

- Rule 6 and tests 11 and 12 carry out plan 16.2 ("Security endpoints are never touched"); the
  paths are the security-related ones seen in the Stage 2 capture on Windows (2026-10-04).
- Tests 6, 7 and 8 are added for behaviour the plan states (10.1 listener, S-11 limits, 10.4
  transports) but S-11 doesn't test; tests 9 and 10 cover the diagnostic interception settled in
  16.2.
- Test 1 states where the 1,000 responses come from (anonymised fixtures, plan 12.1).
- Test 5 measures the added latency as the difference between a request fetched through Verdra
  and the same request fetched directly, back to back on keep-alive connections (handshakes left
  out: the budget is per request). The 20 % regression is judged on that difference divided by
  the direct round trip of the same run, against a baseline committed as
  `tools/bench_baseline.json` from the nightly runner, so a faster or slower runner doesn't count
  as a change; the budget itself is judged in milliseconds.
- The plan's symbionts are built in later milestones; at M1 the pipeline is tested with test
  symbionts only, which is why test 4 doesn't name a real one.
- M-DIAG-02 is added so test 9's TLS details reach Activity with a message ID. The frozen
  build's refusal of the flag (test 10) is the standard command-line error ("unrecognized
  arguments", exit code 2) and has no message ID (plan 16.2, "M1 decisions"; decision record
  0015). Where the diagnostic code lives is decision record 0015 (`roots/litmus.py`, source
  only).
- M-PROXY-04 and M-PROXY-05 are added so the events rules 1 and 3 log reach Activity with a
  message ID (plan 16.2, F13).
- **Diagnostic interception** (plan 16.2, settled): see Behaviour. It exists so the M1 gate can
  check verified TLS and ECDSA acceptance (R-17) on real clients before any feature
  intercepts.
