# packaging/windows/smoke.ps1
# Checks on the built exe, all against a throwaway FRIDGESHEET_HOME so nothing
# touches the builder's real settings and no credential is involved:
#   1. doctor           every probe must pass inside the bundle (Chromium, SumatraPDF, keyring, tzdata...)
#   2. dry-run sheet    run open-work --dry-run --no-refresh --force from a fixture snapshot -> a PDF exists
#   2b. scheduled task  schedule install/remove round-trips through schtasks against a real Task Scheduler
#   3. the server       `web --no-browser` answers /health, /, /diagnostics and /settings from the bundle
#   3b. no-args launch  finds the running server and exits 0 (a crash here is the one failure
#                       the friend would otherwise be first to see)
#   3c. logon task      service install/remove round-trips through schtasks
#   4. detached spawn   a python child spawned with the exact flags host/selfupdate_windows.py
#                       uses survives `taskkill /T` aimed at its parent, an unflagged sibling
#                       does not, and a reparented one is recorded for reference -- the one
#                       claim no unit test (a fake Popen) can actually prove
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$exe = Join-Path $root "dist\FridgeSheet\FridgeSheet.exe"
if (-not (Test-Path $exe)) { throw "no built exe at $exe" }
$smokeHome = Join-Path $env:TEMP ("fridgesheet-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force (Join-Path $smokeHome "cache") | Out-Null
Copy-Item (Join-Path $root "packaging\windows\fixture-snapshot.json") (Join-Path $smokeHome "cache\snapshot.json")
$env:FRIDGESHEET_HOME = $smokeHome
Write-Host "smoke home: $smokeHome"

# The printers probe now correctly fails with no printer configured and no Windows default
# (a real installed PC almost always has one; a freshly imaged CI runner may not). Point the
# app at whatever is installed here, exactly as Settings -> printer would, so the smoke test
# proves printing itself, not this runner's fresh-image quirk.
$printer = Get-Printer -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Name
if ($printer) { $env:FRIDGESHEET_PRINTER = $printer; Write-Host "  using printer: $printer" }

try {
    # 1. doctor (a windowed exe has no stdout; the report is in doctor.txt)
    $p = Start-Process -FilePath $exe -ArgumentList "doctor" -Wait -PassThru -WindowStyle Hidden
    Get-Content (Join-Path $smokeHome "doctor.txt") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    if ($p.ExitCode -ne 0) { throw "doctor reported failures (exit $($p.ExitCode))" }

    # 2. dry-run sheet from the fixture
    $p = Start-Process -FilePath $exe -ArgumentList "run","open-work","--dry-run","--no-refresh","--force" -Wait -PassThru -WindowStyle Hidden
    Get-Content (Join-Path $smokeHome "print-sheet.log") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    if ($p.ExitCode -ne 0) { throw "dry run failed (exit $($p.ExitCode))" }
    $pdf = Get-ChildItem (Join-Path $smokeHome "sheets\*\sheet.pdf") -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pdf) { throw "no sheet.pdf under $smokeHome\sheets" }
    Write-Host "  built $($pdf.FullName) ($($pdf.Length) bytes)"

    # 2b. the scheduled task: task.xml must come out of the frozen bundle and schtasks must accept it
    $p = Start-Process -FilePath $exe -ArgumentList "schedule","install" -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { Get-Content (Join-Path $smokeHome "app.log") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }; throw "schedule install failed (exit $($p.ExitCode))" }
    $q = & schtasks /Query /TN "Fridge Sheet - open-work" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "task not found after install: $q" }
    # --all, not a bare remove: that is the exact command line installer.iss's [UninstallRun]
    # now issues, and it is worth this smoke test proving it against a real schtasks too.
    $p = Start-Process -FilePath $exe -ArgumentList "schedule","remove","--all" -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { throw "schedule remove --all failed (exit $($p.ExitCode))" }
    Write-Host "  scheduled task installed and removed"

    # 3. the server: start it on a free port, fetch two pages, stop it
    $env:FRIDGESHEET_WEB_PORT = "8765"
    $srv = Start-Process -FilePath $exe -ArgumentList "web","--no-browser" -PassThru -WindowStyle Hidden
    $up = $false
    foreach ($i in 1..60) { Start-Sleep -Milliseconds 500; try { $h = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/health; if ($h.Content -match '"fridgesheet"') { $up = $true; break } } catch {} }
    if (-not $up) { Get-Content (Join-Path $smokeHome "app.log") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }; Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue; throw "the server never answered /health" }
    foreach ($path in "/", "/diagnostics", "/settings") {
        $r = Invoke-WebRequest -UseBasicParsing ("http://127.0.0.1:8765" + $path)
        if ($r.StatusCode -ne 200 -or $r.Content -notmatch "Fridge Sheet") { Stop-Process -Id $srv.Id -Force; throw "GET $path failed" }
    }
    Write-Host "  server answered /, /diagnostics, /settings"

    # 3b. no-args launch finds the running server and exits 0 without opening a browser
    $env:FRIDGESHEET_WEB_NO_BROWSER = "1"
    $p = Start-Process -FilePath $exe -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { Get-Content (Join-Path $smokeHome "app.log") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }; Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue; throw "no-args launch failed (exit $($p.ExitCode))" }
    Stop-Process -Id $srv.Id -Force

    # 3c. the logon task round-trips through schtasks. `service install` starts the server via
    #     schtasks /Run on the default port 8433 -- Task Scheduler does not inherit
    #     FRIDGESHEET_WEB_PORT -- and `service remove`'s /End stops it again.
    $p = Start-Process -FilePath $exe -ArgumentList "service","install" -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { Get-Content (Join-Path $smokeHome "app.log") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }; throw "service install failed (exit $($p.ExitCode))" }
    $q = & schtasks /Query /TN "Fridge Sheet - web" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "logon task not found after install: $q" }
    $p = Start-Process -FilePath $exe -ArgumentList "service","remove" -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { throw "service remove failed (exit $($p.ExitCode))" }
    Write-Host "  logon task installed and removed"

    # 4. detached spawn survives a tree kill.
    #
    # installer.iss:117 runs `taskkill /IM FridgeSheet.exe /T /F` before [Files] copies a
    # single file, and /T also kills every process Windows still has recorded as a
    # descendant of the one it targets. fridgesheet/host/selfupdate_windows.py spawns the
    # installer with creationflags = DETACHED_PROCESS (0x8) | CREATE_NEW_PROCESS_GROUP
    # (0x200) specifically so the installer is NOT recorded as FridgeSheet.exe's descendant,
    # and so is not caught by that /T. Unit tests only assert those flags are handed to a
    # fake `Popen`; none of them proves Windows actually honors them. This spawns through the
    # REAL mechanism instead of a PowerShell stand-in for it -- a python parent calling
    # `subprocess.Popen` with the exact same flags -- so the thing under test is the thing we
    # ship. (A temp .py file, not `python -c`, to keep two layers of quoting -- PowerShell's
    # -ArgumentList and Python's own -- out of the same string.)
    #
    # One run answers three questions, one grandchild process each:
    #   A. flagged     the real mechanism above. Expected to SURVIVE the tree kill. If it
    #                  dies, that is a real defect -- self-update would kill its own
    #                  installer mid-upgrade on a family PC -- so this step FAILS loudly
    #                  rather than merely warning.
    #   B. plain       an ordinary child, no special flags -- the negative control. Expected
    #                  to DIE with the parent. If it survives instead, taskkill /T never
    #                  reached the children on this runner at all, which means A surviving
    #                  would prove nothing, so that also fails loudly.
    #   C. reparented  spawned via the classic `cmd /c start` reparenting trick, recorded but
    #                  never gating: DETACHED_PROCESS detaches the console and
    #                  CREATE_NEW_PROCESS_GROUP changes Ctrl+C routing, and neither is
    #                  documented to change the InheritedFromUniqueProcessId that taskkill /T
    #                  actually walks. If A ever fails, this says whether reparenting would
    #                  have worked instead.
    Write-Host "smoke: detached spawn survives a tree kill (installer.iss:117's taskkill /T)"

    # Waits (bounded: 250ms x 40 = 10s max) for a PID file to hold an actual number. The
    # worker writes its own PID after opening the file, so a bare Test-Path can observe it
    # mid write, and `[int]""` under $ErrorActionPreference = "Stop" is a terminating error
    # that would abort the whole release build over a timing hiccup, not a real failure.
    function Wait-ForPidFile($path) {
        for ($i = 0; $i -lt 40; $i++) {
            if (Test-Path $path) {
                $content = Get-Content $path -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($content -match '^\d+$') { return [int]$content }
            }
            Start-Sleep -Milliseconds 250
        }
        return $null
    }

    # Windows recycles PIDs. Every later "is it still alive" check -- including cleanup --
    # goes through here instead of a bare `Get-Process -Id`, so a PID this check spawned that
    # has since been reused by an unrelated process is never mistaken for a survivor, and
    # cleanup never Stop-Process'es a stranger.
    function Get-KnownProcess($processId, $startTime) {
        if (-not $processId) { return $null }
        $p = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($p -and $p.StartTime -eq $startTime) { return $p }
        return $null
    }

    $tag = "fridgesheet-smoke-" + [guid]::NewGuid().ToString("N")
    $workerScript = Join-Path $env:TEMP "$tag-worker.py"
    $parentScript = Join-Path $env:TEMP "$tag-parent.py"
    $pidFlagged = Join-Path $env:TEMP "$tag-flagged.pid"
    $pidPlain = Join-Path $env:TEMP "$tag-plain.pid"
    $pidReparented = Join-Path $env:TEMP "$tag-reparented.pid"
    $tempFiles = @($workerScript, $parentScript, $pidFlagged, $pidPlain, $pidReparented)
    $parentProc = $null
    $flaggedId = $null; $flaggedStart = $null
    $plainId = $null; $plainStart = $null
    $reparentedId = $null; $reparentedStart = $null
    try {
        # The worker just proves it is alive: write its own PID, then sleep. Writing its OWN
        # pid (rather than trusting whatever Popen/Start-Process handed back) is what makes
        # the reparenting case (C) work at all -- `cmd /c start` returns cmd.exe's PID, not
        # the real worker's.
        Set-Content -Path $workerScript -Value @'
import os
import sys
import time

with open(sys.argv[1], "w", encoding="ascii") as f:
    f.write(str(os.getpid()))
time.sleep(120)
'@
        # The parent stands in for FridgeSheet.exe: it spawns all three grandchildren the
        # moment it starts, then stays alive itself so there is something for
        # `taskkill /PID ... /T` to actually kill.
        Set-Content -Path $parentScript -Value @'
import subprocess
import sys
import time

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

worker, pid_flagged, pid_plain, pid_reparented = sys.argv[1:5]

# A: the real mechanism -- exactly the flags selfupdate_windows.py hands to Popen.
subprocess.Popen([sys.executable, worker, pid_flagged],
                  creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                  close_fds=True, stdin=None, stdout=None, stderr=None)

# B: negative control -- an ordinary child, none of those flags.
subprocess.Popen([sys.executable, worker, pid_plain])

# C: the classic reparenting trick, recorded for information only.
subprocess.Popen(["cmd", "/c", "start", "", "/B", sys.executable, worker, pid_reparented])

time.sleep(120)
'@
        $parentProc = Start-Process -FilePath python -ArgumentList $parentScript,$workerScript,$pidFlagged,$pidPlain,$pidReparented -WindowStyle Hidden -PassThru
        $parentStart = $parentProc.StartTime

        $flaggedId = Wait-ForPidFile $pidFlagged
        $plainId = Wait-ForPidFile $pidPlain
        $reparentedId = Wait-ForPidFile $pidReparented
        if (-not $flaggedId) { throw "the flagged grandchild never reported its PID" }
        if (-not $plainId) { throw "the negative-control grandchild never reported its PID" }
        # A missing reparented PID is not an abort: a fast-exiting `cmd /c start` racing this
        # script's patience on a loaded runner just means "not observed", and C is
        # informational only -- it never gates pass/fail.

        $flaggedProc = Get-Process -Id $flaggedId -ErrorAction SilentlyContinue
        $plainProc = Get-Process -Id $plainId -ErrorAction SilentlyContinue
        if (-not $flaggedProc) { throw "the flagged grandchild exited before the tree kill could even be attempted" }
        if (-not $plainProc) { throw "the negative-control grandchild exited before the tree kill could even be attempted" }
        $flaggedStart = $flaggedProc.StartTime
        $plainStart = $plainProc.StartTime
        if ($reparentedId) {
            $reparentedProc = Get-Process -Id $reparentedId -ErrorAction SilentlyContinue
            if ($reparentedProc) { $reparentedStart = $reparentedProc.StartTime }
        }

        taskkill /PID $parentProc.Id /T /F 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "taskkill /PID $($parentProc.Id) /T /F exited $LASTEXITCODE -- the tree kill was never actually attempted, so nothing below can be trusted"
        }

        # taskkill's exit code alone is not proof it landed -- confirm the parent is actually
        # gone (bounded: 250ms x 20 = 5s) before asking what survived it.
        $parentGone = $false
        for ($i = 0; $i -lt 20; $i++) {
            if (-not (Get-KnownProcess $parentProc.Id $parentStart)) { $parentGone = $true; break }
            Start-Sleep -Milliseconds 250
        }
        if (-not $parentGone) {
            throw "the parent process is still alive after taskkill /T /F -- the tree kill never landed, so nothing below can be trusted"
        }
        # A brief, bounded settle: a just-killed process can take an instant to release its
        # children's bookkeeping even after its own PID has already gone.
        Start-Sleep -Seconds 1

        $plainSurvived = [bool](Get-KnownProcess $plainId $plainStart)
        $flaggedSurvived = [bool](Get-KnownProcess $flaggedId $flaggedStart)
        $reparentedSurvived = [bool]($reparentedStart -and (Get-KnownProcess $reparentedId $reparentedStart))

        Write-Host "  B. negative control (unflagged, pid $plainId): $(if ($plainSurvived) { 'SURVIVED (unexpected)' } else { 'died (expected)' })"
        Write-Host "  A. flagged (DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP, pid $flaggedId): $(if ($flaggedSurvived) { 'survived (expected)' } else { 'DIED (unexpected)' })"
        Write-Host "  C. reparented (cmd /c start, informational only): $(if ($reparentedSurvived) { 'survived' } else { 'died' })"

        if ($plainSurvived) {
            throw "the unflagged negative control survived taskkill /T -- it never reached child processes on this runner at all, so the flagged result above proves nothing"
        }
        if (-not $flaggedSurvived) {
            throw "detached spawn (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP) did NOT survive taskkill /T -- self-update would kill its own installer mid-upgrade on a family PC"
        }
        Write-Host "  ok: the flagged grandchild survived the tree kill and the negative control did not"
    } finally {
        # Clean up exactly the processes this check spawned, guarded by PID *and* start time
        # (Windows recycles PIDs) -- never a name-based sweep like `Get-Process python |
        # Stop-Process`, which would also take out any other python process this CI runner
        # happens to have going.
        if (Get-KnownProcess $parentProc.Id $parentProc.StartTime) { Stop-Process -Id $parentProc.Id -Force -ErrorAction SilentlyContinue }
        if (Get-KnownProcess $flaggedId $flaggedStart) { Stop-Process -Id $flaggedId -Force -ErrorAction SilentlyContinue }
        if (Get-KnownProcess $plainId $plainStart) { Stop-Process -Id $plainId -Force -ErrorAction SilentlyContinue }
        if (Get-KnownProcess $reparentedId $reparentedStart) { Stop-Process -Id $reparentedId -Force -ErrorAction SilentlyContinue }
        Remove-Item $tempFiles -ErrorAction SilentlyContinue
    }

    Write-Host "smoke OK"
} finally {
    Remove-Item Env:\FRIDGESHEET_HOME -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_PRINTER -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_WEB_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_WEB_NO_BROWSER -ErrorAction SilentlyContinue
}
