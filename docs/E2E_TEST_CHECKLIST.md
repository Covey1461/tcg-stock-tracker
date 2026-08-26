# End-to-end Windows / Google Drive validation

Run this after the first Windows installation. Use disposable test images/files rather than a valuable live listing for the first pass.

## 1. Installation and layout

- [ ] Google Drive for Desktop is running and synced.
- [ ] Windows installer completes without an error.
- [ ] Built-in diagnostics show all `PASS`.
- [ ] The desktop shortcut opens TCG Resale Evaluator.
- [ ] `New Folder`, `Processing`, `Completed`, `Needs Review`, and `Data` exist in the selected Drive root.

## 2. Desktop button submission

1. Put 2-3 disposable images/files in `New Folder`.
2. Click **Process Current Lot**.

Verify:

- [ ] The old `New Folder` contents move to a new `LOT-...` folder under `Processing`.
- [ ] A new empty `New Folder` appears immediately.
- [ ] You can begin loading the next listing while the first lot remains in `Processing`.
- [ ] No files are lost or duplicated after Drive finishes syncing.

## 3. Phone `process` trigger

1. From the phone, add several disposable images to the Drive `New Folder`.
2. Wait until the uploads appear complete on the phone.
3. Upload/create a file in the app root whose base name is `process`, for example `PROCESS.txt`.

Verify on the PC after Drive sync:

- [ ] The app waits for the intake to settle rather than moving a partially synced lot.
- [ ] The lot moves into `Processing`.
- [ ] A new empty `New Folder` is recreated.
- [ ] The `process` trigger is deleted only after the successful move/recreation.
- [ ] A trigger with other capitalization such as `Process.md` also works.
- [ ] A near-match such as `process-now.txt` does not trigger processing.

## 4. Rapid consecutive lots

Submit one lot, then immediately begin filling the newly recreated `New Folder` while the first lot is still present in `Processing`.

- [ ] The second lot can be prepared without waiting for the first.
- [ ] Each lot gets a unique folder.
- [ ] Contents never cross between lots.

## 5. Inventory CSV flow

Use `examples/sample_inventory.csv` or a disposable export from the real sorting workflow.

- [ ] Choose a processed/completed lot in the app.
- [ ] Import the inventory CSV.
- [ ] A normalized inventory CSV is created.
- [ ] The total quantity and market value are sensible.
- [ ] A buylist-formatted CSV is created.
- [ ] The raw imported CSV remains preserved.

The default buylist is still a generic profile. Replace it with the exact historical buylist format once a sample is available.

## 6. Search/index integrity

- [ ] `Data/TCG_Deal_Index.csv` opens normally in Excel or Google Sheets.
- [ ] Existing rows remain intact after subsequent operations.
- [ ] Lot IDs/folder paths can be used to locate the corresponding Drive folder.

## 7. Failure behavior

- [ ] Clicking Process Current Lot with an empty intake produces a warning and does not create a lot.
- [ ] A `process` trigger with an empty intake is not silently deleted.
- [ ] Closing/reopening the app leaves the folder structure intact.

## Sign-off

Record the date, Windows version, Google Drive mode (stream/mirror), actual Drive root, and any failures. Those details will guide v0.2 hardening before image intelligence is added.
