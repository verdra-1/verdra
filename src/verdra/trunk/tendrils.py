# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Job executor: worker pool, progress, cancellation, results back on the Qt thread.

Spec S-04. `Tendrils` is the app's only worker pool. A job is a plain function that receives a
`JobHandle`, reports progress through it and checks it for cancellation between steps. Each job's
signals are emitted from a worker thread and, because the `Job` object belongs to the Qt thread,
arrive there as queued signals: widgets never see a worker thread.

The workers are daemon threads, so a job that ignores cancellation can't keep Verdra from
quitting: shutdown cancels everything, waits up to 3 s, and then lets the process exit.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal

from verdra.bark import veil

log = logging.getLogger(__name__)

SLOW_AFTER_MS = 2_000
QUIT_GRACE_SECONDS = 3.0


class JobCanceledError(Exception):
    """Raised inside a job by `JobHandle.check` once the job has been cancelled."""


class JobState(Enum):
    """Where a job is in its life."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class JobHandle:
    """What a running job uses to report progress and notice cancellation."""

    def __init__(self, job: Job) -> None:
        self._job = job

    @property
    def canceled(self) -> bool:
        """Return whether the job has been asked to stop."""
        return self._job.cancel_requested

    def check(self) -> None:
        """Stop the job here if it has been cancelled.

        Raises:
            JobCanceledError: The job was cancelled; let it propagate.
        """
        if self._job.cancel_requested:
            raise JobCanceledError

    def report(self, percent: int | None, step: str = "") -> None:
        """Report progress: 0 to 100, or None for indeterminate, with a short step description."""
        if percent is not None:
            percent = max(0, min(100, int(percent)))
        self._job.progress = percent
        self._job.step = step
        self._job._relay.emit("progressed", (percent, step))  # noqa: SLF001 - same module


class Job(QObject):
    """One unit of background work and its outcome.

    Signals (all delivered on the Qt thread):
        progressed(percent, step): `percent` is an int from 0 to 100, or None.
        succeeded(result): The function returned `result`.
        failed(reason): The function raised; `reason` is short and redacted.
        canceled(): The job stopped because it was cancelled.
        finished(): After any of the three outcomes.
    """

    progressed = Signal(object, str)
    succeeded = Signal(object)
    failed = Signal(str)
    canceled = Signal()
    finished = Signal()
    # Emitted on the worker thread; connected to this object's own slot, so Qt queues it onto the
    # Qt thread. The public signals above are emitted from there, whatever their receivers are.
    _relay = Signal(str, object)

    def __init__(
        self, name: str, function: Callable[[JobHandle], Any], parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.state = JobState.QUEUED
        self.progress: int | None = None
        self.step = ""
        self.result: Any = None
        self.reason = ""
        self.started_at: float | None = None
        self._function = function
        self._cancel = threading.Event()
        self._done = threading.Event()
        self._relay.connect(self._deliver)

    @property
    def cancel_requested(self) -> bool:
        """Return whether `cancel` has been called."""
        return self._cancel.is_set()

    @property
    def done(self) -> bool:
        """Return whether the job has finished in any way."""
        return self._done.is_set()

    def cancel(self) -> None:
        """Ask the job to stop at its next check."""
        self._cancel.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the job has finished; return False on timeout. Not for the Qt thread."""
        return self._done.wait(timeout)

    def message(self) -> str:
        """Return the user-facing message for a cancelled or failed job (M-JOB-01, M-JOB-02)."""
        if self.state is JobState.CANCELED:
            return QCoreApplication.translate("M-JOB-01", "{task} canceled.").format(task=self.name)
        if self.state is JobState.FAILED:
            return QCoreApplication.translate(
                "M-JOB-02", "{task} failed: {reason}. Details are in Activity."
            ).format(task=self.name, reason=self.reason)
        return ""

    def run(self) -> None:
        """Run the job on the current (worker) thread and emit its outcome."""
        try:
            if self.cancel_requested:
                raise JobCanceledError
            self.state = JobState.RUNNING
            self.started_at = time.monotonic()
            self.result = self._function(JobHandle(self))
        except JobCanceledError:
            self.state = JobState.CANCELED
            log.debug("%s canceled.", self.name)  # the M-JOB-01 toast is the Activity entry
            self._relay.emit("canceled", ())
        except Exception as error:  # noqa: BLE001 - any failure is reported, never re-raised
            self.state = JobState.FAILED
            self.reason = veil.redact_text(str(error).rstrip(".")) or type(error).__name__
            # Technical detail behind M-JOB-02's "Details are in Activity": the exception.
            log.error("%s: %s", self.name, type(error).__name__, exc_info=error)
            self._relay.emit("failed", (self.reason,))
        else:
            self.state = JobState.SUCCEEDED
            self._relay.emit("succeeded", (self.result,))
        finally:
            # Relay first, then mark done: once `wait` returns, the job never touches Qt again.
            self._relay.emit("finished", ())
            self._done.set()

    def _deliver(self, signal: str, arguments: tuple[Any, ...]) -> None:
        getattr(self, signal).emit(*arguments)


class Tendrils(QObject):
    """The worker pool (spec S-04). Create it on the Qt thread.

    Signals:
        submitted(job): A job was queued; the shell reports its end (M-JOB-01, M-JOB-02).
        slow(job): A job is still running 2 s after it started; show its progress toast.
    """

    submitted = Signal(object)
    slow = Signal(object)

    def __init__(
        self, workers: int = 4, parent: QObject | None = None, *, start: bool = True
    ) -> None:
        """Create the pool; with `start=False` jobs queue until `start()` (plan 8.4 step 5)."""
        super().__init__(parent)
        self._queue: queue.SimpleQueue[Job | None] = queue.SimpleQueue()
        self._jobs: set[Job] = set()
        self._lock = threading.Lock()
        self._closed = False
        self._threads = [
            threading.Thread(target=self._work, name=f"verdra-tendril-{n}", daemon=True)
            for n in range(max(1, workers))
        ]
        if start:
            self.start()

    def start(self) -> None:
        """Start the worker threads; calling it again does nothing."""
        for thread in self._threads:
            if thread.ident is None:
                thread.start()

    @property
    def workers(self) -> int:
        """Return the number of worker threads."""
        return len(self._threads)

    def running(self) -> list[Job]:
        """Return the jobs that haven't finished yet."""
        with self._lock:
            return [job for job in self._jobs if not job.done]

    def submit(self, name: str, function: Callable[[JobHandle], Any]) -> Job:
        """Queue `function` to run on a worker and return its job.

        Args:
            name: What the job does, as people read it in a toast ("Exporting 12 assets").
            function: Called with a `JobHandle`; its return value becomes the job's result.
        """
        if self._closed:
            raise RuntimeError("the executor has shut down")
        # No Qt parent: Python owns the job, so a worker that is still finishing an abandoned job
        # can't outlive the C++ object it emits on.
        job = Job(name, function)
        with self._lock:
            self._jobs.add(job)
        job.finished.connect(lambda: self._forget(job))
        QTimer.singleShot(SLOW_AFTER_MS, self, lambda: self._check_slow(job))
        self.submitted.emit(job)
        self._queue.put(job)
        return job

    def _check_slow(self, job: Job) -> None:
        if not job.done:
            self.slow.emit(job)

    def _forget(self, job: Job) -> None:
        with self._lock:
            self._jobs.discard(job)

    def _work(self) -> None:
        while (job := self._queue.get()) is not None:
            job.run()

    def shutdown(self, grace: float = QUIT_GRACE_SECONDS) -> bool:
        """Cancel every job, wait up to `grace` seconds, and stop the workers.

        Returns:
            Whether every job finished in time. Jobs that didn't are abandoned; the worker
            threads are daemons, so they don't hold up the process's exit.
        """
        self._closed = True
        with self._lock:
            jobs = list(self._jobs)
        for job in jobs:
            job.cancel()
        deadline = time.monotonic() + grace
        finished = all(job.wait(max(0.0, deadline - time.monotonic())) for job in jobs)
        for _ in self._threads:
            self._queue.put(None)
        if not finished:
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-JOB-03",
                    "Some background tasks didn't stop within {seconds} s, so Verdra quit "
                    "without waiting for them.",
                ).format(seconds=f"{grace:.0f}"),
            )
        return finished
