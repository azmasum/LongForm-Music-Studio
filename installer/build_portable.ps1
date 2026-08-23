# Builds the portable ZIP: pyinstaller -> dist\LongFormMusicStudio ->
# releases\LongFormMusicStudio-<version>-portable.zip
# Run from the repo root:  powershell -File installer\build_portable.ps1
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot\..

Write-Host "== LFMS portable build ==" -ForegroundColor Cyan

# 1) version from source of truth
$version = python -c "import sys; sys.path.insert(0,'.'); from lfms.core.version import VERSION; print(VERSION)"
if (-not $version) { throw "could not read VERSION" }
Write-Host "Version: $version"

# 2) tests must pass before packaging (fast core suite, GUI off)
Write-Host "Running test suite..." -ForegroundColor Cyan
python -m pytest -q --tb=short
if ($LASTEXITCODE -ne 0) { throw "tests failed; aborting build" }

# 3) ruff must be clean
python -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "ruff failed; aborting build" }

# 4) PyInstaller
Write-Host "Running PyInstaller..." -ForegroundColor Cyan
python -m PyInstaller installer\lfms.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# 5) verify the frozen exe headlessly (exit code is the assertion)
$exe = "dist\LongFormMusicStudio\LongFormMusicStudio.exe"
if (-not (Test-Path $exe)) { throw "missing $exe" }
Write-Host "Self-check on frozen build..." -ForegroundColor Cyan
$env:LFMS_SELF_CHECK = "1"
& $exe | Out-Null
$selfcheck = $LASTEXITCODE
Remove-Item Env:LFMS_SELF_CHECK
if ($selfcheck -ne 0) { throw "frozen self-check failed rc=$selfcheck" }
Write-Host "Frozen self-check OK" -ForegroundColor Green

# 6) zip it
New-Item -ItemType Directory -Force -Path releases | Out-Null
$zip = "releases\LongFormMusicStudio-$version-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path dist\LongFormMusicStudio -DestinationPath $zip
$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Built $zip ($size MB)" -ForegroundColor Green

Write-Host ""
Write-Host "Next (optional): compile installer\setup.iss with Inno Setup 6 (ISCC.exe)." -ForegroundColor Yellow
