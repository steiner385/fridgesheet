"""Windows toast via PowerShell and the WinRT ToastNotificationManager. No third-party
toast library. The script is passed base64 UTF-16LE (-EncodedCommand) so titles and
bodies never touch shell quoting; inside the XML they are entity-escaped."""
from __future__ import annotations

import base64
import logging
import subprocess
from xml.sax.saxutils import escape

from . import CREATE_NO_WINDOW

log = logging.getLogger("fridgesheet.host.notify")

#: Must match the AppUserModelID Inno Setup puts on the Start menu shortcut (Plan 3).
APP_ID = "Cairnea.FridgeSheet"

_SCRIPT = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>{title}</text><text>{body}</text></binding></visual></toast>')
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show($toast)
"""


def _xml_text(s: str) -> str:
    # escape() handles & < >; quotes are escaped too because the XML sits inside a PS single-quoted string
    return escape(s, {'"': "&quot;", "'": "&apos;"})


def toast(title: str, body: str, run=subprocess.run) -> None:
    try:
        script = _SCRIPT.format(title=_xml_text(title), body=_xml_text(body), app_id=APP_ID)
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded]
        run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=20)
    except Exception as e:
        log.warning("toast failed: %s", e)
