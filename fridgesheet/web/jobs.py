"""One worker thread inside the server: refresh, preview, print, doctor and test login, one at a
time, with progress lines the page streams over server-sent events (spec section 9).

The worker never touches the request's database connection; each action opens its own. A job
that holds the runner's lock (refresh, preview, print) fails cleanly when a scheduled CLI run
holds it first, and the CLI run fails cleanly the other way round -- that is the whole point
of sharing `run.lock`.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from . import actions as _actions

KINDS = ("refresh", "preview", "print", "reprint", "doctor", "login", "update",
         "scheduled-refresh", "scheduled-report")
LABELS = {"refresh": "Refreshing", "preview": "Building today's sheet", "print": "Printing",
          "reprint": "Printing again", "doctor": "Running diagnostics", "login": "Testing the login",
          "update": "Updating Fridge Sheet",
          "scheduled-refresh": "Refreshing on schedule", "scheduled-report": "Running a scheduled report"}
#: Kinds `POST /jobs/{kind}` (the open, unauthenticated route) may start on its own authority.
#: `update` downloads a release asset and executes it as an installer -- the one job kind that
#: is code execution on the family PC, not a read of Canvas/HAC -- so it is started only by the
#: PIN-gated `POST /settings/update` (routes/settings.py). `OPEN_KINDS` is derived from `KINDS`
#: minus `GATED`, not listed on its own, so a kind added to `KINDS` later is never accidentally
#: made public here by someone forgetting to add it to a separate allowlist.
#: `scheduled-*` are the server's own clock's (web/clock.py): started by nothing a request can
#: reach, so the Runs page's "On a schedule" always means the clock, never a POST.
GATED = ("update", "scheduled-refresh", "scheduled-report")
OPEN_KINDS = tuple(k for k in KINDS if k not in GATED)
MAX_LINE = 300
KEEP = 20                                     # finished jobs kept for /jobs/{id}
#: How long a job may hold the single slot before the next submit takes it away. Longer than
#: any honest run (a refresh and print is 1-3 minutes) and shorter than the runner's own stale
#: lock (`runner.LOCK_STALE_SECONDS`, 45 minutes), so a displaced job's `run.lock` is still its
#: own when the replacement job asks for it. A scheduled report may first spend up to
#: `runner.LOCK_WAIT_SECONDS` waiting for `run.lock` (a refresh on the same minute), and that
#: wait counts against this limit too; `run.lock`, not this timeout, is what prevents a double print.
JOB_TIMEOUT_SECONDS = 15 * 60
TIMED_OUT = "timed out after 15 minutes; started again"


@dataclass
class Job:
    id: int
    kind: str
    started_at: datetime
    params: dict = field(default_factory=dict)
    finished_at: datetime | None = None
    outcome: str | None = None                # OK | FAIL
    message: str = ""
    lines: list[str] = field(default_factory=list)
    pdf: Path | None = None

    @property
    def done(self) -> bool:
        return self.finished_at is not None

    @property
    def deadline(self) -> datetime:
        """When this job stops holding the one slot, whatever its thread is still doing."""
        return self.started_at + timedelta(seconds=JOB_TIMEOUT_SECONDS)

    @property
    def label(self) -> str:
        return LABELS[self.kind]


class Worker:
    def __init__(self, state, *, actions=None):
        self.state = state
        self.actions = actions or _actions
        self.current: Job | None = None
        self.last: Job | None = None
        self._jobs: dict[int, Job] = {}
        self._queue: queue.Queue[Job] = queue.Queue()
        self._cond = threading.Condition()
        self._next_id = 1
        self._threads: list[threading.Thread] = []

    # -- submitting ---------------------------------------------------------------------
    def submit(self, kind: str, **params) -> Job | None:
        """Start a job, or return None when one is already running (the route answers 409).

        A job past its deadline does not hold the slot: `refresh`, `preview`, `print` and
        `login` all drive Playwright, which can block forever, and one hung job must not wedge
        every button in the app until somebody kills the server -- which is exactly what the
        parent on Windows cannot do. The hung job is marked FAIL, its thread is left strictly
        alone (it may still be inside Playwright; killing a thread is not a thing Python does)
        and a fresh worker thread takes the next job.

        Two jobs are then in flight. While the abandoned one still holds `<home>/run.lock`, the
        new job's `refresh`, `preview` or `print` fails cleanly with "already running" -- the
        lock is never taken from a job that is merely slow, since `runner.Lock` only treats it
        as abandoned after `runner.LOCK_STALE_SECONDS` (45 minutes), well past this deadline.
        Past that point, though, the guard the lock offers expires: a third submit can take the
        lock away from the abandoned job's still-running second, the same way the second took it
        from the first. What no longer happens, once a lock changes hands, is the *displaced*
        holder deleting it: `runner.Lock.release()` unlinks the file only if it still carries the
        token that holder's own `acquire` wrote, so a late `release()` from job N can't destroy
        the lock job N+1 is actually using.
        """
        if kind not in KINDS:
            raise ValueError(f"unknown job kind {kind!r}; one of {', '.join(KINDS)}")
        stalled = False
        with self._cond:
            now = self.state.now()
            if self.current is not None and not self.current.done and self.current.kind == "update":
                return None                    # an installer is already on its way; nothing preempts it
            if self.current is not None:
                if now < self.current.deadline:
                    return None
                self._abandon(self.current, now)
                stalled = True
            job = Job(self._next_id, kind, now, params)
            self._next_id += 1
            self._jobs[job.id] = job
            for old in sorted(self._jobs)[:-KEEP]:
                del self._jobs[old]
            self.current = job
        if stalled and self._threads:
            self._start_thread()      # the old one may never come back; it becomes a spare
        self._queue.put(job)
        return job

    def _abandon(self, job: Job, now: datetime) -> None:
        """Take the slot away from a job past its deadline. Called holding `self._cond`."""
        job.outcome, job.message, job.finished_at = "FAIL", TIMED_OUT, now
        if not job.lines or job.lines[-1] != TIMED_OUT:
            job.lines.append(TIMED_OUT)
        self.current, self.last = None, job
        self._cond.notify_all()

    def get(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    # -- running --------------------------------------------------------------------------
    def start(self) -> None:
        if not self._threads:
            self._start_thread()

    def _start_thread(self) -> None:
        # A thread that has ended holds nothing; only a stuck one is worth remembering (#4).
        self._threads = [t for t in self._threads if t.is_alive()]
        t = threading.Thread(target=self._loop, name=f"fridgesheet-jobs-{len(self._threads) + 1}", daemon=True)
        self._threads.append(t)
        t.start()

    def _loop(self) -> None:
        while True:
            self._run(self._queue.get())

    def run_pending(self) -> None:
        """Tests: run the queued job on this thread."""
        try:
            job = self._queue.get_nowait()
        except queue.Empty:
            return
        self._run(job)

    def _log(self, job: Job):
        def log(line: str) -> None:
            with self._cond:
                job.lines.append(str(line)[:MAX_LINE])
                self._cond.notify_all()
        return log

    def _run(self, job: Job) -> None:
        if job.done:                              # displaced before this thread ever picked it up
            return
        log = self._log(job)
        settings, home = self.state.settings, self.state.home
        outcome, message = "FAIL", ""
        try:
            if job.kind == "refresh":
                r = self.actions.refresh(home=home, log=log, settings=settings)
                outcome, message = ("OK" if r.ok else "FAIL"), r.message
            elif job.kind == "preview":
                pdf = self.actions.preview(home=home, log=log, settings=settings,
                                           report_key=job.params.get("report", "open-work"),
                                           refresh=job.params.get("refresh_first", False))
                # Set outside the `done` guard below on purpose (#4): a preview displaced for
                # running long still built a real PDF, and its card may as well link to it.
                job.pdf = pdf
                outcome, message = ("OK", f"built {pdf}") if pdf else ("FAIL", "no sheet was built")
            elif job.kind == "print":
                rc = self.actions.print_now(home=home, log=log, settings=settings, date=job.params.get("date"),
                                            report_key=job.params.get("report", "open-work"),
                                            refresh=job.params.get("refresh_first", False))
                outcome, message = ("OK" if rc == 0 else "FAIL"), (job.lines[-1] if job.lines else "")
            elif job.kind == "reprint":
                # The stored PDF of one run, to the printer (#143): the route resolved the
                # file (`safe_pdf`) before submitting, so the card can link it either way.
                job.pdf = Path(job.params["pdf"])
                rc = self.actions.reprint(home=home, log=log, settings=settings, run_id=job.params["run_id"],
                                          pdf=job.params["pdf"], report_key=job.params.get("report", "open-work"))
                outcome, message = ("OK" if rc == 0 else "FAIL"), (job.lines[-1] if job.lines else "")
            elif job.kind == "scheduled-refresh":
                r = self.actions.refresh(home=home, log=log, settings=settings, trigger="schedule")
                outcome, message = ("OK" if r.ok else "FAIL"), r.message
            elif job.kind == "scheduled-report":
                rc = self.actions.scheduled_run(home=home, log=log, settings=settings,
                                                report_key=job.params["report"])
                outcome, message = ("OK" if rc == 0 else "FAIL"), (job.lines[-1] if job.lines else "")
            elif job.kind == "doctor":
                ok = self.actions.run_doctor(home=home, log=log, settings=settings)
                outcome, message = ("OK" if ok else "FAIL"), (job.lines[-1] if job.lines else "")
            elif job.kind == "login":
                r = self.actions.test_login(home=home, log=log, settings=settings)
                outcome, message = ("OK" if r.ok else "FAIL"), r.message
            elif job.kind == "update":
                ok = self.actions.self_update(home=home, log=log, settings=settings, state=self.state)
                outcome, message = ("OK" if ok else "FAIL"), (job.lines[-1] if job.lines else "")
        except Exception as e:  # noqa: BLE001  a job never takes the worker down
            message = f"{type(e).__name__}: {str(e)[:200]}"
            log(message)
        with self._cond:
            # A job displaced by `submit` already has its outcome, and the slot belongs to
            # whatever is running now: record the late lines, but change nothing else.
            if not job.done:
                job.outcome, job.message, job.finished_at = outcome, message, self.state.now()
                # Every kind's outcome line lands in the transcript, appended only when the
                # action's own logging did not already end on it (print and doctor build their
                # message from job.lines itself, so this is a no-op for them). Applying this to
                # every kind -- not just the ones whose message happens to differ today -- means
                # a job kind added later can never silently lose its outcome line from the log
                # pane just because nobody remembered to add it to an allowlist here.
                if not job.lines or job.lines[-1] != message:
                    job.lines.append(message)
            if self.current is job:
                self.current, self.last = None, job
            self._cond.notify_all()

    # -- streaming --------------------------------------------------------------------------
    def events(self, job_id: int) -> Iterator[str]:
        """SSE frames for one job: each line as it arrives, then `done`. Finished jobs replay.

        Never yields while holding `self._cond` -- a paused consumer would otherwise hold the
        worker's lock and stall every other job. Each pass takes the lock only long enough to
        wait for new lines and copy them out, then releases it before yielding.
        """
        job = self._jobs.get(job_id)
        if job is None:
            yield "event: done\ndata: unknown\n\n"
            return
        sent = 0
        while True:
            with self._cond:
                while sent >= len(job.lines) and not job.done:
                    self._cond.wait(timeout=1.0)
                batch = job.lines[sent:]
                finished = job.done
            for line in batch:
                yield f"data: {line}\n\n"
            sent += len(batch)
            if finished and sent >= len(job.lines):
                yield f"event: done\ndata: {job.outcome}\n\n"
                return
