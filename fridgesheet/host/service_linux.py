"""systemd user unit `fridgesheet-web.service`, written and enabled by the app. The household's
hand-written units keep their own names; this one is new and only ever managed here."""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import ServiceError, ServiceInfo, systemd_quote

UNIT_FILE = "fridgesheet-web.service"
#: What systemctl says when the unit is simply not there ("Failed to disable unit: Unit file
#: fridgesheet-web.service does not exist."); anything else is a real failure. Deliberately narrow,
#: as `service_windows.remove`'s "cannot find the file" is: a user manager that is not running
#: answers "Failed to connect to bus: No such file or directory", and a remove that printed
#: "Removed ..." over that left the unit enabled to start the server at the next logon.
_NO_SUCH_UNIT = ("does not exist", "not loaded")


def unit_path(unit_dir: Path | None = None) -> Path:
    return (unit_dir or Path.home() / ".config" / "systemd" / "user") / UNIT_FILE


def unit_text(exe: str, args: str, workdir: str) -> str:
    # No After=network-online.target: that target doesn't exist in a user manager's unit
    # graph, so it would only document an ordering, not create one. Restart=on-failure with
    # RestartSec=5 already covers a server that starts before the network is up.
    return (
        "[Unit]\nDescription=Fridge Sheet web app\n\n"
        f"[Service]\nExecStart={systemd_quote(exe)} {args}\nWorkingDirectory={workdir}\nRestart=on-failure\nRestartSec=5\n\n"
        "[Install]\nWantedBy=default.target\n"
    )


def _systemctl(args: list[str], run) -> subprocess.CompletedProcess:
    return run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=60)


def install(exe: str, args: str, workdir: str, run=subprocess.run, unit_dir: Path | None = None) -> None:
    path = unit_path(unit_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()          # an upgrade re-writes a unit that already works; keep it
    path.write_text(unit_text(exe, args, workdir), encoding="utf-8")
    for cmd in (["daemon-reload"], ["enable", "--now", UNIT_FILE]):
        p = _systemctl(cmd, run)
        if p.returncode != 0:
            if fresh:                  # a unit this attempt wrote and could not enable (#7)
                path.unlink(missing_ok=True)
            raise ServiceError(f"systemctl --user {' '.join(cmd)} failed: {(p.stderr or p.stdout or '').strip()[:300]}")


def remove(run=subprocess.run, unit_dir: Path | None = None) -> None:
    """Stop, disable and delete the unit. Idempotent for a unit that is not there; anything
    else systemctl refuses is raised, so `service remove` never reports a removal it did not do."""
    p = _systemctl(["disable", "--now", UNIT_FILE], run)
    if p.returncode != 0:
        text = f"{p.stderr or ''}\n{p.stdout or ''}".lower()
        if not any(s in text for s in _NO_SUCH_UNIT):         # absent is fine; nothing else is
            raise ServiceError(f"systemctl --user disable --now {UNIT_FILE} failed: "
                               f"{(p.stderr or p.stdout or '').strip()[:300]}")
    unit_path(unit_dir).unlink(missing_ok=True)
    _systemctl(["daemon-reload"], run)


def describe(run=subprocess.run) -> ServiceInfo:
    enabled = _systemctl(["is-enabled", UNIT_FILE], run)
    active = _systemctl(["is-active", UNIT_FILE], run)
    installed = enabled.returncode == 0
    is_active = (active.stdout or "").strip() == "active"
    detail = f"{(enabled.stdout or 'not installed').strip()}, {(active.stdout or 'inactive').strip()}"
    return ServiceInfo("systemd", installed, is_active, detail)
