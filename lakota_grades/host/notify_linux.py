from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger("lakota.host.notify")


def toast(title: str, body: str, run=subprocess.run) -> None:
    try:
        if not shutil.which("notify-send"):
            return
        run(["notify-send", "-a", "Lakota sheet", title, body], capture_output=True, text=True, timeout=20)
    except Exception as e:
        log.warning("notify-send failed: %s", e)
