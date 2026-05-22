"""Main NiceGUI UI layout and event handlers for Claim Data Cleaner."""
from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog

from nicegui import ui, run

from config import settings as app_settings
from config.config_manager import (
    MasterConfig, RequestConfig, EnhertuConfig, EnhertuClaimsConfig, ConfigError
)
from pipeline.orchestrator import run_pipeline, PipelineError

logger = logging.getLogger(__name__)

# ── Mode metadata ────────────────────────────────────────────────────────────

_MODE_NAMES = {
    "claim":          "Claim Data",
    "request":        "Request Data",
    "enhertu":        "Enhertu Data",
    "enhertu_claims": "Enhertu Claims",
}

_MODE_SETTINGS_KEY = {
    "claim":          "local_master_config",
    "request":        "local_request_config",
    "enhertu":        "local_enhertu_config",
    "enhertu_claims": "local_enhertu_claims_config",
}

_MODE_CONFIG_LABEL = {
    "claim":          "Master Config File (.xlsx) — master_config.xlsx",
    "request":        "Request Config File (.xlsx) — request_comparison.xlsx",
    "enhertu":        "Enhertu Config File (.xlsx) — enhertu_config.xlsx",
    "enhertu_claims": "Enhertu Claims Config File (.xlsx) — enhertu_claims_config.xlsx",
}

_MODE_HINT = {
    "claim":
        r'Tip: Paste a OneDrive/SharePoint synced local path and press Enter — '
        r'e.g. C:\Users\you\OneDrive - AZ\configs\master_config.xlsx',
    "request":
        r'Tip: Paste a OneDrive/SharePoint synced local path and press Enter — '
        r'e.g. C:\Users\you\OneDrive - AZ\configs\request_comparison.xlsx',
    "enhertu":
        r'Tip: Paste a OneDrive/SharePoint synced local path and press Enter — '
        r'e.g. C:\Users\you\OneDrive - AZ\configs\enhertu_config.xlsx',
    "enhertu_claims":
        r'Tip: Paste a OneDrive/SharePoint synced local path and press Enter — '
        r'e.g. C:\Users\you\OneDrive - AZ\configs\enhertu_claims_config.xlsx',
}


# ── File-picker helper (tkinter in background thread) ───────────────────────

async def _pick_file(filetypes: list[tuple]) -> str:
    """Open a native OS file dialog without blocking the NiceGUI event loop."""
    result: dict[str, str] = {"path": ""}
    done = threading.Event()

    def _run() -> None:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(filetypes=filetypes)
        root.destroy()
        result["path"] = path or ""
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    while not done.is_set():
        await asyncio.sleep(0.05)
    return result["path"]


# ── Main UI class ────────────────────────────────────────────────────────────

class AppUI:
    """NiceGUI single-page application for Claim Data Cleaner."""

    def __init__(self) -> None:
        self._mode: str = "claim"
        self._config: MasterConfig | RequestConfig | EnhertuConfig | EnhertuClaimsConfig | None = None
        self._config_path: str = ""
        self._input_path: str = ""
        self._fuzzy_threshold: int = 2
        self._processing: bool = False
        self._progress_queue: queue.Queue = queue.Queue()
        self._output_folder: str = ""
        self._settings = app_settings.load()

        self._build_page()
        self._try_load_default_config()

    # ── Page construction ────────────────────────────────────────────────────

    def _build_page(self) -> None:
        with ui.row().classes("w-full items-center justify-between").style(
            "padding: 20px 28px 12px 28px;"
        ):
            ui.label("🧹 Claim Data Cleaner").style(
                "font-size: 22px; font-weight: 700; color: #1D1D1F;"
            )
            ui.label("v1.0").style("font-size: 13px; color: #86868B;")

        with ui.column().classes("w-full").style("padding: 0 28px 28px 28px; gap: 0;"):
            self._build_mode_card()
            self._build_config_card()
            self._build_process_card()
            self._build_results_card()

    # ── Card 1: Mode Selector ────────────────────────────────────────────────

    def _build_mode_card(self) -> None:
        with ui.card().classes("card w-full"):
            ui.label("Step 1: Select Processing Mode").style(
                "font-size: 15px; font-weight: 700; color: #1565C0;"
            )
            ui.separator().style("margin: 8px 0 14px 0;")

            # NiceGUI ui.toggle → Quasar QBtnToggle with built-in selected/unselected state
            self._mode_toggle = (
                ui.toggle(
                    _MODE_NAMES,
                    value="claim",
                    on_change=self._on_mode_change,
                )
                .props("no-caps color=primary")
                .style("font-size: 14px; font-weight: 600;")
            )

            # Prominent active-mode indicator so there is zero ambiguity
            self._active_mode_label = ui.label("▶  Active mode: Claim Data").style(
                "font-size: 14px; font-weight: 700; color: #1565C0; margin-top: 10px;"
            )

    # ── Card 2: Configuration ────────────────────────────────────────────────

    def _build_config_card(self) -> None:
        with ui.card().classes("card w-full"):
            ui.label("Step 2: Select Configuration File").style(
                "font-size: 15px; font-weight: 700; color: #1565C0;"
            )
            ui.separator().style("margin: 8px 0 12px 0;")

            self._config_file_label = ui.label(_MODE_CONFIG_LABEL["claim"]).style(
                "font-size: 13px; color: #86868B; margin-bottom: 6px;"
            )

            with ui.row().classes("w-full items-center").style("gap: 8px; margin-bottom: 4px;"):
                self._config_path_input = (
                    ui.input(placeholder="Paste file path or click Browse…")
                    .style(
                        "flex: 1; font-size: 13px; background: #F2F2F7; "
                        "border: none; border-radius: 8px; padding: 10px 14px;"
                    )
                    .on("keydown.enter", self._on_config_path_entered)
                )
                ui.button("📁 Browse…", on_click=self._pick_config).style(
                    "padding: 8px 16px; font-size: 13px; background: white; "
                    "color: #007AFF; border: 1px solid #007AFF; border-radius: 8px;"
                )

            self._config_hint_label = ui.label(_MODE_HINT["claim"]).style(
                "font-size: 11px; color: #AEAEB2; margin-bottom: 10px;"
            )

            self._config_status_label = ui.label("").style(
                "font-size: 13px; color: #86868B; min-height: 18px;"
            )

            self._debug_expansion = ui.expansion(
                "🔍 Debug — preview loaded config data", value=False
            ).style("margin-top: 10px; font-size: 13px; color: #86868B;")
            with self._debug_expansion:
                self._debug_container = ui.column().classes("w-full").style("gap: 8px;")

    # ── Card 3: Process Data ─────────────────────────────────────────────────

    def _build_process_card(self) -> None:
        with ui.card().classes("card w-full"):
            ui.label("Step 3: Select Input File & Process").style(
                "font-size: 15px; font-weight: 700; color: #1565C0;"
            )
            ui.separator().style("margin: 8px 0 12px 0;")

            ui.label("Input Data File (.csv or .xlsx)").style(
                "font-size: 13px; color: #86868B; margin-bottom: 6px;"
            )
            with ui.element("div").classes("file-box w-full"):
                self._input_filename_label = ui.label("No file selected").style(
                    "flex: 1; color: #1D1D1F; font-size: 14px;"
                )
                ui.button("Change", on_click=self._pick_input).style(
                    "padding: 6px 14px; font-size: 13px; background: white; "
                    "color: #007AFF; border: 1px solid #007AFF; border-radius: 8px;"
                )

            ui.separator().style("margin: 12px 0;")

            with ui.row().classes("items-center").style("gap: 12px; margin-bottom: 16px;"):
                ui.label("Fuzzy Match Threshold:").style("font-size: 14px; color: #1D1D1F;")
                ui.button("−", on_click=self._decrement_threshold).style(
                    "width: 32px; height: 32px; padding: 0; font-size: 18px; "
                    "background: #F2F2F7; color: #1D1D1F; border-radius: 6px; border: none;"
                )
                self._threshold_label = ui.label(str(self._fuzzy_threshold)).style(
                    "font-size: 16px; font-weight: 600; min-width: 24px; text-align: center;"
                )
                ui.button("+", on_click=self._increment_threshold).style(
                    "width: 32px; height: 32px; padding: 0; font-size: 18px; "
                    "background: #F2F2F7; color: #1D1D1F; border-radius: 6px; border: none;"
                )
                ui.label("(1–3 characters)").style("font-size: 13px; color: #86868B;")

            self._process_btn = ui.button(
                "▶  Process File", on_click=self._on_process
            ).style(
                "width: 100%; padding: 14px; font-size: 16px; font-weight: 600; "
                "background: #8E8E93; color: white; border-radius: 10px; border: none; "
                "cursor: not-allowed; margin-bottom: 16px; opacity: 0.6;"
            )

            self._progress_section = ui.column().classes("w-full").style("gap: 6px;")
            with self._progress_section:
                self._progress_bar = ui.linear_progress(value=0).style(
                    "width: 100%; height: 8px; border-radius: 4px;"
                )
                self._status_label = ui.label("").style("font-size: 13px; color: #86868B;")
            self._progress_section.set_visibility(False)

    # ── Card 4: Results ──────────────────────────────────────────────────────

    def _build_results_card(self) -> None:
        self._results_card = ui.card().classes("card w-full")
        with self._results_card:
            ui.label("✅ Results").style(
                "font-size: 17px; font-weight: 600; color: #1D1D1F;"
            )
            ui.separator().style("margin: 8px 0 12px 0;")

            # Institution / Service Provider match chips (Claim + Request + Enhertu Claims)
            self._institution_summary_row = ui.column().style("margin-bottom: 8px;")
            with self._institution_summary_row:
                ui.label("Institution Match Summary:").style(
                    "font-size: 14px; font-weight: 600; color: #1D1D1F; margin-bottom: 8px;"
                )
                with ui.row().classes("items-center").style("gap: 8px; flex-wrap: wrap;"):
                    self._chip_exact   = ui.label("exact-override: 0").classes("chip-blue")
                    self._chip_code    = ui.label("code-match: 0").classes("chip-blue")
                    self._chip_segment = ui.label("segment-match: 0").classes("chip-blue")
                    self._chip_name    = ui.label("name-match: 0").classes("chip-green")
                    self._chip_fuzzy   = ui.label("fuzzy: 0").classes("chip-orange")
                    self._chip_empty   = ui.label("empty: 0").classes("chip-orange")
                    self._chip_manual  = ui.label("manual-review-needed: 0").classes("chip-red")

            # Insurance match chips (Request + Enhertu + Enhertu Claims)
            self._insurance_summary_row = ui.column().style("margin-bottom: 8px;")
            with self._insurance_summary_row:
                ui.label("Insurance Match Summary:").style(
                    "font-size: 14px; font-weight: 600; color: #1D1D1F; margin-bottom: 8px;"
                )
                with ui.row().classes("items-center").style("gap: 8px; flex-wrap: wrap;"):
                    self._chip_ins_exact        = ui.label("exact: 0").classes("chip-blue")
                    self._chip_ins_stripped     = ui.label("exact-stripped: 0").classes("chip-blue")
                    self._chip_ins_code         = ui.label("code-match: 0").classes("chip-blue")
                    self._chip_ins_nomatch      = ui.label("no-match: 0").classes("chip-orange")
            self._insurance_summary_row.set_visibility(False)

            # Indication match chips (Enhertu + Enhertu Claims)
            self._indication_summary_row = ui.column().style("margin-bottom: 8px;")
            with self._indication_summary_row:
                ui.label("Indication Match Summary:").style(
                    "font-size: 14px; font-weight: 600; color: #1D1D1F; margin-bottom: 8px;"
                )
                with ui.row().classes("items-center").style("gap: 8px; flex-wrap: wrap;"):
                    self._chip_ind_exact   = ui.label("exact: 0").classes("chip-blue")
                    self._chip_ind_nomatch = ui.label("no-match: 0").classes("chip-orange")
            self._indication_summary_row.set_visibility(False)

            self._output_path_label = ui.label("📄 Output: —").style(
                "font-size: 13px; color: #1D1D1F; word-break: break-all;"
            )
            self._log_path_label = ui.label("📋 Log: —").style(
                "font-size: 13px; color: #1D1D1F; word-break: break-all;"
            )
            self._extra_log_label = ui.label("").style(
                "font-size: 13px; color: #1D1D1F; word-break: break-all; margin-bottom: 4px;"
            )
            self._extra_log_label.set_visibility(False)
            self._extra_log2_label = ui.label("").style(
                "font-size: 13px; color: #1D1D1F; word-break: break-all; margin-bottom: 12px;"
            )
            self._extra_log2_label.set_visibility(False)

            ui.button("📂 Open Output Folder", on_click=self._on_open_folder).style(
                "padding: 8px 16px; font-size: 13px; background: white; "
                "color: #007AFF; border: 1px solid #007AFF; border-radius: 8px;"
            )

        self._results_card.set_visibility(False)

    # ── Mode change handler ──────────────────────────────────────────────────

    def _on_mode_change(self, e) -> None:
        """Called when the ui.toggle value changes."""
        new_mode = e.value
        if new_mode is None or new_mode == self._mode:
            return
        self._set_mode(new_mode)

    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        mode_name = _MODE_NAMES.get(mode, mode)
        self._active_mode_label.set_text(f"▶  Active mode: {mode_name}")
        self._mode_toggle.set_value(mode)

        self._config_file_label.set_text(_MODE_CONFIG_LABEL[mode])
        self._config_hint_label.set_text(_MODE_HINT[mode])

        # Clear config state and reload default for new mode
        self._config = None
        self._config_path = ""
        self._config_status_label.set_text("")
        self._debug_container.clear()
        self._update_process_btn_state()

        default_path = self._settings.get(_MODE_SETTINGS_KEY[mode], "")
        if default_path and Path(default_path).exists():
            self._config_path_input.set_value(default_path)
            self._load_config(default_path, quiet=True)
        else:
            self._config_path_input.set_value("")

    # ── Config loading ───────────────────────────────────────────────────────

    def _load_config(self, path: str, quiet: bool = False) -> None:
        path = path.strip().strip('"')
        if not path:
            return
        try:
            if self._mode == "claim":
                self._config = MasterConfig(path)
                c = self._config
                status = (
                    f"✅  indication_rule: {len(c.indication_rules):,} rows  |  "
                    f"name_rule: {len(c.name_rules):,} rows  |  "
                    f"dosage_rule: {len(c.dosage_rules):,} rows  |  "
                    f"BU_rule: {len(c.bu_rules):,} rows  |  "
                    f"{c.hcp_sheet_name}: {len(c.hcp_universe):,} rows"
                )
                app_settings.save({"local_master_config": path})
            elif self._mode == "request":
                self._config = RequestConfig(path)
                c = self._config
                status = (
                    f"✅  r_indication_rule: {len(c.indication_rules):,} rows  |  "
                    f"r_insurance_rule: {len(c.insurance_rules):,} rows  |  "
                    f"r_BU_rule: {len(c.bu_rules):,} rows  |  "
                    f"r_name_rule: {len(c.name_rules):,} rows"
                )
                app_settings.save({"local_request_config": path})
            elif self._mode == "enhertu":
                self._config = EnhertuConfig(path)
                c = self._config
                status = (
                    f"✅  insurance_rule: {len(c.insurance_rules):,} rows  |  "
                    f"indication_rule: {len(c.indication_rules):,} rows"
                )
                app_settings.save({"local_enhertu_config": path})
            else:  # enhertu_claims
                self._config = EnhertuClaimsConfig(path)
                c = self._config
                status = (
                    f"✅  insurance_rule: {len(c.insurance_rules):,} rows  |  "
                    f"indication_rule: {len(c.indication_rules):,} rows  |  "
                    f"name_rule: {len(c.name_rules):,} rows"
                )
                app_settings.save({"local_enhertu_claims_config": path})

            self._config_path = path
            self._config_status_label.set_text(status)
            self._config_status_label.style("font-size: 13px; color: #28A745;")
            self._config_path_input.set_value(path)
            self._build_debug_preview()
        except ConfigError as exc:
            self._config = None
            self._config_status_label.set_text(f"✗ Error: {exc}")
            self._config_status_label.style("font-size: 13px; color: #FF3B30;")
            if not quiet:
                ui.notify(str(exc), type="negative", timeout=8000)
        self._update_process_btn_state()

    def _try_load_default_config(self) -> None:
        default = self._settings.get(_MODE_SETTINGS_KEY[self._mode], "")
        if default and Path(default).exists():
            self._config_path_input.set_value(default)
            self._load_config(default, quiet=True)

    async def _on_config_path_entered(self) -> None:
        path = self._config_path_input.value or ""
        if path.strip():
            self._load_config(path)

    async def _pick_config(self) -> None:
        path = await _pick_file([("Excel files", "*.xlsx *.xls"), ("All files", "*.*")])
        if path:
            self._config_path_input.set_value(path)
            self._load_config(path)

    # ── Debug preview ────────────────────────────────────────────────────────

    def _build_debug_preview(self) -> None:
        if not self._config:
            return
        self._debug_container.clear()
        with self._debug_container:
            for sheet_name, preview_df in self._config.sheet_previews().items():
                ui.label(f"📋 {sheet_name} (first 3 rows):").style(
                    "font-size: 12px; font-weight: 600; color: #1D1D1F; margin-top: 8px;"
                )
                headers = list(preview_df.columns)
                rows = preview_df.values.tolist()
                header_html = "".join(
                    f"<th style='padding:4px 10px;background:#F2F2F7;"
                    f"border-bottom:1px solid #D1D1D6;font-weight:600;font-size:12px;"
                    f"text-align:left;white-space:nowrap;'>{h}</th>"
                    for h in headers
                )
                body_html = ""
                for r in rows:
                    cells = "".join(
                        f"<td style='padding:4px 10px;border-bottom:1px solid #F2F2F7;"
                        f"font-size:12px;white-space:nowrap;max-width:240px;"
                        f"overflow:hidden;text-overflow:ellipsis;'>"
                        f"{str(v)[:100]}</td>"
                        for v in r
                    )
                    body_html += f"<tr>{cells}</tr>"
                table_html = (
                    "<div style='overflow-x:auto;'>"
                    "<table style='border-collapse:collapse;width:100%;'>"
                    f"<thead><tr>{header_html}</tr></thead>"
                    f"<tbody>{body_html}</tbody></table></div>"
                )
                ui.html(table_html)

    # ── Input file picker ────────────────────────────────────────────────────

    async def _pick_input(self) -> None:
        path = await _pick_file([
            ("CSV / Excel files", "*.csv *.xlsx *.xls"),
            ("All files", "*.*"),
        ])
        if path:
            self._input_path = path
            self._input_filename_label.set_text(Path(path).name)
            self._update_process_btn_state()

    # ── Fuzzy threshold controls ─────────────────────────────────────────────

    def _increment_threshold(self) -> None:
        if self._fuzzy_threshold < 3:
            self._fuzzy_threshold += 1
            self._threshold_label.set_text(str(self._fuzzy_threshold))

    def _decrement_threshold(self) -> None:
        if self._fuzzy_threshold > 1:
            self._fuzzy_threshold -= 1
            self._threshold_label.set_text(str(self._fuzzy_threshold))

    # ── Process button state ─────────────────────────────────────────────────

    def _update_process_btn_state(self) -> None:
        ready = bool(self._config and self._input_path and not self._processing)
        if ready:
            self._process_btn.style(
                "width: 100%; padding: 14px; font-size: 16px; font-weight: 600; "
                "background: #34C759; color: white; border-radius: 10px; border: none; "
                "cursor: pointer; margin-bottom: 16px; opacity: 1;"
            )
        else:
            self._process_btn.style(
                "width: 100%; padding: 14px; font-size: 16px; font-weight: 600; "
                "background: #8E8E93; color: white; border-radius: 10px; border: none; "
                "cursor: not-allowed; margin-bottom: 16px; opacity: 0.6;"
            )

    # ── Main processing flow ─────────────────────────────────────────────────

    async def _on_process(self) -> None:
        if self._processing:
            return
        if not self._config:
            ui.notify("Please select a Config file first.", type="negative")
            return
        if not self._input_path:
            ui.notify("Please select an Input Data file first.", type="negative")
            return

        self._processing = True
        self._update_process_btn_state()
        self._results_card.set_visibility(False)
        self._progress_section.set_visibility(True)
        self._progress_bar.set_value(0)
        self._status_label.set_text("Starting…")

        while not self._progress_queue.empty():
            try:
                self._progress_queue.get_nowait()
            except queue.Empty:
                break

        config = self._config
        input_path = self._input_path
        fuzzy_threshold = self._fuzzy_threshold
        mode = self._mode
        prog_queue = self._progress_queue

        def _progress_cb(pct: int, msg: str) -> None:
            prog_queue.put((pct, msg))

        def _poll() -> None:
            while not prog_queue.empty():
                try:
                    pct, msg = prog_queue.get_nowait()
                    self._progress_bar.set_value(pct / 100)
                    self._status_label.set_text(msg)
                except queue.Empty:
                    break

        timer = ui.timer(0.1, _poll)

        try:
            result = await run.io_bound(
                run_pipeline, input_path, config, fuzzy_threshold, _progress_cb, mode,
            )
            timer.cancel()
            self._on_complete(result)
        except Exception as exc:
            timer.cancel()
            self._on_error(str(exc))

    def _on_complete(self, result: dict) -> None:
        self._processing = False
        self._update_process_btn_state()
        self._progress_bar.set_value(1.0)
        self._status_label.set_text(
            f"Complete — {result['total_rows']:,} rows processed."
        )

        mode = self._mode

        # Institution/Service Provider chips (Claim + Request + Enhertu Claims)
        is_institution = mode in ("claim", "request", "enhertu_claims")
        self._institution_summary_row.set_visibility(is_institution)
        if is_institution:
            counts = result.get("match_counts", {})
            self._chip_exact.set_text(f"exact-override: {counts.get('exact-override', 0):,}")
            self._chip_code.set_text(f"code-match: {counts.get('code-match', 0):,}")
            self._chip_segment.set_text(f"segment-match: {counts.get('segment-match', 0):,}")
            self._chip_name.set_text(f"name-match: {counts.get('name-match', 0):,}")
            self._chip_fuzzy.set_text(f"fuzzy: {counts.get('fuzzy', 0):,}")
            self._chip_empty.set_text(f"empty: {counts.get('empty', 0):,}")
            self._chip_manual.set_text(
                f"manual-review-needed: {counts.get('manual-review-needed', 0):,}"
            )

        # Insurance chips (Request + Enhertu + Enhertu Claims)
        is_insurance = mode in ("request", "enhertu", "enhertu_claims")
        self._insurance_summary_row.set_visibility(is_insurance)
        if is_insurance:
            ins = result.get("insurance_counts", {})
            self._chip_ins_exact.set_text(f"exact: {ins.get('exact', 0):,}")
            self._chip_ins_stripped.set_text(f"exact-stripped: {ins.get('exact-stripped', 0):,}")
            self._chip_ins_code.set_text(f"code-match: {ins.get('code-match', 0):,}")
            self._chip_ins_nomatch.set_text(f"no-match: {ins.get('no-match', 0):,}")

        # Indication chips (Enhertu + Enhertu Claims)
        is_indication = mode in ("enhertu", "enhertu_claims")
        self._indication_summary_row.set_visibility(is_indication)
        if is_indication:
            ind = result.get("indication_counts", {})
            self._chip_ind_exact.set_text(f"exact: {ind.get('exact', 0):,}")
            self._chip_ind_nomatch.set_text(f"no-match: {ind.get('no-match', 0):,}")

        # Output and log paths
        self._output_path_label.set_text(f"📄 Output: {result['output_path']}")
        self._output_folder = str(Path(result["output_path"]).parent)

        if mode == "claim":
            self._log_path_label.set_text(f"📋 Log: {result['log_path']}")
            self._extra_log_label.set_visibility(False)
            self._extra_log2_label.set_visibility(False)
        elif mode == "request":
            self._log_path_label.set_text(f"📋 Institution Log: {result['log_path']}")
            ins_log = result.get("insurance_log_path", "")
            self._extra_log_label.set_text(f"📋 Insurance Log: {ins_log}")
            self._extra_log_label.set_visibility(True)
            self._extra_log2_label.set_visibility(False)
        elif mode == "enhertu":
            ins_log = result.get("insurance_log_path", "")
            ind_log = result.get("indication_log_path", "")
            self._log_path_label.set_text(f"📋 Insurance Log: {ins_log}")
            self._extra_log_label.set_text(f"📋 Indication Log: {ind_log}")
            self._extra_log_label.set_visibility(True)
            self._extra_log2_label.set_visibility(False)
        else:  # enhertu_claims
            inst_log = result.get("institution_log_path", "")
            ins_log = result.get("insurance_log_path", "")
            ind_log = result.get("indication_log_path", "")
            self._log_path_label.set_text(f"📋 Institution Log: {inst_log}")
            self._extra_log_label.set_text(f"📋 Insurance Log: {ins_log}")
            self._extra_log_label.set_visibility(True)
            self._extra_log2_label.set_text(f"📋 Indication Log: {ind_log}")
            self._extra_log2_label.set_visibility(True)

        self._results_card.set_visibility(True)

        ui.notify(
            f"Processing complete! {result['total_rows']:,} rows → "
            f"{Path(result['output_path']).name}",
            type="positive",
        )

    def _on_error(self, msg: str) -> None:
        self._processing = False
        self._update_process_btn_state()
        self._status_label.set_text("Processing failed.")
        ui.notify(f"Error: {msg}", type="negative", timeout=10000)
        logger.error("Pipeline error: %s", msg)

    # ── Open output folder ───────────────────────────────────────────────────

    def _on_open_folder(self) -> None:
        if self._output_folder and Path(self._output_folder).exists():
            try:
                os.startfile(self._output_folder)
            except AttributeError:
                import subprocess
                subprocess.Popen(["xdg-open", self._output_folder])
