"""The Windows packaging files cannot run here; these tests pin what they must say so a
drift from the spec (a renamed exe, a dropped uninstall step, an unpinned download) fails
on Linux before it costs a Windows build."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIN = ROOT / "packaging" / "windows"

#: The argument list both stop paths pass to taskkill, as one contiguous string. Checking the
#: flags separately does not work here: every `/T` check is satisfied by the `/TN` of the
#: `schtasks /End /TN "Fridge Sheet - web"` call sitting one line away, so `"/T" in body` says
#: nothing about taskkill at all. `/T` (kill the process tree) is the whole point -- {app} also
#: holds the Chromium under ms-playwright\ and SumatraPDF.exe open.
TASKKILL_ARGS = "/IM FridgeSheet.exe /T /F"


def test_sumatra_pin_is_complete_and_hashes_look_like_sha256():
    pin = json.loads((WIN / "sumatra.json").read_text(encoding="utf-8"))
    assert pin["version"] == "3.5.2"
    assert pin["url"].startswith("https://www.sumatrapdfreader.org/dl/rel/3.5.2/") and pin["url"].endswith(".zip")
    assert pin["exe_in_zip"] == "SumatraPDF-3.5.2-64.exe"
    assert pin["license_url"].startswith("https://raw.githubusercontent.com/sumatrapdfreader/sumatrapdf/")
    # SumatraPDF's GitHub tag for this release is "3.5.2rel" (the download site's own
    # version numbering is "3.5.2"; the plain "3.5.2" git ref does not exist and 404s).
    assert pin["license_url"].endswith("/3.5.2rel/COPYING")
    assert pin["source_url"].endswith("/tree/3.5.2rel")
    assert re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) and re.fullmatch(r"[0-9a-f]{64}", pin["license_sha256"])


def test_fixture_snapshot_loads_and_has_one_student_with_nothing_open():
    snap = json.loads((WIN / "fixture-snapshot.json").read_text(encoding="utf-8"))
    assert snap["sources"] == {"canvas": "ok", "hac": "ok"} and snap["stale"] == {}
    (name, entry), = snap["students"].items()
    assert entry["canvas"]["courses"] == [] and entry["hac"]["classes"] == []
    assert isinstance(snap["fetched_at_epoch"], (int, float))


def test_pyinstaller_spec_names_the_entry_point_and_the_package_data():
    spec = (WIN / "FridgeSheet.spec").read_text(encoding="utf-8")
    assert 'name="FridgeSheet"' in spec and "console=False" in spec
    assert "fridgesheet/web/__main__.py" in spec.replace("\\", "/")
    assert "tzdata" in spec and 'copy_metadata("fridgesheet")' in spec and 'copy_metadata("keyring")' in spec
    assert "keyring.backends.Windows" in spec
    assert 'collect_submodules("tzdata")' in spec
    # the browser app: the logon task's XML, the templates and the assets must ride along,
    # and FastAPI/uvicorn/Jinja2 need the hidden imports the part 1 spike proved
    assert "logon-task.xml" in spec
    assert 'web", "templates"' in spec and 'web", "static"' in spec
    assert 'collect_submodules("uvicorn")' in spec and '"fastapi"' in spec


def test_build_script_does_every_spec_step_in_order():
    ps = (WIN / "build.ps1").read_text(encoding="utf-8")
    order = ["pyproject.toml", "[windows]", "playwright install chromium", "sumatra.json", "Get-FileHash", "FridgeSheet.spec",
             "dist\\FridgeSheet\\ms-playwright", "SumatraPDF.exe", "SumatraPDF-LICENSE.txt", "smoke.ps1", "ISCC.exe", "installer.iss"]
    positions = [ps.index(k) for k in order]
    assert positions == sorted(positions), "build.ps1 steps are out of the spec's order"
    assert "$ErrorActionPreference" in ps and '"Stop"' in ps
    assert ps.count("$LASTEXITCODE -ne 0") >= 5 and "$PSNativeCommandUseErrorActionPreference" in ps


def test_smoke_script_runs_doctor_dry_run_the_server_and_a_no_args_launch():
    ps = (WIN / "smoke.ps1").read_text(encoding="utf-8")
    assert "FRIDGESHEET_HOME" in ps and "fixture-snapshot.json" in ps
    assert '"doctor"' in ps and "doctor.txt" in ps
    # A dry run builds sheet-preview.pdf, never the day's sheet.pdf (#143); the smoke test
    # must look for the file the run actually writes, or every release fails at this step.
    assert '"run"' in ps and '"--dry-run"' in ps and '"--no-refresh"' in ps and "sheet-preview.pdf" in ps
    assert "app.log" in ps and "finally" in ps
    assert "$home" not in ps.replace("$smokeHome", ""), "never shadow PowerShell's automatic $HOME"
    assert "MainWindowHandle" not in ps, "the tkinter window is gone; the smoke test drives the server"
    # --all: the exact command line installer.iss's [UninstallRun] issues, run against a real
    # schtasks. `schedule install` only turns a schedule on in config.toml now, so it has no
    # schtasks to prove and the smoke test does not run it (#179 is superseded).
    assert '"schedule","install"' not in ps and '"schedule","remove","--all"' in ps
    # the browser app: serve real pages, then prove the no-args launch and the logon task
    assert '"web","--no-browser"' in ps and "/health" in ps and "/diagnostics" in ps
    assert "FRIDGESHEET_WEB_NO_BROWSER" in ps
    assert '"service","install"' in ps and '"service","remove"' in ps


def test_spike_files_are_gone():
    assert not (WIN / "spike_entry.py").exists()
    assert not (ROOT / ".github" / "workflows" / "spike-pyinstaller.yml").exists()
    assert not (WIN / "spike_web.py").exists() and not (WIN / "SpikeWeb.spec").exists()
    assert not (ROOT / ".github" / "workflows" / "spike-web-pyinstaller.yml").exists()


def test_installer_script_matches_the_spec():
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss
    assert "DefaultDirName={localappdata}\\Programs\\Fridge Sheet" in iss
    assert 'AppUserModelID: "Cairnea.FridgeSheet"' in iss
    assert 'Parameters: "schedule remove --all"' in iss and "[UninstallRun]" in iss
    assert 'Parameters: "service remove"' in iss
    # `service install` runs from [Code], where its exit code is seen (#10), not from [Run].
    assert 'Parameters: "service install"' not in iss
    post = iss[iss.index("procedure CurStepChanged"):]
    post = post[:post.index("\nend;\n") + 6]
    assert "ssPostInstall" in post and "'service install'" in post and "ResultCode <> 0" in post
    assert "SuppressibleMsgBox(" in post                              # a silent self-update never blocks on it
    assert "postinstall" in iss and "desktopicon" in iss
    assert "fridgesheet" in iss and "usPostUninstall" in iss          # the "your data was kept" message
    assert "fridgesheet.db" in iss                                          # ... and it names the database
    assert "OutputBaseFilename=FridgeSheet-Setup-{#AppVersion}" in iss


def test_the_uninstall_farewell_message_can_be_suppressed():
    """A silent uninstall must not stop on a dialog nobody can see.

    `/SUPPRESSMSGBOXES` covers the message boxes *Inno* raises; a plain `MsgBox()` called
    from `[Code]` is the script's own and is shown anyway. Running
    `unins000.exe /VERYSILENT /SUPPRESSMSGBOXES` on a real Windows 11 machine
    (2026-09-17) removed everything correctly -- the log ended "Uninstallation process
    succeeded. Removed all? Yes" -- and then `_unins.tmp` sat in memory for ten minutes
    waiting for an OK on an invisible modal, until it was killed by hand. Interactive
    uninstalls (Settings -> Apps, which is how a parent does it) were never affected, so
    this pins the unattended path specifically.
    """
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    body = iss[iss.index("usPostUninstall"):]
    assert "SuppressibleMsgBox(" in body
    # The bare form would reintroduce the hang. Checked with the trailing "(" so the word
    # inside "SuppressibleMsgBox" does not match.
    assert "MsgBox(" not in body.replace("SuppressibleMsgBox(", "")


def test_installer_stops_the_running_app_before_overwriting_it():
    from fridgesheet.host.service_windows import NAME
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    # An upgrade lands on a running app: the logon task holds FridgeSheet.exe and its
    # _internal DLLs open, so Inno hits locked files unless setup stops it first. #33.
    assert "PrepareToInstall" in iss
    # Scoped to PrepareToInstall's own body, not the whole file: FridgeSheet.exe, NAME and
    # "taskkill"/"schtasks" as bare substrings all appear elsewhere too (e.g. [UninstallRun]),
    # so checking the unscoped file would still pass if the stop moved there instead of
    # running before [Files] copies anything.
    body = iss.split("function PrepareToInstall", 1)[1].split("\nend;", 1)[0]
    assert "schtasks" in body and "/End" in body and NAME in body
    # /T: kill FridgeSheet.exe's descendants too. {app} ships Chromium under ms-playwright\
    # (driven by a Refresh in progress) and SumatraPDF.exe (driven by a print in progress);
    # killing only the parent by image name leaves those winding down on their own, which is
    # exactly the locked-file window this function exists to close.
    #
    # One contiguous string, not `"taskkill" in body and ... and "/T" in body`. That spelling
    # was vacuous: the `schtasks` call one line above passes `/TN "Fridge Sheet - web"`, whose
    # `/TN` contains "/T", so the taskkill flag was never pinned at all -- dropping it left
    # this file green. Pin the argument list the installer actually passes.
    assert "taskkill" in body and TASKKILL_ARGS in body
    # The stop is best-effort: a first install has no task and no running process, and both
    # commands return non-zero in that ordinary case. PrepareToInstall must not fail the
    # install over that -- so its body must never branch on ResultCode. Case-insensitive and
    # whitespace-tolerant: Pascal is case-insensitive, and "If  ResultCode <> 0 then" would
    # slip past a literal "if ResultCode" check.
    assert "ResultCode" in body            # the calls still capture it, per Exec's signature ...
    assert not re.search(r"if\s*\(?\s*ResultCode", body, re.IGNORECASE)    # ... but never test it
    # Termination is a request, not a fact: /F only asks Windows to tear the process down, and
    # a frozen bundle with a few hundred MB of mapped DLLs does not release its handles
    # instantly. Something must give the kill a moment to land before [Files] copies over it.
    assert "Sleep(" in body


def test_uninstaller_stops_the_running_app_before_deleting_its_folder():
    """The install side of this was fixed (`PrepareToInstall`); the uninstall side had the same
    hole. `[UninstallRun]`'s `service remove` ends the logon task, but a copy the parent started
    from the desktop shortcut is not that task's child and outlives it, holding `{app}` --
    FridgeSheet.exe, its `_internal` DLLs, the Chromium under `ms-playwright\\` and
    SumatraPDF.exe -- open while Inno tries to delete the folder.

    `usUninstall` is the hook that runs before `[UninstallRun]` and before any file is removed,
    so the exe is still on disk for those two runs afterwards. Unverified: there is no Windows
    machine here, and the release checklist carries the manual case."""
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    body = iss.split("procedure CurUninstallStepChanged", 1)[1]
    assert "usUninstall" in body and "usPostUninstall" in body         # the stop, and the message box
    stop = body.split("usUninstall then", 1)[1].split("usPostUninstall", 1)[0]
    # Contiguous, for the reason spelled out in the install-side test above: `schtasks`'s
    # `/TN` satisfies a bare `"/T" in stop`, so that spelling pinned nothing.
    assert "taskkill" in stop and TASKKILL_ARGS in stop
    assert "schtasks" in stop and "/End" in stop
    assert "Sleep(" in stop                                            # the kill is a request, not a fact
    assert not re.search(r"if\s*\(?\s*ResultCode", stop, re.IGNORECASE)   # never fail an uninstall on it


def test_release_checklist_describes_the_kill_the_installer_actually_runs():
    """The checklist is what a human debugging a failed upgrade reads. It quoted
    `taskkill /IM FridgeSheet.exe /F` without the `/T` that the script, its comment and
    `test_installer_stops_the_running_app_before_overwriting_it` all treat as the essential
    part -- so a reader would not know to look for orphaned Chromium/SumatraPDF children."""
    page = (ROOT / "docs" / "release-checklist.md").read_text(encoding="utf-8")
    assert "/IM FridgeSheet.exe /F" not in page.replace("/IM FridgeSheet.exe /T /F", "")
    assert "/IM FridgeSheet.exe /T /F" in page
    # ... and the uninstall side, which is new, unverified, and only a human can prove.
    assert "uninstall" in page.lower() and "usUninstall" in page


def test_app_user_model_id_matches_the_toast_code():
    from fridgesheet.host.notify_windows import APP_ID
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    assert f'AppUserModelID: "{APP_ID}"' in iss


def test_release_workflow_triggers_and_gates():
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in wf and '"v*"' in wf
    assert "windows-latest" in wf and "build.ps1" in wf
    assert "upload-artifact" in wf and "action-gh-release" in wf
    assert "startsWith(github.ref, 'refs/tags/v')" in wf
    assert "pyproject.toml" in wf and "github.ref_name" in wf              # tag == v<version> gate
    assert "sumatrapdf/tree/3.5.2" in wf
    # A branch trigger added to prove a Windows build must be taken out again: left in, every
    # push to that branch burns a windows-latest runner for ~20 minutes.
    assert "ccswitch" not in wf, "the temporary branch trigger is still in release.yml"


def test_windows_page_exists_and_names_the_limitations():
    page = (ROOT / "docs" / "windows.md").read_text(encoding="utf-8")
    for phrase in ("SmartScreen", "More info", "Run anyway", "multi-factor", "logged in", "%LOCALAPPDATA%\\fridgesheet",
                   "Test login", "Print now", "no-print-days.txt", "late-rules.toml", "doctor.txt", "Task Scheduler", "Uninstall",
                   "Schedules", "PDF only", "installed itself"):
        assert phrase in page, phrase
    # The QR code is the last sentence of spec section 8 and the one thing on the phone step a
    # parent cannot discover by reading the page: the credits at the bottom thanked segno for
    # it while the walkthrough only ever said "the address to type on the phone", and the
    # release checklist has a human pointing a camera at something the page never mentions.
    assert "QR code" in page
    # The uninstall paragraph promises the uninstaller takes every task with it. Inno runs
    # `schedule remove --all` with `runhidden` and discards its exit code, so that promise can
    # fail silently (an unreadable config.toml, a refused removal); the page has to say where
    # to look. Whoever rewrites that paragraph keeps a pointer to Task Scheduler in it.
    uninstall = page.split("## Uninstall", 1)[1].split("\n## ", 1)[0]
    assert "Task Scheduler" in uninstall and "Delete" in uninstall
    # The Settings page lost these two controls in Plan D part 2; a page that still tells a
    # parent to tick a checkbox that is not there is worse than one that says nothing.
    assert "Print the sheet automatically on school days" not in page
    # The installer's [UninstallRun] used to run a bare `schedule remove`, which only ever
    # named the default report's task (cli.py's `report` positional defaults to "open-work");
    # a parent who scheduled another report on the Schedules page kept that task after
    # uninstalling. It now runs `schedule remove --all` (fridgesheet/cli.py's
    # `_cmd_schedule_remove_all`), which asks Task Scheduler itself for every root-folder
    # `Fridge Sheet - *` task except the web server's own (`host.scheduling_windows.leftovers`)
    # -- no config.toml or database read, so nothing a parent deleted is recreated and no task
    # left by a long-deleted report is missed. Whoever narrows that listing again, or drops back
    # to a bare `schedule remove`, must come here and put the old caveat back -- otherwise this
    # sentence promises something the installer no longer does.
    assert "removes both scheduled tasks" not in page          # never the literal old phrasing either
    assert "will keep running" not in page
    assert "every task it installed" in page
    # The Host check (web/app.py's `same_origin_only`) refuses a parent who reaches the app by
    # this PC's computer name or through a port-forward -- something that worked before it
    # existed. The refusal page names the address that does work; this page has to say the same
    # thing, and has to document the one knob that changes it. `FRIDGESHEET_WEB_HOST` was in no
    # user-facing document at all.
    assert "Fridge Sheet only answers at http://127.0.0.1:8433/" in page
    assert "FRIDGESHEET_WEB_HOST" in page and ".env" in page
    # ...and honestly. Pinning it to a name or a LAN IP takes uvicorn off loopback, which
    # breaks `server.run`'s already-running check, `web/__main__.py`'s launcher probe and
    # `doctor.py`'s web-server probe -- all three hardcode 127.0.0.1. A page that sells it as
    # the fix for the computer-name case sends a parent into exactly that.
    hatch = page.split("`FRIDGESHEET_WEB_HOST`", 1)[1].split("\n- **\"Login failed\"", 1)[0]
    assert "Diagnostics" in hatch and "already running" in hatch
    assert "not a way to make" in hatch


def test_an_upgrade_removes_the_previous_versions_dist_info():
    """An upgrade copies over and deletes nothing, so the old dist-info survived beside the new
    one and importlib.metadata found it first: a 0.3.0 install reported 0.2.0 everywhere,
    including to the update check. Seen on a real upgrade, 2026-09-18."""
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    assert "[InstallDelete]" in iss
    # The section header at line start: the [InstallDelete] comment itself mentions "[Files]".
    block = iss.split("\n[InstallDelete]\n", 1)[1].split("\n[Files]\n", 1)[0]
    assert 'Type: filesandordirs; Name: "{app}\\_internal\\fridgesheet-*.dist-info"' in block
    assert iss.index("\n[InstallDelete]\n") < iss.index("\n[Files]\n")


def test_installer_removes_the_lakota_sheet_install_it_replaces():
    """0.4.0 renamed the app and its AppId. Inno only upgrades in place over the *same* AppId,
    so without this a parent ends up with both apps installed, two logon tasks and one port.
    Setup must find the old app by its old AppId and run its uninstaller silently first."""
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    assert "AppId={{E2163872-16AD-4E68-B034-78F8DA763A69}" in iss
    assert "OldAppId = '{B7E1C0E2-5C1D-4E8B-9C2A-7D3F0A1B2C3D}'" in iss
    body = iss.split("procedure RemoveOldLakotaSheet", 1)[1].split("\nend;", 1)[0]
    assert "RegQueryStringValue(HKCU" in body and "_is1" in body and "UninstallString" in body
    assert "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" in body
    assert '/End /TN "Lakota Sheet - web"' in body and "/IM LakotaSheet.exe /T /F" in body
    # ... and it runs from PrepareToInstall, before [Files] copies anything.
    prepare = iss.split("function PrepareToInstall", 1)[1].split("\nend;", 1)[0]
    assert "RemoveOldLakotaSheet();" in prepare
    # The old distribution's dist-info goes too, or importlib.metadata may report 0.3.x.
    block = iss.split("\n[InstallDelete]\n", 1)[1].split("\n[Files]\n", 1)[0]
    assert "lakota_grades_mcp-*.dist-info" in block


def test_the_mark_is_rendered_into_the_icon_the_exe_and_installer_use():
    from PIL import Image
    ico = WIN / "FridgeSheet.ico"
    assert ico.is_file()
    sizes = sorted(Image.open(ico).info.get("sizes", []))
    assert (16, 16) in sizes and (256, 256) in sizes
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    spec = (WIN / "FridgeSheet.spec").read_text(encoding="utf-8")
    assert "SetupIconFile=FridgeSheet.ico" in iss and 'icon=os.path.join(SPECPATH, "FridgeSheet.ico")' in spec
    static = ROOT / "fridgesheet" / "web" / "static"
    assert (static / "mark.svg").read_text(encoding="utf-8") == (static / "favicon.svg").read_text(encoding="utf-8")
    assert (static / "mark-32.png").is_file() and (static / "mark-180.png").is_file()


def test_the_docs_name_extra_hosts_as_the_way_to_use_a_computer_name():
    """#149: `[web] extra_hosts` is how `http://dobby:8433/` gets admitted, and it was in no
    document -- docs/windows.md said there was no clean way at all."""
    page = (ROOT / "docs" / "windows.md").read_text(encoding="utf-8")
    assert "There is no clean way" not in page
    assert "extra_hosts" in page and 'extra_hosts = ["' in page
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "extra_hosts" in readme
