# fridgesheet/host/credentials.py
"""The OS password store: where `set-credentials` puts the OneLogin password.

Linux: freedesktop Secret Service through `secret-tool` (GNOME keyring), exactly as the
original config.py did, so an existing entry keeps working. Windows: Credential Manager
through the `keyring` library. Nothing here logs or prints a secret.
"""
from __future__ import annotations

from . import IS_WINDOWS, keyring_service  # noqa: F401  re-exported

if IS_WINDOWS:
    from . import credentials_windows as _impl
else:
    from . import credentials_linux as _impl

read_username = _impl.read_username
read_password = _impl.read_password
write = _impl.write


def __getattr__(name: str):
    # `credentials.SERVICE`, as before -- but read from the environment when asked, not bound
    # at import, so a `.env` loaded later still counts (`host.keyring_service`, #148).
    if name == "SERVICE":
        return keyring_service()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
