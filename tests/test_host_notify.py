# tests/test_host_notify.py
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from fridgesheet import host
from fridgesheet.host import notify, notify_linux, notify_windows, opener


def _rec():
    seen = []

    def run(cmd, **kw):
        seen.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return seen, run


def test_linux_uses_notify_send_when_present(monkeypatch):
    seen, run = _rec()
    monkeypatch.setattr(notify_linux.shutil, "which", lambda n: "/usr/bin/notify-send")
    notify_linux.toast("Open Work Sheet", "Printed 2 pages", run=run)
    assert seen[0][0] == ["notify-send", "-a", "Fridge Sheet", "Open Work Sheet", "Printed 2 pages"]
    monkeypatch.setattr(notify_linux.shutil, "which", lambda n: None)
    notify_linux.toast("x", "y", run=run)
    assert len(seen) == 1


def test_windows_runs_an_encoded_powershell_toast_with_no_window():
    seen, run = _rec()
    notify_windows.toast("Open Work Sheet", 'Printed <2> pages & "more"', run=run)
    cmd, kw = seen[0]
    assert cmd[0] == "powershell" and "-NoProfile" in cmd and "-NonInteractive" in cmd
    script = base64.b64decode(cmd[cmd.index("-EncodedCommand") + 1]).decode("utf-16-le")
    assert notify_windows.APP_ID in script
    assert "Open Work Sheet" in script and "Printed &lt;2&gt; pages &amp; &quot;more&quot;" in script
    assert kw["creationflags"] == host.CREATE_NO_WINDOW and kw["timeout"] == 20


def test_toast_never_raises(monkeypatch):
    def boom(cmd, **kw):
        raise OSError("no powershell")
    notify_windows.toast("a", "b", run=boom)
    notify_linux.toast("a", "b", run=boom)
    assert hasattr(notify, "toast")


def test_windows_toast_escapes_apostrophes_so_the_powershell_literal_cannot_break():
    seen, run = _rec()
    notify_windows.toast("O'Brien's sheet", "it's done; ') ; Remove-Item x", run=run)
    cmd, _ = seen[0]
    script = base64.b64decode(cmd[cmd.index("-EncodedCommand") + 1]).decode("utf-16-le")
    assert "O&apos;Brien&apos;s sheet" in script and "it&apos;s done; &apos;) ; Remove-Item x" in script
    # The only single quotes left in the script are the template's own delimiters:
    # LoadXml('...') and CreateToastNotifier('...') — two pairs, four quotes total.
    assert script.count("'") == 4


def test_toast_never_raises_on_bad_input():
    notify_windows.toast(None, "\udcff", run=lambda c, **k: None)   # type: ignore[arg-type]
    notify_linux.toast(None, "x", run=lambda c, **k: None)          # type: ignore[arg-type]


def test_opener_linux_prefers_evince_and_detaches(monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    seen = []
    monkeypatch.setattr(opener.shutil, "which", lambda n: "/usr/bin/evince" if n == "evince" else None)
    opener.open_file(Path("/tmp/s.pdf"), popen=lambda cmd, **kw: seen.append((cmd, kw)))
    cmd, kw = seen[0]
    assert cmd == ["/usr/bin/evince", "/tmp/s.pdf"] and kw["start_new_session"] is True
    monkeypatch.setattr(opener.shutil, "which", lambda n: "/usr/bin/xdg-open" if n == "xdg-open" else None)
    opener.open_file(Path("/tmp/s.pdf"), popen=lambda cmd, **kw: seen.append((cmd, kw)))
    assert seen[1][0][0] == "/usr/bin/xdg-open"


def test_opener_windows_uses_startfile(monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    seen = []
    monkeypatch.setattr(opener, "_startfile", lambda p: seen.append(p))
    opener.open_file(Path("C:/s.pdf"), popen=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no popen on Windows")))
    assert seen == [str(Path("C:/s.pdf"))]


def test_open_text_uses_notepad_on_windows_and_a_viewer_on_linux(monkeypatch):
    seen = []
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    opener.open_text(Path("C:/h/late-rules.toml"), popen=lambda cmd, **kw: seen.append((cmd, kw)))
    assert seen[0][0] == ["notepad.exe", str(Path("C:/h/late-rules.toml"))]
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    monkeypatch.setattr(opener.shutil, "which", lambda n: "/usr/bin/xdg-open" if n == "xdg-open" else None)
    opener.open_text(Path("/h/late-rules.toml"), popen=lambda cmd, **kw: seen.append((cmd, kw)))
    assert seen[1][0] == ["/usr/bin/xdg-open", "/h/late-rules.toml"] and seen[1][1]["start_new_session"] is True
