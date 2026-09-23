"""There is no Linux installer to run. A Linux install is a git checkout."""
from __future__ import annotations

from .selfupdate import UpdateError

#: The one sentence for "this platform cannot self-update". Every entry point that must
#: refuse *before* doing any work -- `web/actions.py`'s `self_update`, the PIN-gated
#: `POST /settings/update` route, and `cli.py`'s `self-update` -- imports this rather than
#: writing a fourth variant of the same refusal; this module (where the dispatcher used to
#: land last) stays the one place that owns the wording.
NOT_WINDOWS = ("Fridge Sheet updates itself only on Windows. This is a source "
              "checkout: update it with `git pull && pip install -e .` and restart "
              "the service.")


def spawn_installer(installer, log_path, *, popen=None) -> None:
    raise UpdateError(NOT_WINDOWS)
