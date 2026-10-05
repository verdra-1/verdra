# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""The proxy latency benchmark (tools/bench.py): spec S-11 test 5, plan 12.4."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tools import bench


def result(median: float, p95: float, direct: float = 0.2) -> bench.Result:
    return bench.Result(100, median, p95, direct, median / direct, p95 / direct)


@pytest.mark.spec("S-11", 5)
def test_the_proxy_adds_less_latency_than_the_budget() -> None:
    """A short run of the real measurement on this runner; the nightly run does 5 × 1,000."""
    measured = asyncio.run(asyncio.wait_for(bench.measure(requests=200, warmup=20), timeout=120))
    assert measured.requests == 200
    assert bench.problems(measured, None, None) == []
    assert measured.direct_median_ms > 0


def test_percentile_is_by_nearest_rank() -> None:
    values = [float(n) for n in range(1, 101)]
    assert bench.percentile(values, 0.95) == 95.0
    assert bench.percentile(values, 0.5) == 50.0
    assert bench.percentile([3.0], 0.95) == 3.0
    assert bench.percentile([2.0, 1.0], 1.0) == 2.0


def test_pairs_are_summarized_in_milliseconds() -> None:
    direct = [0.001] * 19 + [0.002]
    proxied = [0.0015] * 19 + [0.010]
    summary = bench.summarize(direct, proxied)
    assert summary.requests == 20
    assert summary.median_ms == pytest.approx(0.5)
    assert summary.p95_ms == pytest.approx(0.5)
    assert summary.direct_median_ms == pytest.approx(1.0)
    assert summary.median_ratio == pytest.approx(0.5)


def test_the_best_round_takes_each_figure_on_its_own() -> None:
    best = bench.best([result(0.4, 0.9), result(0.5, 0.6, direct=0.25)])
    assert (best.median_ms, best.p95_ms) == (0.4, 0.6)
    assert best.median_ratio == pytest.approx(2.0)
    assert best.p95_ratio == pytest.approx(2.4)


def test_the_budget_of_plan_12_4_is_checked() -> None:
    assert bench.problems(result(5.0, 20.0), None, None) == []
    assert bench.problems(result(5.1, 20.1), None, None) == [
        "median 5.10 ms is over the 5.0 ms budget",
        "95th percentile 20.10 ms is over the 20.0 ms budget",
    ]


def test_a_regression_above_the_limit_fails_and_one_below_passes() -> None:
    baseline = result(0.4, 0.6)
    assert bench.problems(result(0.47, 0.71), baseline, 20) == []
    assert bench.problems(result(0.49, 0.6), baseline, 20) == [
        "median regressed 22 % against the baseline (limit 20 %)"
    ]
    assert bench.problems(result(0.49, 0.6), baseline, None) == []


def test_the_regression_is_judged_relative_to_the_direct_round_trip() -> None:
    """A runner twice as slow doubles both times; that isn't a regression."""
    assert bench.problems(result(0.8, 1.2, direct=0.4), result(0.4, 0.6), 20) == []


def test_the_baseline_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    assert bench.load_baseline(path) is None
    path.write_text(json.dumps(bench.asdict(result(0.4, 0.6))), encoding="utf-8")
    assert bench.load_baseline(path) == result(0.4, 0.6)


def test_the_committed_baseline_is_within_the_budget() -> None:
    baseline = bench.load_baseline()
    assert baseline is not None
    assert bench.problems(baseline, None, None) == []


def test_main_reports_and_writes_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rounds = iter([result(0.5, 0.7), result(0.4, 0.9)])

    async def fake_measure(_requests: int) -> bench.Result:
        return next(rounds)

    path = tmp_path / "baseline.json"
    monkeypatch.setattr(bench, "measure", fake_measure)
    monkeypatch.setattr(bench, "BASELINE", path)
    assert bench.main(["--rounds", "2", "--write-baseline", "--max-regression", "20"]) == 0
    assert bench.load_baseline(path) == bench.best([result(0.5, 0.7), result(0.4, 0.9)])
    out = capsys.readouterr().out
    assert "Best: added latency median 0.400 ms, 95th percentile 0.700 ms" in out
    assert "Within the latency budget of plan 12.4." in out


def test_main_fails_on_a_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_measure(_requests: int) -> bench.Result:
        return result(1.0, 1.0)

    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(bench.asdict(result(0.4, 0.6))), encoding="utf-8")
    monkeypatch.setattr(bench, "measure", fake_measure)
    monkeypatch.setattr(bench, "BASELINE", path)
    assert bench.main(["--rounds", "1", "--max-regression", "20"]) == 1
    out = capsys.readouterr().out
    assert "FAILED: median regressed 150 % against the baseline (limit 20 %)" in out
    assert bench.main(["--rounds", "1"]) == 0  # without --max-regression only the budget counts
