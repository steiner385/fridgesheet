# fridgesheet/host/credentials_linux.py
from __future__ import annotations

import logging
import subprocess

from . import keyring_service

log = logging.getLogger("fridgesheet.host.credentials")
LABEL = "Fridge Sheet OneLogin"


def _lookup(key: str, run) -> str | None:
    """None when unavailable so the caller falls through. A locked keyring makes secret-tool
    block on a GUI prompt, which would hang a timer forever -- hence the timeout."""
    try:
        p = run(["secret-tool", "lookup", "service", keyring_service(), "key", key], capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        log.warning("secret-tool timed out reading %r; is the login keyring locked?", key)
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    return p.stdout.rstrip("\n")


def read_username(run=subprocess.run) -> str | None:
    return _lookup("username", run)


def read_password(username: str, run=subprocess.run) -> str | None:
    return _lookup("password", run)      # the Secret Service entry is keyed by attribute, not by user


def _store(key: str, value: str, run) -> None:
    """`value` goes on stdin, never argv, so it cannot leak through the process table."""
    p = run(["secret-tool", "store", "--label", LABEL, "service", keyring_service(), "key", key],
            input=value, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"`secret-tool store` failed for {key!r}: {(p.stderr or '').strip()[:200]}")


def write(username: str, password: str, run=subprocess.run) -> None:
    _store("username", username, run)
    _store("password", password, run)
