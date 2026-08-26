# TCG Resale Evaluator

A local-first desktop app for turning Marketplace/OfferUp TCG listing photos into an organized, searchable resale workflow without requiring Zapier.

## V1 goals

- Keep a permanent `New Folder` drop slot in a Google Drive-synced folder.
- Submit the current lot from the desktop app or from a phone by uploading any file whose base name is `process` (case-insensitive), such as `PROCESS.txt` or `Process.md`.
- Move submitted lots into a processing queue and immediately recreate a fresh `New Folder` so the next lot can be uploaded while the first is still processing.
- Delete the `process` trigger only after the move and fresh-folder creation both succeed.
- Preserve original images and create resized analysis copies.
- Generate readable filenames, lot metadata, a ChatGPT-ready prompt, and a searchable deal index.
- Import a final inventory/pricing CSV after a lot is fully sorted.
- Normalize that inventory and export a second CSV using a configurable buylist profile.

## Folder layout

```text
TCG Resale Evaluator/
├── New Folder/                 # reusable intake slot
├── Processing/                 # submitted lots waiting/being processed
├── Completed/                  # processed lots
├── Needs Review/               # failures / ambiguous lots
├── Data/
│   └── TCG_Deal_Index.csv      # searchable master index
└── process.txt                 # optional phone trigger; deleted after successful submit
```

## Trigger behavior

The trigger matcher uses the file's **base name**, ignoring capitalization and extension:

- `process` ✅
- `PROCESS.txt` ✅
- `Process.md` ✅
- `process.jpg` ✅
- `process-now.txt` ❌

The trigger is not deleted until the lot has been moved to `Processing` and a replacement `New Folder` has been created. If submission fails, the trigger remains so the app can retry after the problem is fixed.

## Development status

This repository is being built in small tested slices. See `docs/ARCHITECTURE.md` and `docs/WORKFLOW.md`.
