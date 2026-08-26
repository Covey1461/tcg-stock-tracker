# TCG Resale Evaluator

Local-first tooling for organizing, preparing, indexing, and reviewing TCG collection listings for resale opportunities.

## What v0.1 does

- Reusable `New Folder` intake for photos and screenshots.
- One-click **Process Current Lot** submission from the desktop app.
- Phone-friendly trigger: place any file whose base name is `process` in the app root (`process`, `PROCESS.txt`, `Process.md`, etc.).
- Waits for Google Drive uploads to settle before moving the lot.
- Moves the lot into `Processing` and immediately recreates an empty `New Folder`.
- Deletes the `process` trigger only after a successful move and replacement-folder creation.
- Maintains a searchable master CSV deal index.
- Imports a final post-sort inventory CSV, preserves the source, normalizes card/pricing data, and creates a buylist-formatted CSV using a profile.
- Includes automated tests and security checks for secret leakage, unsafe paths, Python security issues, and vulnerable dependencies.

## Windows deployment

For the first real-PC installation, see [Windows setup](docs/WINDOWS_SETUP.md) and the [end-to-end Google Drive test checklist](docs/E2E_TEST_CHECKLIST.md). The installer creates a local virtual environment, configures the Drive root, runs a health check, and creates a desktop shortcut.

## Security

No API keys or credentials belong in the repository. Future integrations must use environment variables or an operating-system credential store. See `SECURITY.md` for the security policy and CI checks.

## Development

```bash
python -m pip install -e '.[dev]'
pytest -q
python scripts/secret_scan.py
```

Run the app with:

```bash
tcg-resale-evaluator
```

Run the installation health check with:

```bash
tcg-resale-doctor
```

Set `TCG_RESALE_ROOT` if your Google Drive folder lives somewhere else.
