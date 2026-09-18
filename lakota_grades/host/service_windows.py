"""Logon task "Lakota Sheet - web": Task Scheduler starts the server when the user signs in
and restarts it if it dies. Registered by the installer, removed by the uninstaller."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from importlib import resources
from xml.sax.saxutils import escape

from . import CREATE_NO_WINDOW, ServiceError, ServiceInfo

NAME = "Lakota Sheet - web"
_NOT_FOUND = "cannot find the file"


def render_logon_task_xml(name: str, exe: str, args: str, workdir: str) -> str:
    template = resources.files("lakota_grades.host").joinpath("logon-task.xml").read_text(encoding="utf-8")
    return (template.replace("{description}", escape("Lakota Sheet: the browser app's server"))
                    .replace("{exe}", escape(exe)).replace("{args}", escape(args)).replace("{workdir}", escape(workdir)))


def _schtasks(cmd: list[str], run) -> subprocess.CompletedProcess:
    return run(["schtasks", *cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=60)


def install(exe: str, args: str, workdir: str, run=subprocess.run) -> None:
    xml = render_logon_task_xml(NAME, exe, args, workdir)
    fd, path = tempfile.mkstemp(prefix="lakota-web-", suffix=".xml")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(xml.encode("utf-16"))
        p = _schtasks(["/Create", "/TN", NAME, "/XML", path, "/F"], run)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if p.returncode != 0:
        raise ServiceError(f"schtasks /Create failed: {(p.stderr or p.stdout or '').strip()[:300]}")
    _schtasks(["/Run", "/TN", NAME], run)                       # start it now; the trigger covers the next logon


def remove(run=subprocess.run) -> None:
    _schtasks(["/End", "/TN", NAME], run)                       # stop a running server; absent is fine
    p = _schtasks(["/Delete", "/TN", NAME, "/F"], run)
    if p.returncode != 0 and _NOT_FOUND not in (p.stderr or ""):
        raise ServiceError(f"schtasks /Delete failed: {(p.stderr or p.stdout or '').strip()[:300]}")


def describe(run=subprocess.run) -> ServiceInfo:
    p = _schtasks(["/Query", "/TN", NAME, "/FO", "LIST", "/V"], run)
    if p.returncode != 0:
        return ServiceInfo("task-scheduler", False, False, "not installed")
    fields = {}
    for line in (p.stdout or "").splitlines():
        m = re.match(r"^([A-Za-z ]+):\s*(.*?)\s*$", line)
        if m:
            fields.setdefault(m.group(1).strip(), m.group(2))
    status = fields.get("Status", "")
    return ServiceInfo("task-scheduler", True, status.lower() == "running", f"logon task {status or 'installed'}")
