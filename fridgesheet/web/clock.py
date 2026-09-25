"""The server's own clock: fires every schedule in `config.toml` (spec 2026-09-25).

Once a minute: read the settings fresh, ask `schedule_plan` which schedule is due, submit it
to the one jobs worker, and record the slot in `schedule_fires` once the worker took it. A
busy worker takes nothing and nothing is recorded, so the next minute tries again. At most
one job per tick, refresh first: the worker runs one at a time anyway, and a refresh due in
the same minute as a print should finish before the print reads the snapshot.

This replaced the OS scheduler. Task Scheduler ran every task "only when the user is logged
on", and on the household's kiosk the app's account never is -- not one schedule ever fired.
The server runs as the right account and is always up; it is the one place that can.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

from .. import host, reports as registry, schedule_plan
from . import db
from .stores import fires

log = logging.getLogger("fridgesheet.web.clock")

TICK_SECONDS = 60
STALE_AFTER = timedelta(minutes=3)
PAUSED = "Schedules are paused: the scheduler inside Fridge Sheet has stopped. Restart Fridge Sheet."

_current: "Clock | None" = None


def current() -> "Clock | None":
    """The clock running in this process, None outside the server (the CLI, doctor from a
    terminal)."""
    return _current


def configured(home: Path, settings=None) -> tuple[list[schedule_plan.Schedule], dict[str, str]]:
    """Every enabled schedule for `home`, and a problem per one that cannot run. The one place
    that reads the report list for the planner, so the page, doctor and the clock agree."""
    if settings is None:
        from .actions import _settings_for
        settings = _settings_for(home)
    reports = [(r.key, r.title, r.default_time) for r in registry.available(home)]
    return schedule_plan.schedules_from(settings, reports)


class Clock:
    def __init__(self, state, *, submit=None):
        self.state = state
        self._submit = submit or (lambda kind, **p: state.jobs.submit(kind, **p))
        self.last_tick: datetime | None = None
        self.problems: dict[str, str] = {}
        self._thread: threading.Thread | None = None

    def tick(self, now: datetime) -> str | None:
        schedules, self.problems = configured(self.state.home)
        conn = db.open_db(self.state.home)
        try:
            fired = fires.all(conn)
            submitted, tried = None, False
            for s in schedules:
                d = schedule_plan.due(s, now, fired.get(s.key))
                if d is None:
                    continue
                if not d.fire:
                    fires.record(conn, s.key, d.slot)          # first sight: this slot is past
                    continue
                if tried:
                    continue                                   # one job per tick
                tried = True
                job = (self._submit("scheduled-refresh") if s.key == host.DATA_REFRESH_KEY
                       else self._submit("scheduled-report", report=s.key))
                if job is None:
                    continue                                   # busy: the next tick tries again
                try:
                    fires.record(conn, s.key, d.slot)
                except Exception as e:                         # noqa: BLE001  the job is already running
                    log.warning("could not record that %s fired at %s: %s", s.key, d.slot, e)
                submitted = s.key
        finally:
            conn.close()
        self.last_tick = now
        return submitted

    def safe_tick(self, now: datetime) -> None:
        """`tick`, never raising: one bad minute is a log line, not a dead clock. A failed tick
        does not stamp the heartbeat, so a clock failing every minute shows as paused."""
        try:
            self.tick(now)
        except Exception:                                      # noqa: BLE001
            log.exception("clock tick failed")

    def stale(self, now: datetime) -> bool:
        return self.last_tick is None or now - self.last_tick > STALE_AFTER

    def start(self) -> None:
        global _current
        _current = self
        stop = threading.Event()

        def loop() -> None:
            while not stop.is_set():
                self.safe_tick(self.state.now())
                stop.wait(TICK_SECONDS)

        self._thread = threading.Thread(target=loop, name="fridgesheet-clock", daemon=True)
        self._thread.start()


def remove_leftovers(state, remove=None) -> None:
    """Remove what earlier versions registered with the OS; keep what could not be removed for
    the Schedules page. Never raises: a server that cannot clean up still serves."""
    if remove is None:
        from ..host.scheduling import remove_os_leftovers as remove
    try:
        got = remove()
    except Exception as e:                                 # noqa: BLE001
        log.warning("could not remove old scheduled tasks: %s", e)
        return
    for name in got.removed:
        log.info("removed %s, which an earlier version registered", name)
    state.extra["leftovers"] = got.failed


def start_background(state) -> "Clock":
    """What the real server starts beside the worker: the clock, and a one-off cleanup of the
    OS tasks earlier versions registered -- on its own thread, so the first page never waits
    for `schtasks`. `server.run` calls this once; `create_app` never does, so no test app ever
    runs a background clock or touches the OS scheduler."""
    c = Clock(state)
    state.extra["clock"] = c
    c.start()
    threading.Thread(target=remove_leftovers, args=(state,), name="fridgesheet-leftovers", daemon=True).start()
    return c
