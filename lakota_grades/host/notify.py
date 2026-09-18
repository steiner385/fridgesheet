# lakota_grades/host/notify.py
"""A desktop notification at the end of a scheduled run. Best effort: never raises."""
from __future__ import annotations

from . import IS_WINDOWS

if IS_WINDOWS:
    from . import notify_windows as _impl
else:
    from . import notify_linux as _impl

toast = _impl.toast
