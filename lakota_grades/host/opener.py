"""Open a file in the desktop's viewer, detached from us so it outlives a terminal window."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import lakota_grades.host as host   # attribute lookup at call time, so tests can flip IS_WINDOWS


def _startfile(path: str) -> None:
    os.startfile(path)  # type: ignore[attr-defined]  # Windows only


def open_file(path: Path, popen=None) -> None:
    """`popen` defaults to `None`, resolved to `subprocess.Popen` here at the point of use
    rather than as `popen=subprocess.Popen` in the signature. A default argument is bound
    once, at `def` time (i.e. at import) -- the same trap `run=subprocess.run` falls into
    across `lakota_grades/host/*`, and the reason a test guard that patches the
    `subprocess.Popen` *attribute* (see `tests/conftest.py::_no_real_scheduler`) would never
    have reached a `popen=subprocess.Popen` default captured before it ran. Resolving here
    means every call that does not inject its own `popen=` goes through whatever
    `subprocess.Popen` currently is, so a patched attribute is always seen. Tests keep the
    same injection seam by passing `popen=` explicitly, exactly as before."""
    if host.IS_WINDOWS:
        _startfile(str(path))
        return
    popen = popen or subprocess.Popen
    viewer = shutil.which("evince") or shutil.which("xdg-open")
    if not viewer:
        raise RuntimeError("no PDF viewer found (evince or xdg-open)")
    popen([viewer, path.as_posix()], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def open_text(path: Path, popen=None) -> None:
    """Open a plain-text settings file in an editor. Windows has no association for .toml,
    so Notepad is named explicitly; Linux goes through the desktop's opener.

    `popen` is resolved to `subprocess.Popen` here rather than captured as a `def`-time
    default -- see `open_file`'s docstring for why that distinction matters for a test guard
    that patches `subprocess.Popen` after import."""
    popen = popen or subprocess.Popen
    if host.IS_WINDOWS:
        popen(["notepad.exe", str(path)], creationflags=host.CREATE_NO_WINDOW)
        return
    viewer = shutil.which("xdg-open")
    if not viewer:
        raise RuntimeError("no text editor found (xdg-open)")
    popen([viewer, path.as_posix()], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
