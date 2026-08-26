$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "TCG Resale Evaluator is not installed. Run scripts\windows\install.ps1 first."
}

Set-Location $RepoRoot
& $Python -m tcg_resale_evaluator.app
