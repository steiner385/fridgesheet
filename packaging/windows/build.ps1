# packaging/windows/build.ps1
# Builds dist\FridgeSheet\ and dist\FridgeSheet-Setup-<version>.exe. Runnable by hand on
# any Windows box with Python 3.12 and Inno Setup 6; this is exactly what release.yml runs.
#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$SkipSmoke,        # skip the smoke test (faster local iteration)
    [switch]$SkipInstaller     # stop after dist\FridgeSheet\ (no Inno Setup needed)
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$ProgressPreference = "SilentlyContinue"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))

$version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
if (-not $version) { throw "could not read version from pyproject.toml" }
Write-Host "== Fridge Sheet $version"

Write-Host "== Python packages"
python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed ($LASTEXITCODE)" }
python -m pip install ".[windows]" "pyinstaller>=6.6"
if ($LASTEXITCODE -ne 0) { throw "pip install failed ($LASTEXITCODE)" }

Write-Host "== Chromium"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD "build\ms-playwright"
python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "playwright install chromium failed ($LASTEXITCODE)" }

Write-Host "== SumatraPDF (pinned)"
$pin = Get-Content packaging\windows\sumatra.json | ConvertFrom-Json
New-Item -ItemType Directory -Force build\sumatra | Out-Null
Invoke-WebRequest -UseBasicParsing -Uri $pin.url -OutFile build\sumatra\sumatra.zip
$hash = (Get-FileHash build\sumatra\sumatra.zip -Algorithm SHA256).Hash.ToLower()
if ($hash -ne $pin.sha256) { throw "SumatraPDF checksum mismatch: got $hash, pinned $($pin.sha256)" }
Expand-Archive -Force build\sumatra\sumatra.zip build\sumatra
Invoke-WebRequest -UseBasicParsing -Uri $pin.license_url -OutFile build\sumatra\COPYING
$lhash = (Get-FileHash build\sumatra\COPYING -Algorithm SHA256).Hash.ToLower()
if ($lhash -ne $pin.license_sha256) { throw "SumatraPDF licence checksum mismatch: got $lhash" }

Write-Host "== PyInstaller"
Remove-Item -Recurse -Force dist\FridgeSheet -ErrorAction SilentlyContinue
pyinstaller --noconfirm --clean packaging\windows\FridgeSheet.spec
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed ($LASTEXITCODE)" }
Copy-Item -Recurse build\ms-playwright dist\FridgeSheet\ms-playwright
Copy-Item (Join-Path build\sumatra $pin.exe_in_zip) dist\FridgeSheet\SumatraPDF.exe
Copy-Item build\sumatra\COPYING dist\FridgeSheet\SumatraPDF-LICENSE.txt
Remove-Item Env:\PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue   # the exe must find Chromium by itself

if (-not $SkipSmoke) {
    Write-Host "== Smoke test"
    & (Join-Path $PSScriptRoot "smoke.ps1")
}

$distSizeMB = (Get-ChildItem dist\FridgeSheet -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Host "== dist size: $([math]::Round($distSizeMB)) MB (dist\FridgeSheet)"

if ($SkipInstaller) { Write-Host "== done (no installer)"; exit 0 }

Write-Host "== Inno Setup"
$iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found at $iscc" }
Remove-Item dist\FridgeSheet-Setup-*.exe -ErrorAction SilentlyContinue
& $iscc "/DAppVersion=$version" "/DSourceDir=$PWD\dist\FridgeSheet" "/O$PWD\dist" packaging\windows\installer.iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
Get-ChildItem dist\FridgeSheet-Setup-*.exe | ForEach-Object { Write-Host "== built $($_.FullName) ($([math]::Round($_.Length / 1MB)) MB), dist\FridgeSheet was $([math]::Round($distSizeMB)) MB" }
