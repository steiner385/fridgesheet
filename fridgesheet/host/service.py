"""The always-on web server (spec section 10): a systemd user unit on Linux, a logon task on
Windows. Same shape as the other adapters: the platform picks an implementation at import,
every implementation takes `run=subprocess.run`, and the CLI and installer call these three."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path, PureWindowsPath

from . import IS_WINDOWS
from . import ServiceError, ServiceInfo  # noqa: F401  re-exported

SERVICE_NAME = "Fridge Sheet - web"
UNIT = "fridgesheet-web"


def command_for() -> tuple[str, str, str]:
    """(exe, args, workdir) that runs the server in the foreground from this installation.
    The frozen exe is always the Windows build (see web/__main__.py), so its parent
    directory is computed with PureWindowsPath even when tests run this on Linux."""
    if getattr(sys, "frozen", False):
        return sys.executable, "web --no-browser", str(PureWindowsPath(sys.executable).parent)
    return sys.executable, "-m fridgesheet.cli web --no-browser", str(Path.cwd())


if IS_WINDOWS:
    from . import service_windows as _impl
else:
    from . import service_linux as _impl


def install_service(run=subprocess.run) -> str:
    exe, args, workdir = command_for()
    note = _impl.install(exe, args, workdir, run=run)
    # `service_windows.install` returns "" on today's ordinary path and a non-empty note when
    # `/Create` was refused but an already-registered, matching task was started instead of
    # rewritten (graphy, 2026-09-23) -- fold it in so `cmd_service`'s existing
    # `print(f"Installed ...: {service.install_service()}")` says which one happened, without
    # `cmd_service` itself needing to know about the fallback. `service_linux.install` returns
    # None, which is falsy here just the same.
    return f"{exe} {args} ({note})" if note else f"{exe} {args}"


def remove_service(run=subprocess.run) -> None:
    _impl.remove(run=run)


def describe_service(run=subprocess.run) -> ServiceInfo:
    return _impl.describe(run=run)
