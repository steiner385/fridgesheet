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
    Write-Host "smoke OK"
} finally {
    Remove-Item Env:\FRIDGESHEET_HOME -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_PRINTER -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_WEB_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:\FRIDGESHEET_WEB_NO_BROWSER -ErrorAction SilentlyContinue
}
