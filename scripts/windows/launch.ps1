$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

# Desktop/File Explorer processes may not see a user environment-variable change until the next
# Windows sign-in. Read the persisted value explicitly so a newly installed shortcut immediately
# opens the configured Google Drive root instead of the fallback folder.
if ([string]::IsNullOrWhiteSpace($env:TCG_RESALE_ROOT)) {
    $SavedRoot = [Environment]::GetEnvironmentVariable("TCG_RESALE_ROOT", "User")
    if (-not [string]::IsNullOrWhiteSpace($SavedRoot)) {
        $env:TCG_RESALE_ROOT = $SavedRoot
    }
}

if (-not (Test-Path $Python)) {
    throw "TCG Resale Evaluator is not installed. Run scripts\windows\install.ps1 first."
}

Set-Location $RepoRoot
& $Python -m tcg_resale_evaluator.app
