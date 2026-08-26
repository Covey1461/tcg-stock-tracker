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
