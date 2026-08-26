param(
    [string]$RootPath = "",
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

function Find-Python {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += ,@("py", "-3")
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $candidates += ,@("python")
    }

    foreach ($candidate in $candidates) {
        $exe = $candidate[0]
        $prefix = @($candidate | Select-Object -Skip 1)
        try {
            $version = & $exe @prefix -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$version -ge [version]"3.11") {
                return ,$candidate
            }
        } catch {
            continue
        }
    }
    throw "Python 3.11 or newer is required. Install Python from python.org, then run this script again."
}

function Choose-RootFolder {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Choose the TCG Resale Evaluator folder inside Google Drive. You can create a new folder here."
    $dialog.ShowNewFolderButton = $true
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        throw "Setup cancelled because no Drive folder was selected."
    }
    return $dialog.SelectedPath
}

Write-Host "TCG Resale Evaluator - Windows setup" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"

$PythonCommand = Find-Python
$PythonExe = $PythonCommand[0]
$PythonPrefix = @($PythonCommand | Select-Object -Skip 1)
Write-Host "Using Python: $PythonExe $($PythonPrefix -join ' ')"

$Venv = Join-Path $RepoRoot ".venv"
if (-not (Test-Path $Venv)) {
    Write-Host "Creating virtual environment..."
    & $PythonExe @PythonPrefix -m venv $Venv
}

$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment creation failed: $VenvPython was not created."
}

Write-Host "Installing application..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e .

if ([string]::IsNullOrWhiteSpace($RootPath)) {
    $RootPath = Choose-RootFolder
}

$RootPath = [System.IO.Path]::GetFullPath($RootPath)
New-Item -ItemType Directory -Force -Path $RootPath | Out-Null
[Environment]::SetEnvironmentVariable("TCG_RESALE_ROOT", $RootPath, "User")
$env:TCG_RESALE_ROOT = $RootPath
Write-Host "Drive root: $RootPath"

Write-Host "Running system check..."
& $VenvPython -m tcg_resale_evaluator.diagnostics
if ($LASTEXITCODE -ne 0) {
    throw "System check failed. Review the messages above before launching the app."
}

if (-not $NoShortcut) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "TCG Resale Evaluator.lnk"
    $Launcher = Join-Path $PSScriptRoot "launch.ps1"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = "powershell.exe"
    $Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$Launcher`""
    $Shortcut.WorkingDirectory = $RepoRoot
    $Shortcut.Description = "Launch TCG Resale Evaluator"
    $Shortcut.Save()
    Write-Host "Desktop shortcut created: $ShortcutPath"
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Open the desktop shortcut or run scripts\windows\launch.ps1."
