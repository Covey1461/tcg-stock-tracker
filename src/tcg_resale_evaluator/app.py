from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import AppConfig
from .intake import SubmissionError, submit_current_lot
from .inventory_flow import import_inventory_for_lot
from .watcher import IntakeWatcher


def open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]  # nosec B606 - opens a trusted local app folder
    else:
        import subprocess  # nosec B404 - fixed OS opener, never uses a shell

        subprocess.Popen(  # nosec B603 - executable is fixed and path is passed as one argument
            ["open" if os.uname().sysname == "Darwin" else "xdg-open", str(path)]
        )


class App(tk.Tk):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.config.ensure_layout()
        self.title("TCG Resale Evaluator")
        self.geometry("720x420")
        self.minsize(620, 360)

        self.status_var = tk.StringVar(value="Ready. Drop photos into New Folder.")
        self.path_var = tk.StringVar(value=str(config.root))

        container = ttk.Frame(self, padding=18)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="TCG Resale Evaluator", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(container, textvariable=self.path_var).pack(anchor="w", pady=(4, 18))

        primary = ttk.Button(container, text="Process Current Lot", command=self.process_now)
        primary.pack(fill="x", ipady=10)

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=10)
        ttk.Button(actions, text="Open New Folder", command=lambda: open_path(config.intake_dir)).pack(side="left", expand=True, fill="x", padx=(0, 4))
        ttk.Button(actions, text="Open Processing", command=lambda: open_path(config.processing_dir)).pack(side="left", expand=True, fill="x", padx=4)
        ttk.Button(actions, text="Open Completed", command=lambda: open_path(config.completed_dir)).pack(side="left", expand=True, fill="x", padx=(4, 0))

        ttk.Separator(container).pack(fill="x", pady=16)

        ttk.Label(container, text="Post-sort inventory").pack(anchor="w")
        ttk.Button(container, text="Import Inventory CSV for a Lot", command=self.import_inventory).pack(fill="x", pady=(6, 0), ipady=6)

        ttk.Label(container, textvariable=self.status_var, wraplength=650).pack(anchor="w", pady=(22, 0))

        self.watcher = IntakeWatcher(config, on_status=self._threadsafe_status)
        self.watcher.start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _threadsafe_status(self, message: str) -> None:
        self.after(0, lambda: self.status_var.set(message))

    def process_now(self) -> None:
        try:
            result = submit_current_lot(self.config)
        except SubmissionError as exc:
            messagebox.showwarning("Could not submit lot", str(exc))
            return
        self.status_var.set(f"Queued {result.lot_id}. A fresh New Folder is ready.")

    def import_inventory(self) -> None:
        lot_folder = filedialog.askdirectory(
            title="Choose the processed lot folder",
            initialdir=str(self.config.completed_dir),
        )
        if not lot_folder:
            return
        csv_path = filedialog.askopenfilename(
            title="Choose the final card inventory CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not csv_path:
            return

        profile_path = Path(__file__).resolve().parents[2] / "profiles" / "default-buylist.json"
        if not profile_path.exists():
            picked = filedialog.askopenfilename(
                title="Choose buylist profile JSON",
                filetypes=[("JSON files", "*.json")],
            )
            if not picked:
                return
            profile_path = Path(picked)

        def work() -> None:
            try:
                result = import_inventory_for_lot(Path(lot_folder), Path(csv_path), profile_path)
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Inventory import failed", str(exc)))
                return
            text = (
                f"Imported {result.summary.rows} rows / {result.summary.quantity} cards. "
                f"Market value: ${result.summary.market_value:.2f}. "
                f"Buylist CSV created at {result.buylist_csv.name}."
            )
            self.after(0, lambda: self.status_var.set(text))

        threading.Thread(target=work, daemon=True).start()

    def on_close(self) -> None:
        self.watcher.stop()
        self.destroy()


def choose_root() -> Path:
    env_root = os.getenv("TCG_RESALE_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    default = Path.home() / "Google Drive" / "TCG Resale Evaluator"
    return default


def main() -> None:
    config = AppConfig(root=choose_root())
    app = App(config)
    app.mainloop()


if __name__ == "__main__":
    main()
