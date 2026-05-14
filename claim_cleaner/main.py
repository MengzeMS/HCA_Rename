"""
Claim Data Cleaner v1.0 — tkinter GUI entry point.
Run with:  python main.py
Package:   pyinstaller build.spec
"""
from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import (
    END,
    BooleanVar,
    Frame,
    IntVar,
    Label,
    Spinbox,
    StringVar,
    Text,
    Tk,
    filedialog,
    messagebox,
    ttk,
)
import tkinter as tk

# Allow running from repo root without install
sys.path.insert(0, str(Path(__file__).parent))

from config import settings as app_settings
from config.config_manager import MasterConfig, ConfigError, download_from_sharepoint
from pipeline.orchestrator import run_pipeline, PipelineError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

APP_TITLE = "Claim Data Cleaner v1.0"
WIN_WIDTH = 660
WIN_HEIGHT = 620


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.resizable(True, True)
        self.minsize(WIN_WIDTH, WIN_HEIGHT)

        self._settings = app_settings.load()
        self._config: MasterConfig | None = None
        self._processing = False

        self._build_ui()
        self._try_load_default_config()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}
        self.columnconfigure(0, weight=1)

        # ── Title bar ──
        title_frame = Frame(self, bg="#003366")
        title_frame.grid(row=0, column=0, sticky="ew")
        Label(
            title_frame,
            text=APP_TITLE,
            bg="#003366",
            fg="white",
            font=("Segoe UI", 13, "bold"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=8)

        body = Frame(self)
        body.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        body.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        row = 0

        # ── Master config selector ──
        Label(body, text="Master Config (.xlsx):", anchor="w").grid(
            row=row, column=0, sticky="w", **pad
        )
        self._config_path_var = StringVar(
            value=self._settings.get("local_master_config", "")
        )
        config_entry = tk.Entry(body, textvariable=self._config_path_var, width=45)
        config_entry.grid(row=row, column=1, sticky="ew", padx=(0, 4), pady=6)
        tk.Button(body, text="Select File…", command=self._select_config).grid(
            row=row, column=2, padx=(0, 12), pady=6
        )
        row += 1

        # Config status label
        self._config_status_var = StringVar(value="Status: not loaded")
        Label(body, textvariable=self._config_status_var, fg="gray", anchor="w").grid(
            row=row, column=1, columnspan=2, sticky="w", padx=(0, 12), pady=(0, 4)
        )
        row += 1

        # ── SharePoint refresh ──
        sp_frame = Frame(body)
        sp_frame.grid(row=row, column=0, columnspan=3, sticky="w", **pad)
        tk.Button(
            sp_frame,
            text="↻  Refresh Config from SharePoint",
            command=self._refresh_sharepoint,
        ).pack(side="left")
        self._sp_sync_var = StringVar(
            value=f"SharePoint sync: {self._settings.get('last_sharepoint_sync', 'never')}"
        )
        Label(sp_frame, textvariable=self._sp_sync_var, fg="gray").pack(
            side="left", padx=10
        )
        row += 1

        ttk.Separator(body, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=8
        )
        row += 1

        # ── Input file selector ──
        Label(body, text="Input File (.csv / .xlsx):", anchor="w").grid(
            row=row, column=0, sticky="w", **pad
        )
        self._input_path_var = StringVar()
        tk.Entry(body, textvariable=self._input_path_var, width=45).grid(
            row=row, column=1, sticky="ew", padx=(0, 4), pady=6
        )
        tk.Button(body, text="Select File…", command=self._select_input).grid(
            row=row, column=2, padx=(0, 12), pady=6
        )
        row += 1

        # ── Fuzzy threshold spinner ──
        Label(body, text="Fuzzy Match Threshold:", anchor="w").grid(
            row=row, column=0, sticky="w", **pad
        )
        self._fuzzy_var = IntVar(value=self._settings.get("fuzzy_threshold", 2))
        Spinbox(body, from_=1, to=3, textvariable=self._fuzzy_var, width=5).grid(
            row=row, column=1, sticky="w", padx=(0, 4), pady=6
        )
        Label(body, text="(edit distance, 1–3)", fg="gray").grid(
            row=row, column=2, sticky="w", padx=(0, 12)
        )
        row += 1

        # ── Process button ──
        self._process_btn = tk.Button(
            body,
            text="▶  Process File",
            command=self._start_processing,
            bg="#1a7a32",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=6,
        )
        self._process_btn.grid(row=row, column=0, columnspan=3, pady=12)
        row += 1

        # ── Progress bar ──
        Label(body, text="Progress:", anchor="w").grid(
            row=row, column=0, sticky="w", **pad
        )
        self._progress_var = IntVar(value=0)
        self._progress_bar = ttk.Progressbar(
            body, variable=self._progress_var, maximum=100, length=350
        )
        self._progress_bar.grid(row=row, column=1, sticky="ew", pady=6)
        self._progress_pct_var = StringVar(value="0%")
        Label(body, textvariable=self._progress_pct_var, width=5).grid(
            row=row, column=2, padx=(4, 12)
        )
        row += 1

        # ── Status message ──
        self._status_var = StringVar(value="")
        Label(body, textvariable=self._status_var, fg="#555555", anchor="w", wraplength=500).grid(
            row=row, column=0, columnspan=3, sticky="w", padx=12, pady=2
        )
        row += 1

        ttk.Separator(body, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=8
        )
        row += 1

        # ── Output paths ──
        Label(body, text="Output:", anchor="w", fg="#333").grid(
            row=row, column=0, sticky="w", **pad
        )
        self._output_path_var = StringVar(value="—")
        Label(body, textvariable=self._output_path_var, anchor="w", fg="#1a5276", wraplength=440).grid(
            row=row, column=1, columnspan=2, sticky="w", pady=6
        )
        row += 1

        Label(body, text="Log:", anchor="w", fg="#333").grid(
            row=row, column=0, sticky="w", **pad
        )
        self._log_path_var = StringVar(value="—")
        Label(body, textvariable=self._log_path_var, anchor="w", fg="#1a5276", wraplength=440).grid(
            row=row, column=1, columnspan=2, sticky="w", pady=6
        )
        row += 1

        ttk.Separator(body, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=8
        )
        row += 1

        # ── Summary ──
        Label(body, text="Summary:", anchor="w", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="nw", **pad
        )
        self._summary_text = Text(body, height=6, width=55, state="disabled", relief="flat",
                                   bg="#f5f5f5", font=("Consolas", 9))
        self._summary_text.grid(row=row, column=1, columnspan=2, sticky="ew", pady=6, padx=(0, 12))
        row += 1

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #

    def _select_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Master Config File",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if path:
            self._config_path_var.set(path)
            self._load_config(path)

    def _select_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Input Data File",
            filetypes=[
                ("CSV / Excel files", "*.csv *.xlsx *.xls"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._input_path_var.set(path)

    def _try_load_default_config(self) -> None:
        default = self._settings.get("local_master_config", "")
        if default and Path(default).exists():
            self._load_config(default, quiet=True)

    def _load_config(self, path: str, quiet: bool = False) -> None:
        try:
            self._config = MasterConfig(path)
            self._config_status_var.set(f"Status: Loaded ({self._config.summary()})")
            self._config_status_var_color("green")
            app_settings.save({"local_master_config": path})
        except ConfigError as exc:
            self._config = None
            self._config_status_var.set(f"Status: ERROR — {exc}")
            self._config_status_var_color("red")
            if not quiet:
                messagebox.showerror("Config Error", str(exc))

    def _config_status_var_color(self, color: str) -> None:
        # Find the config status label by scanning children — simple approach
        for widget in self.winfo_children():
            self._set_label_color(widget, self._config_status_var, color)

    def _set_label_color(self, parent: tk.Widget, var: StringVar, color: str) -> None:
        for child in parent.winfo_children():
            if isinstance(child, Label) and hasattr(child, "cget"):
                try:
                    if child.cget("textvariable") == str(var):
                        child.config(fg=color)
                except Exception:
                    pass
            self._set_label_color(child, var, color)

    def _refresh_sharepoint(self) -> None:
        if self._processing:
            return
        settings = app_settings.load()

        def _do_refresh() -> None:
            try:
                dest = Path(self._config_path_var.get() or settings.get("local_master_config", ""))
                if not dest.name.endswith(".xlsx"):
                    dest = Path(settings.get("local_master_config", "config_files/master_config.xlsx"))
                download_from_sharepoint(settings, dest)
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                app_settings.save({"last_sharepoint_sync": now})
                self.after(0, lambda: self._sp_sync_var.set(f"SharePoint sync: {now}"))
                self.after(0, lambda: self._load_config(str(dest)))
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        "SharePoint", f"Config downloaded successfully.\n{dest}"
                    ),
                )
            except Exception as exc:
                self.after(
                    0,
                    lambda: messagebox.showerror(
                        "SharePoint Error",
                        f"Could not download from SharePoint:\n{exc}\n\n"
                        "Using locally cached config file.",
                    ),
                )

        threading.Thread(target=_do_refresh, daemon=True).start()

    def _start_processing(self) -> None:
        if self._processing:
            return

        config_path = self._config_path_var.get().strip()
        input_path = self._input_path_var.get().strip()

        if not config_path:
            messagebox.showerror("Error", "Please select a Master Config file.")
            return
        if not input_path:
            messagebox.showerror("Error", "Please select an Input File.")
            return

        # Reload config if needed
        if self._config is None:
            self._load_config(config_path)
        if self._config is None:
            return  # load failed, error already shown

        fuzzy_threshold = self._fuzzy_var.get()
        config = self._config

        self._processing = True
        self._process_btn.config(state="disabled")
        self._progress_var.set(0)
        self._progress_pct_var.set("0%")
        self._status_var.set("Starting…")
        self._clear_summary()

        def _do_process() -> None:
            try:
                result = run_pipeline(
                    input_path=input_path,
                    config=config,
                    fuzzy_threshold=fuzzy_threshold,
                    progress_cb=self._on_progress,
                )
                self.after(0, lambda: self._on_complete(result))
            except (PipelineError, Exception) as exc:
                self.after(0, lambda: self._on_error(str(exc)))

        threading.Thread(target=_do_process, daemon=True).start()

    def _on_progress(self, pct: int, msg: str) -> None:
        self.after(0, lambda: self._update_progress(pct, msg))

    def _update_progress(self, pct: int, msg: str) -> None:
        self._progress_var.set(pct)
        self._progress_pct_var.set(f"{pct}%")
        self._status_var.set(msg)

    def _on_complete(self, result: dict) -> None:
        self._processing = False
        self._process_btn.config(state="normal")
        self._output_path_var.set(result["output_path"])
        self._log_path_var.set(result["log_path"])
        self._update_summary(result)
        self._status_var.set(f"Complete — {result['total_rows']:,} rows processed.")

    def _on_error(self, msg: str) -> None:
        self._processing = False
        self._process_btn.config(state="normal")
        self._status_var.set("Processing failed.")
        messagebox.showerror("Processing Error", msg)

    def _clear_summary(self) -> None:
        self._summary_text.config(state="normal")
        self._summary_text.delete("1.0", END)
        self._summary_text.config(state="disabled")

    def _update_summary(self, result: dict) -> None:
        counts = result.get("match_counts", {})
        lines = [
            f"Total rows:          {result['total_rows']:>8,}",
            f"exact-override:      {counts.get('exact-override', 0):>8,}",
            f"code-match:          {counts.get('code-match', 0):>8,}",
            f"segment-match:       {counts.get('segment-match', 0):>8,}",
            f"name-match:          {counts.get('name-match', 0):>8,}",
            f"fuzzy:               {counts.get('fuzzy', 0):>8,}",
            f"empty:               {counts.get('empty', 0):>8,}",
            f"manual-review-needed:{counts.get('manual-review-needed', 0):>8,}",
        ]
        self._summary_text.config(state="normal")
        self._summary_text.delete("1.0", END)
        self._summary_text.insert(END, "\n".join(lines))
        self._summary_text.config(state="disabled")


# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #

def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
