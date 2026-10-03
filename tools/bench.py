# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Proxy latency benchmark: spec S-11 test 5, Master plan 12.4 (nightly).

Measures the latency Verdra's proxy adds to an intercepted request. Every replayed response of
`tools/fake_roblox.py` is fetched twice over keep-alive TLS connections: once straight from the
fake server and once through Verdra (CONNECT, TLS to Verdra's leaf, Verdra's own verified TLS to
the server). The two fetches of a pair run back to back, in alternating order, so both see the
same machine at the same moment; a pair's added latency is the proxied time minus the direct
time. Connection setup (the TLS handshakes) is left out, as is a warm-up of `WARMUP` pairs: the
budget is per request. Each round reports the median and 95th percentile of the added latency;
the best of `ROUNDS` rounds is kept, so a moment of noise on a shared runner doesn't count.

Two checks, both of which fail the run (exit 1):

- the budget of plan 12.4: median at most 5 ms and 95th percentile at most 20 ms;
- `--max-regression P`: neither statistic may exceed the committed baseline
  (`tools/bench_baseline.json`) by more than P %. The comparison uses the added latency divided
  by the direct round trip measured in the same run, so a faster or slower runner doesn't move
  it; the baseline also records the milliseconds for reference.

    python -m tools.bench                         measure and check the budget
    python -m tools.bench --max-regression 20     also compare with the baseline (nightly)
    python -m tools.bench --write-baseline        measure and store the result as the baseline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import statistics
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from tests.support.client import FakeClient

from tools import fake_roblox
from verdra.bark import resin
from verdra.roots import hyphae, mycelium, taproot

BASELINE: Final = Path(__file__).with_name("bench_baseline.json")
#: Plan 12.4: added latency per intercepted request.
BUDGET_MEDIAN_MS: Final = 5.0
BUDGET_P95_MS: Final = 20.0
REQUESTS: Final = 1000
WARMUP: Final = 50
ROUNDS: Final = 5


@dataclass(frozen=True, slots=True)
class Result:
    """One measurement: added latency in milliseconds, and relative to the direct round trip."""

    requests: int
    median_ms: float
    p95_ms: float
    direct_median_ms: float
    #: The added latency divided by the direct round trip of the same round.
    median_ratio: float
    p95_ratio: float


def percentile(values: Sequence[float], share: float) -> float:
    """Return the `share` quantile (0 to 1) of `values`, by nearest rank."""
    ordered = sorted(values)
    rank = max(1, round(share * len(ordered) + 0.5 - 1e-9))
    return ordered[min(rank, len(ordered)) - 1]


def summarize(direct: Sequence[float], proxied: Sequence[float]) -> Result:
    """Return the added latency of paired fetches (seconds in, milliseconds out)."""
    added = [(p - d) * 1000 for d, p in zip(direct, proxied, strict=True)]
    median, p95 = statistics.median(added), percentile(added, 0.95)
    direct_median = statistics.median(direct) * 1000
    return Result(
        requests=len(added),
        median_ms=median,
        p95_ms=p95,
        direct_median_ms=direct_median,
        median_ratio=median / direct_median,
        p95_ratio=p95 / direct_median,
    )


def best(results: Sequence[Result]) -> Result:
    """Return the best of several rounds: each figure's lowest value, taken on its own."""
    return Result(
        requests=min(r.requests for r in results),
        median_ms=min(r.median_ms for r in results),
        p95_ms=min(r.p95_ms for r in results),
        direct_median_ms=min(r.direct_median_ms for r in results),
        median_ratio=min(r.median_ratio for r in results),
        p95_ratio=min(r.p95_ratio for r in results),
    )


def problems(result: Result, baseline: Result | None, max_regression: float | None) -> list[str]:
    """Return why `result` fails the budget or the regression limit (empty if it passes)."""
    found: list[str] = []
    if result.median_ms > BUDGET_MEDIAN_MS:
        found.append(f"median {result.median_ms:.2f} ms is over the {BUDGET_MEDIAN_MS} ms budget")
    if result.p95_ms > BUDGET_P95_MS:
        found.append(
            f"95th percentile {result.p95_ms:.2f} ms is over the {BUDGET_P95_MS} ms budget"
        )
    if baseline is not None and max_regression is not None:
        limit = 1 + max_regression / 100
        for name, now, then in (
            ("median", result.median_ratio, baseline.median_ratio),
            ("95th percentile", result.p95_ratio, baseline.p95_ratio),
        ):
            if now > then * limit:
                found.append(
                    f"{name} regressed {100 * (now / then - 1):.0f} % against the baseline "
                    f"(limit {max_regression:g} %)"
                )
    return found


async def measure(requests: int = REQUESTS, warmup: int = WARMUP) -> Result:
    """Fetch each response directly and through Verdra, in pairs; return the added latency."""
    replays = fake_roblox.responses(requests + warmup)
    now = datetime.now(UTC)
    authority = resin.create_authority(now)
    async with fake_roblox.FakeRoblox(replays, now=now) as server:

        async def open_upstream(host: str, _port: int) -> hyphae.Streams:
            return await taproot.open_tls(
                taproot.Transport("direct"),
                host,
                server.port,
                context=server.client_context(),
                address="127.0.0.1",
            )

        hosts = frozenset(fake_roblox.HOSTS)
        interception = hyphae.Interception(
            hyphae.LeafContexts(authority), lambda: hosts, open_upstream
        )
        proxy = mycelium.Mycelium(
            0,
            lambda _host, _port: asyncio.open_connection("127.0.0.1", server.port),
            interceptor=interception,
        )
        port = await proxy.start()
        trusts_verdra = ssl.create_default_context(
            cadata=resin.certificate_pem(authority.certificate).decode()
        )
        direct: dict[str, FakeClient] = {}
        proxied: dict[str, FakeClient] = {}
        times: tuple[list[float], list[float]] = ([], [])
        try:
            for replay in replays:
                host = replay.host
                if host not in direct:
                    reader, writer = await asyncio.open_connection(
                        "127.0.0.1", server.port, ssl=server.client_context(), server_hostname=host
                    )
                    direct[host] = FakeClient(reader, writer)
                    proxied[host] = await FakeClient.connect(port, host, trusts_verdra)
                pair = (direct[host], proxied[host])
                order = (0, 1) if replay.index % 2 else (1, 0)
                for which in order:
                    started = time.perf_counter()
                    answer = await pair[which].exchange(replay.request())
                    elapsed = time.perf_counter() - started
                    if answer != replay.raw:
                        raise AssertionError(f"replay {replay.index} came back changed")
                    if replay.index >= warmup:
                        times[which].append(elapsed)
        finally:
            for client in (*direct.values(), *proxied.values()):
                await client.close()
            await proxy.stop()
    return summarize(*times)


def load_baseline(path: Path | None = None) -> Result | None:
    """Return the committed baseline, or None before one is recorded."""
    path = path or BASELINE
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Result(**{field.name: data[field.name] for field in fields(Result)})


def report(result: Result, label: str) -> str:
    return (
        f"{label}: added latency median {result.median_ms:.3f} ms, 95th percentile "
        f"{result.p95_ms:.3f} ms over {result.requests} requests (direct round trip "
        f"{result.direct_median_ms:.3f} ms; ratios {result.median_ratio:.3f} and "
        f"{result.p95_ratio:.3f})"
    )


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark; exit 1 if the budget or the regression limit is missed."""
    parser = argparse.ArgumentParser(description="Measure the latency Verdra's proxy adds.")
    parser.add_argument("--requests", type=int, default=REQUESTS, help="pairs per round")
    parser.add_argument("--rounds", type=int, default=ROUNDS, help="rounds; the best is kept")
    parser.add_argument("--max-regression", type=float, help="percent allowed over the baseline")
    parser.add_argument("--write-baseline", action="store_true", help="store this result")
    args = parser.parse_args(argv)
    rounds = []
    for number in range(1, args.rounds + 1):
        rounds.append(asyncio.run(measure(args.requests)))
        print(report(rounds[-1], f"Round {number}"), flush=True)
    result = best(rounds)
    print(report(result, "Best"))
    if args.write_baseline:
        BASELINE.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
        print(f"Baseline written to {BASELINE.name}.")
    baseline = load_baseline()
    if args.max_regression is not None:
        print(report(baseline, "Baseline") if baseline else f"No {BASELINE.name} yet.")
    found = problems(result, baseline, args.max_regression)
    for problem in found:
        print(f"FAILED: {problem}")
    if not found:
        print("Within the latency budget of plan 12.4.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
