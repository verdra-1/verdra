# S-04 Background jobs

**Status:** Agreed
**Milestone:** M0
**Risk badge:** none
**Plan sections:** 8.3, 8.4, 12.4, Reference R2 (`advanced.worker_threads`)

## Purpose

Run slow work off the UI thread with progress, cancellation and orderly shutdown.

## Behaviour

- One executor, `trunk/tendrils`, with a worker pool of `advanced.worker_threads` threads
  (default 4, range 2 to 8; a change applies after restart).
- A job is a named function that receives a handle through which it reports progress (0 to 100,
  or indeterminate) with a short step description, and checks for cancellation.
- Results, progress and errors are delivered on the Qt thread through queued signals.
- A job that runs longer than 2 s appears in a progress toast showing its name, step and progress,
  with a "Cancel" action.
- Cancelling sets the job's cancellation flag; a job checks it between steps and stops. A
  cancelled job reports M-JOB-01.
- A job that raises reports M-JOB-02 with a plain reason, and the full error (redacted, S-03)
  goes to Activity.
- On quit, running jobs get a cancel signal and 3 s to finish; after that Verdra exits anyway.

## Rules

1. No other thread pools anywhere in the code; the proxy's own asyncio thread (plan 8.3) is not a
   pool and is the only other long-lived thread.
2. No polling loops: work is event- or timer-driven, and timers fire at most once per second while
   idle.
3. Jobs never touch widgets; they hand results back through the executor.

## Messages

- M-JOB-01 "<Task> canceled."
- M-JOB-02 "<Task> failed: <reason>. Details are in Activity." The details are a technical record
  of the task's name, the exception's type and its traceback, redacted.
- M-JOB-03 (new, kind Activity) "Some background tasks didn't stop within <seconds> s, so Verdra
  quit without waiting for them."

## Acceptance tests

1. Cancel stops a job within 500 ms.
2. Quit with running jobs exits within 4 s.
3. The idle CPU budget from plan 12.4 (at most 0.5 % of one core) holds with the executor running.
4. Progress and results arrive on the Qt thread.
5. A job running longer than 2 s shows a progress toast with "Cancel"; a shorter one doesn't.
6. A failing job shows M-JOB-02 and writes the error to Activity.

## Lives in

`trunk/tendrils.py`.

## Refinements from the plan

- **Worker count**: 2 to 8, default 4 (plan S-04; Reference R2 now matches; decision record
  0008).
- The quit grace period (3 s) plus flushing keeps test 2 within 4 s.
