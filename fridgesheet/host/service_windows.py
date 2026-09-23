"""Logon task "Fridge Sheet - web": Task Scheduler starts the server when the user signs in
and restarts it if it dies. Registered by the installer, removed by the uninstaller."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from importlib import resources
from xml.sax.saxutils import escape

from . import CREATE_NO_WINDOW, ServiceError, ServiceInfo
from . import current_user as _current_user

NAME = "Fridge Sheet - web"
_NOT_FOUND = "cannot find the file"
_WHITESPACE = re.compile(r"\s+")


def _normalize_command(command: str) -> str:
    """Make two spellings of "the same command" comparable. `schtasks /Query`'s `Task To
    Run` is one string, quoted (or not) however Task Scheduler feels like it that day, while
    we hold exe and args separately and join them plainly -- so a task installed by an
    ordinary `/Create` can read back with different quoting than the one this install would
    pass, on the very same exe. Windows paths are also case-insensitive.

    Strip quotes, collapse whitespace, casefold. Deliberately not a real command-line
    parser: just enough to tell "the task we would have created" from "a task pointing
    somewhere else" (graphy, 2026-09-23) without being so strict that a harmless quoting
    difference re-introduces the bug this exists to fix.
    """
    return _WHITESPACE.sub(" ", (command or "").replace('"', "").replace("'", "")).strip().casefold()


def render_logon_task_xml(name: str, exe: str, args: str, workdir: str) -> str:
    template = resources.files("fridgesheet.host").joinpath("logon-task.xml").read_text(encoding="utf-8")
    return (template.replace("{description}", escape("Fridge Sheet: the browser app's server"))
                    .replace("{exe}", escape(exe)).replace("{args}", escape(args)).replace("{workdir}", escape(workdir)))


def _schtasks(cmd: list[str], run) -> subprocess.CompletedProcess:
    return run(["schtasks", *cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=60)


def _fallback_note_or_raise(exe: str, args: str, create_err: str, run) -> str:
    """`install()`'s `/Create` just failed. Decide whether the task Task Scheduler already
    has is safe to just start, or whether this must still be a hard error.

    graphy, 2026-09-23, a real 0.4.1 -> 0.5.0 upgrade: the logon task was registered by an
    administrator while the app runs as `svc_fridgesheet`, a standard, non-admin account. That
    account cannot overwrite a task it does not own -- `schtasks /Create ... /F` failed with
    "ERROR: Access is denied." -- so `install()` raised, the installer's `[Run]` entry
    (`FridgeSheet.exe service install`) exited 1, and because Inno Setup does not check
    `[Run]` exit codes the installer reported success while `/health` stayed unreachable and
    `Get-Process FridgeSheet` returned nothing, until a human ran `schtasks /Run` by hand.
    The in-app self-update feature spawns that same installer and depends on this same
    `install()` to bring the server back, so this defect meant every self-update left the
    household's app down.

    A task merely being *present* is not enough to fall back to, though: it must be the one
    this install would have created -- same command, same account -- or turning a broken
    task into a silent success would be worse than the bug above. Deliberately not gated on
    *why* `/Create` failed (see the "unrelated reason" test in
    `tests/test_host_service_windows.py`): schtasks' stderr text is not a stable contract
    across locales and Windows versions, so the exe/account match is what has to carry the
    safety here, not the wording of the error.
    """
    info = describe(run=run)
    if not info.installed:
        raise ServiceError(f"schtasks /Create failed: {create_err} (and no existing "
                            f"'{NAME}' task to fall back to)")
    wanted = _normalize_command(f"{exe} {args}")
    have = _normalize_command(info.command)
    if have != wanted:
        raise ServiceError(f"schtasks /Create failed: {create_err} (existing '{NAME}' task "
                            f"runs {info.command!r}, not {exe} {args}, so it is not safe to just start)")
    me = _current_user()
    if not me or info.owner.strip().casefold() != me.casefold():
        # `not me` (not `me and ...`) is deliberate, same as `cli.cmd_self_update`'s check:
        # `getpass.getuser()` can fail (no password-database entry, some container/service
        # contexts), and when we cannot confirm who we are, that is a reason to stop, not to
        # assume a match -- so the message says that plainly rather than printing `''`.
        who = f"we run as {me!r}" if me else "this shell's account could not be determined"
        raise ServiceError(f"schtasks /Create failed: {create_err} (existing '{NAME}' task "
                            f"runs as {info.owner!r}; {who}, so it is not safe to just start)")
    return (f"schtasks /Create failed ({create_err}); the existing '{NAME}' task already "
            f"runs {exe} {args} as {me!r}, so it was started instead of being re-registered")


def install(exe: str, args: str, workdir: str, run=subprocess.run) -> str:
    """Register the logon task and start it. Returns "" when `/Create` succeeded (today's
    path, unchanged); returns a non-empty note when `/Create` failed but the task already
    registered turned out to be the one this install would have created, so `/Run` alone
    was enough -- see `_fallback_note_or_raise` for why that fallback exists and when it is
    safe."""
    xml = render_logon_task_xml(NAME, exe, args, workdir)
    fd, path = tempfile.mkstemp(prefix="fridgesheet-web-", suffix=".xml")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(xml.encode("utf-16"))
        p = _schtasks(["/Create", "/TN", NAME, "/XML", path, "/F"], run)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    note = ""
    if p.returncode != 0:
        create_err = (p.stderr or p.stdout or "").strip()[:300]
        note = _fallback_note_or_raise(exe, args, create_err, run)
    r = _schtasks(["/Run", "/TN", NAME], run)                   # start it now; the trigger covers the next logon
    if note and r.returncode != 0:
        # Deliberately asymmetric, and only on the fallback path: after an ordinary
        # successful /Create, an /Run failure here is tolerable -- the task itself is
        # correct and its own LogonTrigger starts it at the next sign-in regardless, so
        # today's happy path stays exactly as forgiving as before. On the fallback path
        # /Run is not a courtesy start, it is the *entire* remedy for a /Create that could
        # not touch the task at all (graphy, 2026-09-23). If /Run also fails there, nothing
        # brings the server back, and returning the fallback note anyway would report
        # success over the exact same shape of bug this fix exists for, just one step
        # later. Do not "simplify" this into one rule for both paths.
        raise ServiceError(f"existing '{NAME}' task matched, but schtasks /Run failed: "
                            f"{(r.stderr or r.stdout or '').strip()[:300]}")
    return note


def remove(run=subprocess.run) -> None:
    _schtasks(["/End", "/TN", NAME], run)                       # stop a running server; absent is fine
    p = _schtasks(["/Delete", "/TN", NAME, "/F"], run)
    if p.returncode != 0 and _NOT_FOUND not in (p.stderr or ""):
        raise ServiceError(f"schtasks /Delete failed: {(p.stderr or p.stdout or '').strip()[:300]}")


def describe(run=subprocess.run) -> ServiceInfo:
    # `schtasks /Query /V`'s field labels -- "Status", "Run As User", "Task To Run" -- are
    # English, and schtasks localizes them on a non-English Windows. This is NOT locale-proof:
    # on such a machine every field below comes back "", `owner`/`command` are "" too, and
    # `_fallback_note_or_raise`'s command/account comparison then mismatches an empty string
    # against a real one and raises rather than falling through. That is a fail-CLOSED
    # failure -- a loud ServiceError, not a silent wrong start -- so it is not the graphy bug
    # again, but it does mean the fallback simply never engages on a localized install; it is
    # not a general fix for that case.
    p = _schtasks(["/Query", "/TN", NAME, "/FO", "LIST", "/V"], run)
    if p.returncode != 0:
        return ServiceInfo("task-scheduler", False, False, "not installed")
    fields = {}
    for line in (p.stdout or "").splitlines():
        m = re.match(r"^([A-Za-z ]+):\s*(.*?)\s*$", line)
        if m:
            fields.setdefault(m.group(1).strip(), m.group(2))
    status = fields.get("Status", "")
    return ServiceInfo("task-scheduler", True, status.lower() == "running",
                       f"logon task {status or 'installed'}", owner=fields.get("Run As User", ""),
                       command=fields.get("Task To Run", ""))
