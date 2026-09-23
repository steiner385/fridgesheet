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
#   4. detached spawn   a process spawned the way host/selfupdate_windows.py spawns the
#                       installer survives `taskkill /T` aimed at its parent -- the one claim
#                       no unit test (a fake Popen) can actually prove
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
    # descendant of the one it targets. selfupdate_windows.py spawns the installer with
    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP specifically so the installer -- and
    # whatever it spawns in turn -- is NOT recorded as FridgeSheet.exe's descendant, and so
    # is not caught by that /T. Every unit test written for self-update asserts only the
    # flags handed to a fake `popen`; none of them proves Windows actually honors those flags
    # the way the design assumes. Prove it here, once, on a real runner: start a "parent"
    # process that itself spawns a detached "grandchild", tree-kill the parent by PID exactly
    # as installer.iss does, and confirm the grandchild is still alive afterward. If it is
    # not, self-update would kill its own installer mid-upgrade on a family PC -- so this
    # throws instead of merely warning.
    Write-Host "smoke: detached spawn survives a tree kill"
    $tag = "fridgesheet-smoke-" + [guid]::NewGuid().ToString("N")
    $grandchildScript = Join-Path $env:TEMP "$tag-grandchild.ps1"
    $parentScript = Join-Path $env:TEMP "$tag-parent.ps1"
    $pidFile = Join-Path $env:TEMP "$tag.pid"
    # The grandchild stands in for the installer: it just has to keep running long enough for
    # this check to look at it.
    Set-Content -Path $grandchildScript -Value "Start-Sleep -Seconds 60"
    # The parent stands in for FridgeSheet.exe: it spawns the "installer" the same shape as
    # `spawn_installer` does (a detached child of a still-running app) and then keeps running
    # itself, so it is still there for `taskkill /PID ... /T` to find and kill.
    Set-Content -Path $parentScript -Value @'
param($GrandchildScript, $PidFile)
$g = Start-Process -FilePath powershell -ArgumentList "-NoProfile","-File",$GrandchildScript -WindowStyle Hidden -PassThru
Set-Content -Path $PidFile -Value $g.Id
Start-Sleep -Seconds 60
'@
    $parentProc = Start-Process -FilePath powershell -ArgumentList "-NoProfile","-File",$parentScript,"-GrandchildScript",$grandchildScript,"-PidFile",$pidFile -WindowStyle Hidden -PassThru
    $grandchildId = $null
    try {
        $found = $false
        foreach ($i in 1..20) { Start-Sleep -Milliseconds 500; if (Test-Path $pidFile) { $found = $true; break } }
        if (-not $found) { throw "the grandchild never reported its PID" }
        $grandchildId = [int](Get-Content $pidFile)
        if (-not (Get-Process -Id $grandchildId -ErrorAction SilentlyContinue)) {
            throw "the grandchild exited before the tree kill could even be attempted"
        }

        taskkill /PID $parentProc.Id /T /F | Out-Null
        Start-Sleep -Seconds 2

        if (-not (Get-Process -Id $grandchildId -ErrorAction SilentlyContinue)) {
            throw "detached spawn did not survive taskkill /T -- self-update would kill its own installer mid-upgrade"
        }
        Write-Host "  ok: detached grandchild (pid $grandchildId) outlived the tree kill"
    } finally {
        # Clean up exactly the two processes this check spawned, by PID -- never a
        # name-based sweep like `Get-Process powershell | Stop-Process`, which would also
        # take out any other powershell process this CI runner happens to have going.
        foreach ($id in @($parentProc.Id, $grandchildId)) {
            if ($id) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
        }
        Remove-Item $grandchildScript, $parentScript, $pidFile -ErrorAction SilentlyContinue
    }

    Write-Host "smoke OK"
} finally {
    Remove-Item Env:\FRIDGESHEET_HOME -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_PRINTER -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_WEB_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_WEB_NO_BROWSER -ErrorAction SilentlyContinue
}
