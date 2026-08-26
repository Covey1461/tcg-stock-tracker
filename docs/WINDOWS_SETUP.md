# Windows setup

This is the initial supported deployment path for TCG Resale Evaluator. Google Drive for Desktop should already be installed and signed in.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- Google Drive for Desktop
- A local copy of this repository (GitHub Desktop, `git clone`, or downloaded source)

No API key is required for local intake and photo preparation. Automatic card identification and
recommendations are optional and require an OpenAI API key with API billing enabled.

## Install

1. Open PowerShell in the repository folder.
2. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\windows\install.ps1
   ```

3. Choose a folder inside Google Drive when prompted. Recommended name: `TCG Resale Evaluator`.
4. The installer creates a private virtual environment, installs the app, stores the selected app root as the user-level `TCG_RESALE_ROOT` environment variable, runs the built-in system check, and creates a desktop shortcut.

The selected Drive root is configuration, not a credential. Do not store future API keys in this folder.

## What setup creates in Drive

```text
TCG Resale Evaluator/
├── New Folder/
├── Processing/
├── Completed/
├── Needs Review/
└── Data/
```

`New Folder` is always the reusable intake slot.

## Launch

Use the `TCG Resale Evaluator` desktop shortcut, or run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\launch.ps1
```

## Run the health check again

```powershell
.\.venv\Scripts\python.exe -m tcg_resale_evaluator.diagnostics
```

Every check should report `PASS`.

## Changing the Drive root

Re-run the installer and choose a different folder, or explicitly supply one:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\windows\install.ps1 -RootPath "G:\My Drive\TCG Resale Evaluator"
```

The app does not move old data when the root changes.

## Enable automatic recommendations

1. Create an API key in your OpenAI API project and set a small project spending limit.
2. Close the TCG Resale Evaluator.
3. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\windows\configure-ai.ps1
   ```

4. Paste the key into the hidden prompt and reopen the desktop shortcut.

The key is stored as a Windows user environment variable, never in Google Drive or this repository.
The default balanced-quality model is `gpt-5.6-terra`; `TCG_OPENAI_MODEL` can override it. The app sends
only bounded prepared images, uses structured output and web search, requests `store=false`, and
records token usage and price-source retrieval dates in each lot's `Evaluation/` folder.

When evaluation succeeds, open `recommendations.md` at the top of the completed lot from your phone.
If the asking price is unknown, the file gives a conditional maximum offer. If
`evaluation_error.json` appears, inspect the app log, correct the issue, delete that error file, and
reopen the app to retry.

## Uninstall

The app currently has no system-wide installation. To remove it:

1. Close the app.
2. Delete the repository's `.venv` folder.
3. Delete the desktop shortcut.
4. Remove the user environment variable `TCG_RESALE_ROOT` if desired.

Your Drive data is separate and is not deleted by uninstalling the program.
