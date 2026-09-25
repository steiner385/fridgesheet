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
#   4. detached spawn   a python child spawned the exact way host/selfupdate_windows.py's
#                       spawn_installer spawns (`cmd /c start "" /b ...`) survives
#                       `taskkill /T` aimed at its parent, an unflagged sibling does not, and
#                       the same mechanism through a path containing a space also survives --
#                       the one claim no unit test (a fake Popen) can actually prove
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$exe = Join-Path $root "dist\FridgeSheet\FridgeSheet.exe"
if (-not (Test-Path $exe)) { throw "no built exe at $exe" }
$smokeHome = Join-Path $env:TEMP ("fridgesheet-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force (Join-Path $smokeHome "cache") | Out-Null
# Not a plain Copy-Item: the fixture's committed `fetched_at`/`fetched_at_epoch` drifts stale
# (runner.py's MAX_DATA_AGE_HOURS ceiling on --no-refresh) within a day of being committed,
# and refreshing that committed value would just push the same 24-hour bomb further out. The
# fixture's age is not what this step exercises -- restamp_snapshot.py re-stamps it to "now"
# on the way into the throwaway home instead, every run, so this step never goes stale again.
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "python is not on PATH; smoke.ps1 needs it to restamp the fixture snapshot (see packaging/windows/restamp_snapshot.py)" }
python (Join-Path $root "packaging\windows\restamp_snapshot.py") (Join-Path $root "packaging\windows\fixture-snapshot.json") (Join-Path $smokeHome "cache\snapshot.json")
if ($LASTEXITCODE -ne 0) { throw "restamp_snapshot.py failed (exit $LASTEXITCODE)" }
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
    # A dry run keeps the day's printed sheet.pdf untouched and builds sheet-preview.pdf
    # beside it (#143), so that is the file this step proves.
    $pdf = Get-ChildItem (Join-Path $smokeHome "sheets\*\sheet-preview.pdf") -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pdf) { throw "no sheet-preview.pdf under $smokeHome\sheets" }
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
        if ($r.StatusCode -ne 200 -or $r.Content -notmatch "Fridge Sheet") { Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue; throw "GET $path failed" }
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
    # descendant of the one it targets.
    #
    # An earlier version of this step spawned with `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`
    # and asserted that survives. Measured on real Windows (windows-latest,
    # 2026-09-23, GitHub Actions runs 35844316753 / 35844539925, workflow
    # `probe-detachment.yml`): that assertion is FALSE. A process spawned with those flags is
    # killed by `taskkill /T` exactly like an unflagged control -- both were confirmed
    # recorded descendants of the parent, and both died. What DOES survive is `cmd /c start
    # "" /b <exe> ...`, because cmd.exe exits immediately after launching its target,
    # breaking the recorded parent/child chain before taskkill /T ever walks it -- and that
    # is what `fridgesheet/host/selfupdate_windows.py`'s `spawn_installer` now does. Unit
    # tests only assert that argv is handed to a fake `Popen`; none of them proves Windows
    # actually honors it. This spawns through the REAL mechanism instead of a PowerShell
    # stand-in for it -- a python parent calling `subprocess.Popen` with the exact same argv
    # -- so the thing under test is the thing we ship. (A temp .py file, not `python -c`, to
    # keep two layers of quoting -- PowerShell's -ArgumentList and Python's own -- out of the
    # same string.)
    #
    # One run answers three questions, one grandchild process each:
    #   A. mechanism   the production mechanism above (`cmd /c start "" /b ...`). Expected to
    #                  SURVIVE the tree kill. If it dies, that is a real defect -- self-update
    #                  would kill its own installer mid-upgrade on a family PC -- so this step
    #                  FAILS loudly rather than merely warning.
    #   B. plain       an ordinary child, no special handling -- the negative control.
    #                  Expected to DIE with the parent. If it survives instead, taskkill /T
    #                  never reached the children on this runner at all, which means A
    #                  surviving would prove nothing, so that also fails loudly.
    #   C. spaced      the same production mechanism, but the worker it launches lives under
    #                  a directory whose name contains a space. `start` reads a lone quoted
    #                  argument as the window title, so the empty "" title right after
    #                  `start` is what keeps a real path like
    #                  `C:\Users\John Smith\...\Setup.exe` from being swallowed as a title
    #                  instead of run -- this is the case that would bite a household whose
    #                  Windows username has a space in it. Expected to SURVIVE, exactly like
    #                  A: a household with a spaced username is not a lesser case.
    Write-Host "smoke: detached spawn survives a tree kill (installer.iss:117's taskkill /T)"

    # This step drives the real mechanism through a *python* parent/worker pair (see the
    # comment above), not through the shipped FridgeSheet.exe -- so unlike every other step
    # in this script, it depends on something outside the built bundle. A CI runner with no
    # Python on PATH would otherwise fail deep inside Start-Process below with a bare "the
    # mechanism grandchild never reported its PID" (Wait-ForPidFile timing out because
    # nothing ever started), which sends whoever reads the log looking at the detachment
    # mechanism itself rather than at what actually broke. Fail here, immediately, naming
    # what is missing and why this one step -- and only this step -- needs it.
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "step 4 (detached spawn survives a tree kill) needs 'python' on PATH: it drives " +
              "the real 'cmd /c start' mechanism through a throwaway python parent/worker " +
              "pair rather than the shipped exe, and none was found. Install Python and " +
              "ensure 'python' resolves, or run this smoke test on a runner that already " +
              "has it."
    }

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
    $pidMechanism = Join-Path $env:TEMP "$tag-mechanism.pid"
    $pidPlain = Join-Path $env:TEMP "$tag-plain.pid"
    $pidSpaced = Join-Path $env:TEMP "$tag-spaced.pid"
    # C's worker lives under a directory whose name contains a space, and is itself copied
    # to a filename with a space -- the case that would bite a household whose Windows
    # username has a space in it (%LOCALAPPDATA% is under C:\Users\<username>\...). This
    # path is built INSIDE the python parent, not here: Start-Process -ArgumentList joins
    # array elements with spaces and does not quote them, so handing it a path containing a
    # space would silently split into multiple arguments, misassigning every argv position
    # after it in the parent script below -- with no error, just wrong pid files and step 4
    # blaming the mechanism for a failure that was actually in this harness. $tag itself has
    # no spaces, so it is the only thing that needs to cross that boundary; kept here only
    # so `finally` can clean up the same directory the parent constructs from it.
    $spacedDir = Join-Path $env:TEMP "$tag dir with space"
    $tempFiles = @($workerScript, $parentScript, $pidMechanism, $pidPlain, $pidSpaced)
    $parentProc = $null
    $mechanismId = $null; $mechanismStart = $null
    $plainId = $null; $plainStart = $null
    $spacedId = $null; $spacedStart = $null
    try {
        # The worker just proves it is alive: write its own PID, then sleep. Writing its OWN
        # pid (rather than trusting whatever Popen/Start-Process handed back) is what makes
        # the production mechanism (A, C) provable at all -- `cmd /c start` returns cmd.exe's
        # PID, not the real worker's.
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
import os
import shutil
import subprocess
import sys
import time

CREATE_NO_WINDOW = 0x08000000

worker, tag, pid_mechanism, pid_plain, pid_spaced = sys.argv[1:6]

# C's spaced path is built HERE, not by PowerShell, and only `tag` (no spaces) crossed that
# boundary to get here -- see the comment beside $spacedDir in smoke.ps1 for why.
spaced_dir = os.path.join(os.path.dirname(worker), tag + " dir with space")
spaced_worker = os.path.join(spaced_dir, tag + " worker copy.py")
os.makedirs(spaced_dir, exist_ok=True)
shutil.copy(worker, spaced_worker)

# A: the production mechanism -- exactly what host/selfupdate_windows.py's spawn_installer
# hands to Popen. cmd.exe exits immediately after launching its target, which is what
# breaks the recorded parent/child chain before taskkill /T ever walks it -- not the
# DETACHED_PROCESS/CREATE_NEW_PROCESS_GROUP flags this used to carry, which were measured
# on real Windows to do nothing here.
subprocess.Popen(["cmd", "/c", "start", "", "/b", sys.executable, worker, pid_mechanism],
                  creationflags=CREATE_NO_WINDOW,
                  close_fds=True, stdin=None, stdout=None, stderr=None)

# B: negative control -- an ordinary child, no special handling at all.
subprocess.Popen([sys.executable, worker, pid_plain])

# C: the same production mechanism, but the target lives under a path with a space in it.
# The empty "" right after `start` is what keeps a quoted, spaced path from being read as
# the window title instead of run.
subprocess.Popen(["cmd", "/c", "start", "", "/b", sys.executable, spaced_worker, pid_spaced],
                  creationflags=CREATE_NO_WINDOW,
                  close_fds=True, stdin=None, stdout=None, stderr=None)

time.sleep(120)
'@
        $parentProc = Start-Process -FilePath python -ArgumentList $parentScript,$workerScript,$tag,$pidMechanism,$pidPlain,$pidSpaced -WindowStyle Hidden -PassThru
        $parentStart = $parentProc.StartTime

        $mechanismId = Wait-ForPidFile $pidMechanism
        $plainId = Wait-ForPidFile $pidPlain
        $spacedId = Wait-ForPidFile $pidSpaced
        if (-not $mechanismId) { throw "the mechanism grandchild (A, cmd /c start) never reported its PID" }
        if (-not $plainId) { throw "the negative-control grandchild never reported its PID" }
        if (-not $spacedId) { throw "the spaced-path grandchild (C, cmd /c start under a path with a space) never reported its PID -- that IS the finding: the empty title quoting failed" }

        $mechanismProc = Get-Process -Id $mechanismId -ErrorAction SilentlyContinue
        $plainProc = Get-Process -Id $plainId -ErrorAction SilentlyContinue
        $spacedProc = Get-Process -Id $spacedId -ErrorAction SilentlyContinue
        if (-not $mechanismProc) { throw "the mechanism grandchild exited before the tree kill could even be attempted" }
        if (-not $plainProc) { throw "the negative-control grandchild exited before the tree kill could even be attempted" }
        if (-not $spacedProc) { throw "the spaced-path grandchild exited before the tree kill could even be attempted" }
        $mechanismStart = $mechanismProc.StartTime
        $plainStart = $plainProc.StartTime
        $spacedStart = $spacedProc.StartTime

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
        $mechanismSurvived = [bool](Get-KnownProcess $mechanismId $mechanismStart)
        $spacedSurvived = [bool](Get-KnownProcess $spacedId $spacedStart)

        Write-Host "  B. negative control (unflagged, pid $plainId): $(if ($plainSurvived) { 'SURVIVED (unexpected)' } else { 'died (expected)' })"
        Write-Host "  A. mechanism (cmd /c start, pid $mechanismId): $(if ($mechanismSurvived) { 'survived (expected)' } else { 'DIED (unexpected)' })"
        Write-Host "  C. mechanism, path with a space (pid $spacedId): $(if ($spacedSurvived) { 'survived (expected)' } else { 'DIED (unexpected)' })"

        if ($plainSurvived) {
            throw "the unflagged negative control survived taskkill /T -- it never reached child processes on this runner at all, so the results above prove nothing"
        }
        if (-not $mechanismSurvived) {
            throw "the production spawn mechanism (cmd /c start) did NOT survive taskkill /T -- self-update would kill its own installer mid-upgrade on a family PC"
        }
        if (-not $spacedSurvived) {
            throw "the production spawn mechanism did NOT survive taskkill /T when its target's path contained a space -- self-update would kill its own installer mid-upgrade on any family PC whose Windows username has a space in it"
        }
        Write-Host "  ok: both mechanism grandchildren survived the tree kill and the negative control did not"
    } finally {
        # Clean up exactly the processes this check spawned, guarded by PID *and* start time
        # (Windows recycles PIDs) -- never a name-based sweep like `Get-Process python |
        # Stop-Process`, which would also take out any other python process this CI runner
        # happens to have going.
        if (Get-KnownProcess $parentProc.Id $parentStart) { Stop-Process -Id $parentProc.Id -Force -ErrorAction SilentlyContinue }
        if (Get-KnownProcess $mechanismId $mechanismStart) { Stop-Process -Id $mechanismId -Force -ErrorAction SilentlyContinue }
        if (Get-KnownProcess $plainId $plainStart) { Stop-Process -Id $plainId -Force -ErrorAction SilentlyContinue }
        if (Get-KnownProcess $spacedId $spacedStart) { Stop-Process -Id $spacedId -Force -ErrorAction SilentlyContinue }
        Remove-Item $tempFiles -ErrorAction SilentlyContinue
        Remove-Item $spacedDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Host "smoke OK"
} finally {
    Remove-Item Env:\FRIDGESHEET_HOME -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_PRINTER -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_WEB_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_WEB_NO_BROWSER -ErrorAction SilentlyContinue
}
