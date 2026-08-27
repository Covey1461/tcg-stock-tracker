# TCG Resale Evaluator

Local-first tooling for organizing, preparing, indexing, and reviewing TCG collection listings for resale opportunities.

## What the app does

- Reusable `New Folder` intake for photos and screenshots.
- One-click **Process Current Lot** submission from the desktop app.
- Phone-friendly trigger: place any file whose base name is `process` in the app root (`process`, `PROCESS.txt`, `Process.md`, etc.).
- Waits for Google Drive uploads to settle before moving the lot.
- Moves the lot into `Processing` and immediately recreates an empty `New Folder`.
- Deletes the `process` trigger only after a successful move and replacement-folder creation.
- Atomically claims queued lots so concurrent workers cannot process the same folder. Claims left
  by a stopped process are safely returned to the queue on the next run.
- Preserves every source image byte-for-byte under `Originals/`.
- Accepts JPEG, PNG, and WebP images and applies file-size, pixel-count, dimension, malformed-file,
  and Pillow decompression-bomb protections before normalization.
- Applies EXIF orientation, creates bounded JPEG copies under `Prepared/Images/`, and detects exact
  plus lightweight perceptual duplicates.
- Creates a contact sheet, conservative `possible_` category filenames, `rename_manifest.csv`,
  `listing_data.json`, `listing_summary.md`, and `chatgpt_prompt.txt`.
- Moves successful lots to `Completed` and safety/validation failures to `Needs Review` with an
  `error_report.json`; originals remain available in either route.
- Maintains a searchable master CSV deal index.
- Optionally identifies visible cards, researches current price evidence, calculates a conservative
  maximum offer, and updates the deal index using the OpenAI Responses API.
- Includes reasonably identifiable visible cards even when printing or finish is uncertain, values
  the unitemized remainder separately as bulk, and avoids double-counting between those estimates.
- Adds a confidence-discounted premium for clearly visible good-card signals and shows exactly how
  much that evidence raises the buying ceiling above the bulk-and-priced-card baseline.
- Uses conservatively priced visible cards as a downside backstop for older or genuinely mixed-era
  lots; when those cards cover at least 75% of the asking price, verified remainder value can support
  a BUY WITH CHECKS closer to the visible-card total. Mostly modern bulk does not receive this bias.
- Drops a phone-friendly `recommendations.md` directly in every evaluated lot with the verdict,
  offer ceiling, expected profit, and any missing photos or details.
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

Set `TCG_RESALE_ROOT` if your Google Drive folder lives somewhere else. Automatic recommendations
are opt-in; see [Windows setup](docs/WINDOWS_SETUP.md#enable-automatic-recommendations).

## Completed lot layout

```text
Completed/LOT-.../
├── Originals/                 # unchanged uploaded files
├── Prepared/
    ├── Images/                # oriented, resized JPEG copies
    ├── contact_sheet.jpg
    ├── rename_manifest.csv
    ├── listing_data.json
    ├── listing_summary.md
│   └── chatgpt_prompt.txt
├── Evaluation/
│   ├── evaluation.json
│   ├── evaluation_summary.md
│   ├── price_sources.json
│   ├── api_usage.json
│   └── recommendations.md
└── recommendations.md         # quick phone view
```

The desktop app runs the processor in the background. Logs are rotated under
`Data/logs/tcg-resale-evaluator.log`.
