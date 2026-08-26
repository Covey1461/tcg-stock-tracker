# Architecture

## Design principles

1. **Local first.** Google Drive for Desktop handles cloud sync. The app operates on normal local folders.
2. **No paid automation dependency.** Core intake, indexing, CSV processing, and file operations run locally.
3. **One submission path.** Desktop button and phone trigger both call `submit_current_lot`.
4. **Safe trigger cleanup.** A `process` trigger is removed only after the lot is queued and a fresh intake folder exists.
5. **Preserve raw inputs.** Original images and uploaded inventory CSVs are retained.
6. **Configurable exports.** Buylist formats are JSON profiles rather than hard-coded one-off conversions.

## Components

- `config.py`: folder layout and application settings.
- `intake.py`: submit transaction and `process` filename rules.
- `stability.py`: detects when synced files have stopped changing.
- `watcher.py`: polling watcher for phone triggers.
- `csv_tools.py`: inventory normalization and template-driven buylist export.
- `inventory_flow.py`: preserves the raw CSV and creates normalized + buylist outputs.
- `index_store.py`: master searchable CSV index.
- `app.py`: lightweight Windows-friendly desktop UI.

## Why polling instead of filesystem events?

Google Drive sync can produce bursts of filesystem events and temporary states. A small polling loop is simpler and more predictable for this use case. The watcher also requires the intake folder signature to remain unchanged for a short settle window before submitting from a phone trigger.
