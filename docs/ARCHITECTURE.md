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
- `processor.py`: claims, validates, prepares, indexes, and routes queued image lots.
- `evaluator.py`: opt-in, idempotent image identification, web-priced evaluation, local deal math,
  source/usage artifacts, index updates, and phone recommendations.
- `logging_config.py`: bounded rotating application logs under `Data/logs`.
- `app.py`: lightweight Windows-friendly desktop UI.

## Why polling instead of filesystem events?

Google Drive sync can produce bursts of filesystem events and temporary states. A small polling loop is simpler and more predictable for this use case. The watcher also requires the intake folder signature to remain unchanged for a short settle window before submitting from a phone trigger.
# Processing boundary

`processor.py` is the local queue consumer. Queue ownership is established by an atomic directory
rename that includes the worker process ID. This avoids shared lock services and remains compatible
with a Google Drive-backed root. Dead-process claims are recoverable.

Original uploads and generated files have a strict boundary:

- `Originals/` contains only preserved intake files.
- `Prepared.__building__/` is an internal staging directory.
- `Prepared/` appears only after every output has been written successfully.

This staging boundary makes retries predictable and prevents a partial artifact set from looking
complete. Deal-index writes use an in-process lock and an atomic temporary-file replacement.

Image preparation and categorization are deliberately heuristic and local. The separate evaluator is
disabled by default and requires explicit configuration. It never sends originals, uses an atomic
claim plus staging folder, fingerprints successful inputs, and writes no credential to Drive.
