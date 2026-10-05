# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-04: background jobs."""

import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from verdra.trunk import rings
from verdra.trunk.tendrils import JobHandle, JobState, Tendrils


@pytest.fixture
def tendrils(qtbot: QtBot) -> Iterator[Tendrils]:
    pool = Tendrils(workers=4)
    yield pool
    pool.shutdown(grace=1.0)


def busy(seconds: float) -> Callable[[JobHandle], str]:
    def work(handle: JobHandle) -> str:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            handle.check()
            time.sleep(0.01)
        return "done"

    return work


@pytest.mark.spec("S-04", 1)
def test_cancel_stops_a_job_within_500_ms(tendrils: Tendrils, qtbot: QtBot) -> None:
    job = tendrils.submit("Long task", busy(30))
    qtbot.waitUntil(lambda: job.state is JobState.RUNNING, timeout=1000)
    started = time.monotonic()
    with qtbot.waitSignal(job.canceled, timeout=500):
        job.cancel()
    assert time.monotonic() - started < 0.5
    assert job.message() == "Long task canceled."


@pytest.mark.spec("S-04", 2)
def test_quit_with_running_jobs_exits_within_4_s(tmp_path: Path) -> None:
    script = textwrap.dedent(
        """
        import time
        from PySide6.QtCore import QCoreApplication
        from verdra.trunk.tendrils import Tendrils

        app = QCoreApplication([])
        pool = Tendrils(workers=4)

        def polite(handle):
            while True:
                handle.check()
                time.sleep(0.01)

        def stubborn(handle):
            time.sleep(60)  # never checks for cancellation

        for _ in range(3):
            pool.submit("Polite", polite)
        pool.submit("Stubborn", stubborn)
        time.sleep(0.3)
        print("quitting", flush=True)
        print("finished" if pool.shutdown() else "abandoned", flush=True)
        """
    )
    # Timed from the quit to the process's exit; starting Python and Qt doesn't count.
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", script], stdout=subprocess.PIPE, text=True
    )
    assert process.stdout is not None
    try:
        assert process.stdout.readline().strip() == "quitting"
        quit_at = time.monotonic()
        rest, _ = process.communicate(timeout=10)
        elapsed = time.monotonic() - quit_at
    finally:
        process.kill()
    assert process.returncode == 0
    assert rest.strip() == "abandoned"
    assert elapsed < 4.0


@pytest.mark.spec("S-04", 3)
def test_idle_cpu_budget(tendrils: Tendrils, qtbot: QtBot) -> None:
    jobs = [tendrils.submit("Warm-up", lambda _handle: None) for _ in range(tendrils.workers)]
    qtbot.waitUntil(lambda: all(job.done for job in jobs), timeout=1000)
    window = 2.0
    before = time.process_time()
    time.sleep(window)
    used = time.process_time() - before
    assert used <= 0.005 * window, f"{used * 1000:.1f} ms of CPU in {window} s idle"


@pytest.mark.spec("S-04", 4)
def test_progress_and_results_arrive_on_the_qt_thread(tendrils: Tendrils, qtbot: QtBot) -> None:
    main = threading.get_ident()
    seen: list[tuple[str, int]] = []

    def work(handle: JobHandle) -> int:
        for step in range(3):
            handle.report(step * 50, f"Step {step + 1}")
        return 42

    job = tendrils.submit("Counting", work)
    job.progressed.connect(lambda percent, step: seen.append((step, threading.get_ident())))
    job.succeeded.connect(lambda result: seen.append((str(result), threading.get_ident())))
    with qtbot.waitSignal(job.finished, timeout=1000):
        pass
    assert [entry[0] for entry in seen] == ["Step 1", "Step 2", "Step 3", "42"]
    assert {entry[1] for entry in seen} == {main}
    assert job.result == 42


@pytest.mark.spec("S-04", 5)
def test_slow_jobs_are_announced_after_2_s(tendrils: Tendrils, qtbot: QtBot) -> None:
    announced: list[str] = []
    tendrils.slow.connect(lambda job: announced.append(job.name))
    quick = tendrils.submit("Quick", busy(0.2))
    slow = tendrils.submit("Slow", busy(3))
    qtbot.waitUntil(lambda: announced == ["Slow"], timeout=2600)
    assert quick.done
    slow.cancel()


@pytest.mark.spec("S-04", 6)
def test_a_failing_job_reports_and_logs(tendrils: Tendrils, qtbot: QtBot, tmp_path: Path) -> None:
    installed = rings.Rings(tmp_path / "logs")
    installed.start()

    def broken(_handle: JobHandle) -> None:
        raise OSError("The disk is full")

    job = tendrils.submit("Exporting 12 assets", broken)
    with qtbot.waitSignal(job.failed, timeout=1000) as signal:
        pass
    installed.stop()
    assert signal.args == ["The disk is full"]
    assert job.message() == "Exporting 12 assets failed: The disk is full. Details are in Activity."
    # The record behind "Details are in Activity": task name, exception type and traceback.
    (record,) = [
        r for r in installed.ring.snapshot() if "Exporting 12 assets: OSError" in r.message
    ]
    assert "OSError: The disk is full" in record.message


def test_submit_after_shutdown_is_refused(qtbot: QtBot) -> None:
    pool = Tendrils(workers=1)
    assert pool.shutdown()
    with pytest.raises(RuntimeError):
        pool.submit("Late", lambda _handle: None)


def test_finished_jobs_are_forgotten(tendrils: Tendrils, qtbot: QtBot) -> None:
    job = tendrils.submit("Short", lambda _handle: None)
    with qtbot.waitSignal(job.finished, timeout=1000):
        pass
    qtbot.waitUntil(lambda: tendrils.running() == [], timeout=1000)


def test_jobs_wait_until_the_workers_start(qtbot: QtBot) -> None:
    # Plan 8.4: the pool is created before the splash but its workers start at step 5.
    pool = Tendrils(workers=2, start=False)
    try:
        job = pool.submit("Early save", lambda _handle: "saved")
        time.sleep(0.2)
        assert job.state is JobState.QUEUED
        pool.start()
        pool.start()
        qtbot.waitUntil(lambda: job.state is JobState.SUCCEEDED, timeout=2000)
        assert pool.workers == 2
    finally:
        pool.shutdown(grace=1.0)
