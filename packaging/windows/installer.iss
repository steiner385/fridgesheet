; packaging/windows/installer.iss
; Per-user installer for Fridge Sheet. Built by build.ps1:
;   ISCC.exe /DAppVersion=<version> /DSourceDir=<repo>\dist\FridgeSheet /O<repo>\dist installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\FridgeSheet"
#endif

[Setup]
; A new AppId with the new name (0.4.0). The old one, Lakota Sheet's, is in [Code] below:
; setup finds that install by it and runs its uninstaller before installing this one.
AppId={{E2163872-16AD-4E68-B034-78F8DA763A69}
AppName=Fridge Sheet
SetupIconFile=FridgeSheet.ico
AppVersion={#AppVersion}
AppVerName=Fridge Sheet {#AppVersion}
AppPublisher=Tony Stein
AppPublisherURL=https://github.com/steiner385/fridgesheet
AppSupportURL=https://github.com/steiner385/fridgesheet/blob/main/docs/windows.md
DefaultDirName={localappdata}\Programs\Fridge Sheet
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=FridgeSheet-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Fridge Sheet
UninstallDisplayIcon={app}\FridgeSheet.exe

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[InstallDelete]
; An upgrade copies the new bundle over the old one and deletes nothing, so a file the new
; bundle no longer has stays behind. For most files that is harmless clutter; for the
; package's own dist-info it is not: after the first upgrade {app}\_internal held both
; fridgesheet-0.2.0.dist-info and -0.3.0.dist-info, importlib.metadata found the old
; one first, and a 0.3.0 install introduced itself as 0.2.0 -- in the About box, in /health,
; and to the update check, which would then have offered it its own version as new. Seen on
; a real upgrade, 2026-09-18. Every dist-info of ours goes before [Files] runs.
Type: filesandordirs; Name: "{app}\_internal\fridgesheet-*.dist-info"
; ... and the distribution's old name, from any bundle built before the rename.
Type: filesandordirs; Name: "{app}\_internal\lakota_grades_mcp-*.dist-info"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Fridge Sheet"; Filename: "{app}\FridgeSheet.exe"; AppUserModelID: "Cairnea.FridgeSheet"
Name: "{autodesktop}\Fridge Sheet"; Filename: "{app}\FridgeSheet.exe"; AppUserModelID: "Cairnea.FridgeSheet"; Tasks: desktopicon

[Run]
; Register the logon task first, so the server is already running (or will be at next logon)
; before the shortcut below opens the browser at it.
Filename: "{app}\FridgeSheet.exe"; Parameters: "service install"; Flags: runhidden waituntilterminated
Filename: "{app}\FridgeSheet.exe"; Description: "Open Fridge Sheet"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove the logon task and every scheduled task while the exe still exists. RunOnceId keeps
; Inno from running each of them twice. `schedule remove --all` (not a bare `schedule
; remove`, which only ever named the default report) walks every report this app knows about
; -- Inno Setup script cannot itself enumerate a parent's saved reports; they live in
; fridgesheet.db, not anywhere this installer reads.
Filename: "{app}\FridgeSheet.exe"; Parameters: "service remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveService"
Filename: "{app}\FridgeSheet.exe"; Parameters: "schedule remove --all"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveSchedule"

[Code]
const
  // Lakota Sheet, this app's name through 0.3.x. A different AppId, so Inno would not treat
  // this install as its upgrade: both would end up installed, two logon tasks fighting over
  // one port, two Start-menu entries. Setup removes the old one first (RemoveOldLakotaSheet).
  OldAppId = '{B7E1C0E2-5C1D-4E8B-9C2A-7D3F0A1B2C3D}';

procedure RemoveOldLakotaSheet();
var
  Uninst: String;
  ResultCode: Integer;
begin
  // Inno registers a per-user uninstaller under HKCU\...\Uninstall\<AppId>_is1. If the old
  // app is there, stop it the way PrepareToInstall stops this one, then run its uninstaller
  // silently. That uninstaller keeps the data directory (%LOCALAPPDATA%\lakota-grades) and
  // the Credential Manager entry; the app moves both to the new name on its first start
  // (fridgesheet\migrate.py). Best-effort and exit-code-blind, like every stop here: a
  // machine that never had Lakota Sheet has no key and skips this whole block.
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' + OldAppId + '_is1', 'UninstallString', Uninst) then
  begin
    Exec('schtasks.exe', '/End /TN "Lakota Sheet - web"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('taskkill.exe', '/IM LakotaSheet.exe /T /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1000);
    Exec(RemoveQuotes(Uninst), '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  RemoveOldLakotaSheet();
  // The logon task holds FridgeSheet.exe and its _internal DLLs open around the clock, so an
  // upgrade over a working install would hit locked files -- Inno's Restart Manager would at
  // best refuse to overwrite them, at worst ask for a reboot. Inno calls PrepareToInstall
  // before [Files] copies anything, which is the window to stop it; [Run] re-registers and
  // restarts the task afterward, once the new files are in place. #33.
  Exec('schtasks.exe', '/End /TN "Fridge Sheet - web"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // A copy the parent launched from the shortcut (or is still sitting in, having closed the
  // browser tab) is not the task's child, so schtasks /End does not touch it -- kill it by
  // image name too. /T also ends its descendants: {app} ships Chromium under ms-playwright\
  // (running because a dashboard Refresh is in progress) and SumatraPDF.exe (running because a
  // print is in progress), and killing only the parent leaves those winding down on their own
  // -- exactly the locked-file window this function exists to close.
  Exec('taskkill.exe', '/IM FridgeSheet.exe /T /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // Both calls are best-effort and their exit codes are deliberately ignored: on a first
  // install there is no task and no running process, and both commands return non-zero in
  // that ordinary case. Treating that as an error would break the install that works today.
  // Termination above is a request, not a fact, though: /F only asks Windows to tear the
  // process down, and a frozen bundle with a few hundred MB of mapped DLLs does not release
  // its handles the instant taskkill.exe returns. Give it a moment to actually land before
  // [Files] tries to overwrite anything.
  Sleep(1000);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  // Same locked-file hazard as PrepareToInstall, on the other side. [UninstallRun]'s
  // `service remove` ends the logon task, but a copy the parent started from the desktop
  // shortcut is not that task's child and survives it -- along with the Chromium under
  // {app}\ms-playwright\ and the SumatraPDF.exe it may have running -- and then Inno tries to
  // delete {app} out from under all of them. usUninstall runs before [UninstallRun] and
  // before any file is removed, so the exe is still there for [UninstallRun] to start
  // afterwards (those runs are short-lived and exit on their own). Best-effort and
  // exit-code-blind for the same reason as PrepareToInstall: with nothing running, both
  // commands legitimately return non-zero, and an uninstall must not fail over that.
  if CurUninstallStep = usUninstall then
  begin
    Exec('schtasks.exe', '/End /TN "Fridge Sheet - web"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('taskkill.exe', '/IM FridgeSheet.exe /T /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(1000);
  end;
  // SuppressibleMsgBox, not MsgBox: /SUPPRESSMSGBOXES suppresses the boxes Inno itself
  // raises, but a plain MsgBox() from [Code] is the script's own and is shown regardless.
  // A silent uninstall therefore stopped here on a modal dialog with no desktop to show it
  // on -- the uninstaller's own log read "Uninstallation process succeeded. Removed all?
  // Yes" while _unins.tmp sat in memory waiting for an OK nobody could ever click (observed
  // on a real Windows 11 box, 2026-09-17). Everything was in fact removed, so the last
  // argument -- what the call returns when suppressed -- is IDOK: the message is a courtesy,
  // and nothing branches on the answer.
  if CurUninstallStep = usPostUninstall then
    SuppressibleMsgBox('Fridge Sheet has been removed.' + #13#10 + #13#10 +
           'Your settings, notes and flags (fridgesheet.db), printed sheets and logs were kept in' + #13#10 +
           ExpandConstant('{localappdata}\fridgesheet') + #13#10 + #13#10 +
           'Delete that folder yourself if you no longer want them. Your OneLogin password stays in Windows Credential Manager under "fridgesheet".',
           mbInformation, MB_OK, IDOK);
end;
