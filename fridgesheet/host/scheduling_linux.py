"""Linux: remove the systemd user units earlier versions of this app wrote.

Only a unit whose first line is `MARKER` was written by this app; anything else -- the
household's hand-written timers, the web server's own unit -- is never touched.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import SchedulingError
from .service_linux import UNIT_FILE as _WEB_UNIT

#: The first line of every unit an earlier version wrote.
MARKER = "# Written by Fridge Sheet. Edits here are lost when the schedule is saved.\n"
_NO_SUCH_UNIT = ("does not exist", "not loaded")


def _unit_dir(d: Path | None = None) -> Path:
    return d or Path.home() / ".config" / "systemd" / "user"


def _ours(path: Path) -> bool:
    try:
        return path.name != _WEB_UNIT and path.read_text(encoding="utf-8").startswith(MARKER)
    except (OSError, UnicodeDecodeError):
        return False


def leftovers(unit_dir: Path | None = None) -> list[str]:
    d = _unit_dir(unit_dir)
    return sorted(p.name for p in d.glob("fridgesheet-*.timer") if _ours(p))


def _systemctl(args: list[str], run) -> subprocess.CompletedProcess:
    return run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=60)


def remove_timer(name: str, run=subprocess.run, unit_dir: Path | None = None) -> None:
    d = _unit_dir(unit_dir)
    timer, service = d / name, d / name.replace(".timer", ".service")
    if not _ours(timer):
        raise SchedulingError(f"{name} was not written by this app; refusing to touch it")
    try:
        p = _systemctl(["disable", "--now", name], run)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise SchedulingError(f"systemctl --user disable --now {name}: {e}") from None
    text = f"{p.stderr or ''}\n{p.stdout or ''}".lower()
    if p.returncode != 0 and not any(s in text for s in _NO_SUCH_UNIT):
        raise SchedulingError((p.stderr or p.stdout or "").strip()[:300])
    timer.unlink(missing_ok=True)
    if _ours(service):
        service.unlink(missing_ok=True)
    try:
        _systemctl(["daemon-reload"], run)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def command_for(name: str) -> str:
    return f"systemctl --user disable --now {name} && rm ~/.config/systemd/user/{name}"
