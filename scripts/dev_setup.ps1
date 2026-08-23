# Development environment setup for LFMS (Windows PowerShell 5.1+)
param(
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path "$root\.venv\Scripts\python.exe")) {
    Write-Host 'Creating virtual environment...'
    python -m venv .venv
}

$py = "$root\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -e ".[dev]"

if ($SkipTests) {
    Write-Host 'Setup complete. Tests skipped.'
} else {
    & $py -m pytest
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Setup complete. All tests passed.'
    } else {
        Write-Warning 'Tests failed - see output above.'
        exit 1
    }
}
