# fridgesheet/host/credentials_windows.py
"""Windows Credential Manager via the `keyring` library (Windows extra). Imported lazily so
the module loads, and tests can fake it, on any OS."""
from __future__ import annotations

import logging
import subprocess

from . import SERVICE

log = logging.getLogger("fridgesheet.host.credentials")


def _keyring():
    import keyring
    return keyring


def read_username(run=subprocess.run) -> str | None:
    return None      # config.toml [account].username is the username on Windows


def read_password(username: str, run=subprocess.run) -> str | None:
    if not username:
        return None
    try:
        return _keyring().get_password(SERVICE, username)
    except Exception as e:
        log.warning("credential store read failed for %r: %s", username, e)
        return None


def write(username: str, password: str, run=subprocess.run) -> None:
    try:
        _keyring().set_password(SERVICE, username, password)
    except Exception as e:
        raise RuntimeError(f"credential store write failed: {str(e)[:200]}") from e
