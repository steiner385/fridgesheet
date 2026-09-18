"""The one-time move from the old name (lakota-grades / Lakota Sheet) to Fridge Sheet.

Everything an installed copy of the old app left behind is picked up here, once, without
anyone having to know it happened: the data directory, the database file inside it, the
password in the OS credential store, and the `LAKOTA_*` environment variables a parent's
own units or .env may still set. Each step is idempotent and does nothing when there is
nothing old to find, so this module can run on every start.

Nothing here deletes anything of the old app's. The old keyring entry stays (a second,
older install may still read it) and on Linux the old data directory becomes a symlink to
the new one, because hand-written systemd units and archive paths name it explicitly.

See docs/superpowers/specs/2026-09-18-fridgesheet-rebrand-design.md, section 3.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger("fridgesheet.migrate")

OLD_PREFIX = "LAKOTA_"
NEW_PREFIX = "FRIDGESHEET_"
#: Old names whose new spelling is not a plain prefix swap.
RENAMED = {"LAKOTA_GRADES_HOME": "FRIDGESHEET_HOME", "LAKOTA_GRADES_BIN": "FRIDGESHEET_BIN"}
OLD_SERVICE = "lakota-grades"           # keyring service; the new one is host.SERVICE
OLD_DB_NAME = "lakota.db"
OLD_DIR_LINUX = ".lakota-grades"
OLD_DIR_WINDOWS = "lakota-grades"


def alias_legacy_env(environ=None) -> list[str]:
    """For every `LAKOTA_<X>` set, also set `FRIDGESHEET_<X>` unless that is already set.

    The new name always wins when both are present. Returns the old names that were
    honoured, for `doctor` to list. Safe to call repeatedly.
    """
    env = os.environ if environ is None else environ
    honoured: list[str] = []
    for old in sorted(k for k in env if k.startswith(OLD_PREFIX)):
        new = RENAMED.get(old) or NEW_PREFIX + old[len(OLD_PREFIX):]
        if new not in env:
            env[new] = env[old]
        honoured.append(old)
    return honoured


def legacy_home(*, is_windows: bool, environ=None) -> Path | None:
    """Where the old app kept its data on this OS, or None when a home override is in force
    (an override names one directory for both the old and the new app; nothing to move)."""
    env = os.environ if environ is None else environ
    if env.get("FRIDGESHEET_HOME") or env.get("LAKOTA_GRADES_HOME"):
        return None
    if is_windows:
        return Path(env.get("LOCALAPPDATA") or Path.home()) / OLD_DIR_WINDOWS
    return Path.home() / OLD_DIR_LINUX


def migrate_home(new: Path, old: Path | None, *, link_old: bool) -> str | None:
    """Move the old data directory to the new path, once.

    Only when `new` does not exist and `old` is a real directory (not already a link).
    With `link_old` (Linux), a symlink is left at the old path so explicit references to
    it -- `Environment=LAKOTA_ENV_FILE=%h/.lakota-grades/.env` in a hand-written unit --
    keep resolving. Returns a one-line description of what happened, or None for nothing.
    """
    if old is None or old == new:
        return None
    if new.exists() or new.is_symlink():
        return None
    if not old.is_dir() or old.is_symlink():
        return None
    new.parent.mkdir(parents=True, exist_ok=True)
    os.replace(old, new)
    what = f"moved {old} to {new}"
    if link_old:
        try:
            old.symlink_to(new, target_is_directory=True)
            what += f" and left a link at {old}"
        except OSError as e:  # a filesystem without symlinks: the move still stands
            what += f" (could not leave a link at {old}: {e})"
    log.info(what)
    return what


def migrate_db(home: Path, new_name: str) -> str | None:
    """Rename `lakota.db` (and its -wal/-shm sidecars) to the new file name, once, when the
    new file is not there yet. WAL sidecars must travel with the main file or SQLite would
    see a database whose last transactions are in a file it no longer looks for."""
    old = home / OLD_DB_NAME
    new = home / new_name
    if new.exists() or not old.is_file():
        return None
    for suffix in ("-wal", "-shm"):
        side = home / (OLD_DB_NAME + suffix)
        if side.exists():
            os.replace(side, home / (new_name + suffix))
    os.replace(old, new)
    log.info("renamed %s to %s", old, new)
    return f"renamed {old.name} to {new.name}"


def read_legacy_password(username: str, *, is_windows: bool, run=subprocess.run) -> str | None:
    """The password the old app stored, if any. Never raises; None when there is none or the
    store cannot be reached (a locked keyring must not hang an unattended start)."""
    if is_windows:
        if not username:
            return None
        try:
            import keyring
            return keyring.get_password(OLD_SERVICE, username)
        except Exception as e:  # noqa: BLE001
            log.warning("could not read the old credential entry: %s", e)
            return None
    try:
        p = run(["secret-tool", "lookup", "service", OLD_SERVICE, "key", "password"],
                capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    return p.stdout.rstrip("\n")


def read_legacy_username(*, is_windows: bool, run=subprocess.run) -> str | None:
    """Linux only: the old Secret Service entry also carried the username."""
    if is_windows:
        return None
    try:
        p = run(["secret-tool", "lookup", "service", OLD_SERVICE, "key", "username"],
                capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    return p.stdout.rstrip("\n")


def legacy_in_use(*, environ=None, home: Path | None = None, legacy_home_path: Path | None = None) -> list[str]:
    """What still goes by the old name on this machine, one short line each, for `doctor`.
    Empty when the machine is fully on the new name."""
    env = os.environ if environ is None else environ
    out: list[str] = []
    old_vars = sorted(k for k in env if k.startswith(OLD_PREFIX))
    if old_vars:
        out.append("environment: " + ", ".join(old_vars) + " (use FRIDGESHEET_* instead)")
    if env.get("FRIDGESHEET_LEGACY_COMMAND"):
        out.append("command: started as `lakota-grades` (use `fridgesheet`)")
    if legacy_home_path is not None and legacy_home_path.is_symlink():
        out.append(f"data directory: {legacy_home_path} is a link to {home} (paths in your own units or shortcuts still name it)")
    return out
