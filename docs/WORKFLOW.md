# Workflow

## Desktop

1. Put listing screenshots/photos into `New Folder`.
2. Click **Process Current Lot**.
3. The lot moves to `Processing/<temporary lot id>`.
4. A fresh `New Folder` appears immediately.
5. Continue loading the next listing while prior work continues.

## Phone

1. Upload listing screenshots/photos into the synced `New Folder`.
2. Upload any file whose base name is `process` into the app root. Examples: `process.txt`, `PROCESS`, `Process.md`.
3. The local watcher sees the trigger and waits until the image folder has stopped changing for the configured settle period.
4. It submits the lot and recreates `New Folder`.
5. Only then does it delete the `process` trigger.

If the move fails, the trigger remains in place so the app can retry rather than silently losing the request.

## After sorting the physical lot

1. Export/upload your final card inventory CSV with quantities and pricing.
2. In the app choose **Import Inventory CSV for a Lot**.
3. The source CSV is copied into `Inventory/` unchanged.
4. The app creates `inventory_normalized.csv`.
5. The app creates `buylist_export.csv` using the selected profile.
6. The normalized totals can be written back into the master deal index.

## Buylist formats

`profiles/default-buylist.json` is a placeholder general profile. Once an exact historical buylist sample is available, add a dedicated profile with the exact header names/order expected by that destination.
# Processing worker

After intake places a uniquely named lot in `Processing`, the background worker:

1. Atomically renames the lot to a hidden, process-owned claim.
2. Moves source files into `Originals/` without recompressing or rewriting them.
3. Validates the extension and decoded format allowlists, file size, dimensions, total pixels,
   decompression-bomb warnings, and image readability.
4. Applies EXIF orientation and creates bounded RGB JPEGs under `Prepared/Images/`.
5. Records SHA-256 exact duplicates and difference-hash near duplicates.
6. Generates the contact sheet, rename manifest, JSON metadata, Markdown summary, and ChatGPT prompt.
7. Moves the lot to `Completed` and updates `Data/TCG_Deal_Index.csv`.

Any validation or generation failure sends the lot to `Needs Review` with an error report. Source
files stay in `Originals/`. A claim owned by a process that is no longer running is returned to the
visible queue on the next worker pass. A finished lot is not selected again, and a complete
`Prepared/listing_data.json` acts as the restart marker if final routing was interrupted.

Generated names are intentionally conservative. Category labels such as
`possible_card_image_001.jpg` are hints for human/ChatGPT review, not asserted identifications.
