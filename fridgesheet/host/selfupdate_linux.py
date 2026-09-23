"""There is no Linux installer to run. A Linux install is a git checkout."""
from __future__ import annotations

from .selfupdate import UpdateError


def spawn_installer(installer, log_path, *, popen=None) -> None:
    raise UpdateError("Fridge Sheet updates itself only on Windows. This is a source "
                      "checkout: update it with `git pull && pip install -e .` and restart "
                      "the service.")
