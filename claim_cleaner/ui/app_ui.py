"""Main NiceGUI UI layout and all event handlers."""
from __future__ import annotations

import asyncio
import os
import queue
import threading
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog

from nicegui import ui, app as nicegui_app, run

from config import settings as app_settings
from config.config_manager import MasterConfig, ConfigError, download_from_sharepoint
from pipeline.orchestrator import run_pipeline, PipelineError


async def _pick_file(filetypes: list[tuple]) -> str:
    """Open a native file picker dialog in a background thread."""
    result = {'path': ''}
    done = threading.Event()

    def _run():
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        path = filedialog.askopenfilename(filetypes=filetypes)
        root.destroy()
        result['path'] = path or ''
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    while not done.is_set():
        await asyncio.sleep(0.05)
    return result['path']


class AppUI:
    """NiceGUI-based UI for Claim Data Cleaner."""

    def __init__(self) -> None:
        self._config: MasterConfig | None = None
        self._config_path: str = ''
        self._input_path: str = ''
        self._fuzzy_threshold: int = 2
        self._processing: bool = False
        self._progress_queue: queue.Queue = queue.Queue()
        self._settings = app_settings.load()

        self._build_page()
        self._try_load_default_config()

    def _build_page(self) -> None:
        """Construct the full page layout."""
        # ── Page title row ──
        with ui.row().classes('w-full items-center justify-between').style(
            'padding: 16px 24px 8px 24px;'
        ):
            ui.label('🧹 Claim Data Cleaner').classes('section-header').style(
                'font-size: 22px; font-weight: 700; color: #1D1D1F;'
            )
            ui.label('v1.0').classes('sublabel')

        # Scrollable content area
        with ui.column().classes('w-full').style('padding: 0 24px 24px 24px; gap: 0;'):
            self._build_config_card()
            self._build_process_card()
            self._build_results_card()

    def _build_config_card(self) -> None:
        """Card 1 — Configuration section."""
        with ui.card().classes('card w-full'):
            ui.label('⚙️ Configuration').classes('section-header')
            ui.separator().style('margin: 8px 0;')

            # Master Config File
            ui.label('Master Config File').classes('sublabel').style('margin-bottom: 6px;')
            with ui.element('div').classes('file-box w-full'):
                self._config_filename_label = ui.label('No file selected').style(
                    'flex: 1; color: #1D1D1F; font-size: 14px;'
                )
                ui.button('Change', on_click=self._pick_config).classes('btn-secondary').style(
                    'padding: 6px 14px; font-size: 13px;'
                )

            # Config status
            self._config_status_label = ui.label('').classes('sublabel').style(
                'margin-top: 6px; color: #86868B;'
            )

            ui.separator().style('margin: 12px 0;')

            # SharePoint sync row
            with ui.row().classes('items-center').style('gap: 16px;'):
                ui.button(
                    '🔄 Sync from SharePoint',
                    on_click=self._on_sharepoint_sync
                ).classes('btn-secondary').style('padding: 8px 16px; font-size: 13px;')

                last_sync = self._settings.get('last_sharepoint_sync', '')
                self._sync_label = ui.label(
                    f'Last sync: {last_sync or "never"}'
                ).classes('sublabel')

    def _build_process_card(self) -> None:
        """Card 2 — Process Data section."""
        with ui.card().classes('card w-full'):
            ui.label('📊 Process Data').classes('section-header')
            ui.separator().style('margin: 8px 0;')

            # Input Data File
            ui.label('Input Data File').classes('sublabel').style('margin-bottom: 6px;')
            with ui.element('div').classes('file-box w-full'):
                self._input_filename_label = ui.label('No file selected').style(
                    'flex: 1; color: #1D1D1F; font-size: 14px;'
                )
                ui.button('Change', on_click=self._pick_input).classes('btn-secondary').style(
                    'padding: 6px 14px; font-size: 13px;'
                )

            ui.separator().style('margin: 12px 0;')

            # Fuzzy threshold row
            with ui.row().classes('items-center').style('gap: 12px; margin-bottom: 16px;'):
                ui.label('Fuzzy Match Threshold:').style('font-size: 14px; color: #1D1D1F;')
                self._minus_btn = ui.button(
                    '−', on_click=self._decrement_threshold
                ).style(
                    'width: 32px; height: 32px; padding: 0; font-size: 16px; '
                    'background: #F2F2F7; color: #1D1D1F; border-radius: 6px; border: none;'
                )
                self._threshold_label = ui.label(str(self._fuzzy_threshold)).style(
                    'font-size: 16px; font-weight: 600; min-width: 24px; text-align: center;'
                )
                self._plus_btn = ui.button(
                    '+', on_click=self._increment_threshold
                ).style(
                    'width: 32px; height: 32px; padding: 0; font-size: 16px; '
                    'background: #F2F2F7; color: #1D1D1F; border-radius: 6px; border: none;'
                )
                ui.label('(1–3 chars)').classes('sublabel')

            # Process button
            self._process_btn = ui.button(
                '▶ Process File',
                on_click=self._on_process
            ).style(
                'width: 100%; padding: 14px; font-size: 16px; font-weight: 600; '
                'background: #34C759; color: white; border-radius: 10px; border: none; '
                'cursor: pointer; margin-bottom: 16px;'
            )
            self._update_process_btn_state()

            # Progress section (hidden until processing)
            self._progress_section = ui.column().classes('w-full').style('gap: 8px;')
            with self._progress_section:
                self._progress_bar = ui.linear_progress(value=0).style(
                    'width: 100%; height: 8px; border-radius: 4px;'
                )
                self._status_label = ui.label('').classes('progress-label')
            self._progress_section.set_visibility(False)

    def _build_results_card(self) -> None:
        """Card 3 — Results section (hidden until processing completes)."""
        self._results_card = ui.card().classes('card w-full')
        with self._results_card:
            ui.label('✅ Results').classes('section-header')
            ui.separator().style('margin: 8px 0;')

            # Match summary chips
            ui.label('Match Summary:').style(
                'font-size: 14px; font-weight: 600; color: #1D1D1F; margin-bottom: 8px;'
            )
            with ui.row().classes('items-center').style('gap: 8px; flex-wrap: wrap; margin-bottom: 16px;'):
                self._chip_exact = ui.label('Exact/Override: 0').classes('chip-blue')
                self._chip_code = ui.label('Code Match: 0').classes('chip-blue')
                self._chip_fuzzy = ui.label('Fuzzy: 0').classes('chip-orange')
                self._chip_manual = ui.label('Manual Review: 0').classes('chip-red')

            # Output paths
            self._output_path_label = ui.label('📄 Output: —').style(
                'font-size: 13px; color: #1D1D1F; word-break: break-all;'
            )
            self._log_path_label = ui.label('📋 Log: —').style(
                'font-size: 13px; color: #1D1D1F; word-break: break-all; margin-bottom: 12px;'
            )

            # Open folder button
            self._open_folder_btn = ui.button(
                '📂 Open Output Folder',
                on_click=self._on_open_folder
            ).classes('btn-secondary').style('padding: 8px 16px; font-size: 13px;')

        self._results_card.set_visibility(False)

    # ------------------------------------------------------------------ #
    # File pickers
    # ------------------------------------------------------------------ #

    async def _pick_config(self) -> None:
        path = await _pick_file([
            ('Excel files', '*.xlsx *.xls'),
            ('All files', '*.*'),
        ])
        if path:
            self._config_path = path
            self._config_filename_label.set_text(Path(path).name)
            self._load_config(path)

    async def _pick_input(self) -> None:
        path = await _pick_file([
            ('CSV / Excel files', '*.csv *.xlsx *.xls'),
            ('All files', '*.*'),
        ])
        if path:
            self._input_path = path
            self._input_filename_label.set_text(Path(path).name)
            self._update_process_btn_state()

    # ------------------------------------------------------------------ #
    # Config loading
    # ------------------------------------------------------------------ #

    def _load_config(self, path: str, quiet: bool = False) -> None:
        try:
            self._config = MasterConfig(path)
            summary = self._config.summary()
            self._config_status_label.set_text(f'✓ Loaded — {summary}')
            self._config_status_label.style('color: #28A745; font-size: 13px;')
            app_settings.save({'local_master_config': path})
        except ConfigError as exc:
            self._config = None
            self._config_status_label.set_text(f'✗ Error: {exc}')
            self._config_status_label.style('color: #FF3B30; font-size: 13px;')
            if not quiet:
                ui.notify(str(exc), type='negative')
        self._update_process_btn_state()

    def _try_load_default_config(self) -> None:
        default = self._settings.get('local_master_config', '')
        if default and Path(default).exists():
            self._config_path = default
            self._config_filename_label.set_text(Path(default).name)
            self._load_config(default, quiet=True)

    # ------------------------------------------------------------------ #
    # Fuzzy threshold controls
    # ------------------------------------------------------------------ #

    def _increment_threshold(self) -> None:
        if self._fuzzy_threshold < 3:
            self._fuzzy_threshold += 1
            self._threshold_label.set_text(str(self._fuzzy_threshold))

    def _decrement_threshold(self) -> None:
        if self._fuzzy_threshold > 1:
            self._fuzzy_threshold -= 1
            self._threshold_label.set_text(str(self._fuzzy_threshold))

    # ------------------------------------------------------------------ #
    # Process button state
    # ------------------------------------------------------------------ #

    def _update_process_btn_state(self) -> None:
        ready = bool(self._config and self._input_path and not self._processing)
        if ready:
            self._process_btn.style(
                'width: 100%; padding: 14px; font-size: 16px; font-weight: 600; '
                'background: #34C759; color: white; border-radius: 10px; border: none; '
                'cursor: pointer; margin-bottom: 16px; opacity: 1;'
            )
        else:
            self._process_btn.style(
                'width: 100%; padding: 14px; font-size: 16px; font-weight: 600; '
                'background: #8E8E93; color: white; border-radius: 10px; border: none; '
                'cursor: not-allowed; margin-bottom: 16px; opacity: 0.6;'
            )

    # ------------------------------------------------------------------ #
    # SharePoint sync
    # ------------------------------------------------------------------ #

    async def _on_sharepoint_sync(self) -> None:
        if self._processing:
            return

        settings = app_settings.load()
        dest_path_str = settings.get('local_master_config', 'config_files/master_config.xlsx')
        dest_path = Path(dest_path_str)

        ui.notify('Syncing from SharePoint…', type='warning')

        def _do_sync():
            download_from_sharepoint(settings, dest_path)

        try:
            await run.io_bound(_do_sync)
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            app_settings.save({'last_sharepoint_sync': now})
            self._sync_label.set_text(f'Last sync: {now}')
            self._config_path = str(dest_path)
            self._config_filename_label.set_text(dest_path.name)
            self._load_config(str(dest_path))
            ui.notify('SharePoint sync complete!', type='positive')
        except Exception as exc:
            ui.notify(f'SharePoint sync failed: {exc}', type='negative')

    # ------------------------------------------------------------------ #
    # Main processing flow
    # ------------------------------------------------------------------ #

    async def _on_process(self) -> None:
        if self._processing:
            return

        if not self._config:
            ui.notify('Please select a Master Config file first.', type='negative')
            return
        if not self._input_path:
            ui.notify('Please select an Input Data file first.', type='negative')
            return

        self._processing = True
        self._update_process_btn_state()

        # Clear results and show progress
        self._results_card.set_visibility(False)
        self._progress_section.set_visibility(True)
        self._progress_bar.set_value(0)
        self._status_label.set_text('Starting…')

        # Clear the queue
        while not self._progress_queue.empty():
            try:
                self._progress_queue.get_nowait()
            except queue.Empty:
                break

        config = self._config
        input_path = self._input_path
        fuzzy_threshold = self._fuzzy_threshold
        prog_queue = self._progress_queue

        def _progress_cb(pct: int, msg: str) -> None:
            prog_queue.put((pct, msg))

        # Start polling timer
        poll_timer = ui.timer(0.1, self._drain_progress_queue)

        def _run_pipeline():
            return run_pipeline(
                input_path=input_path,
                config=config,
                fuzzy_threshold=fuzzy_threshold,
                progress_cb=_progress_cb,
            )

        try:
            result = await run.io_bound(_run_pipeline)
            poll_timer.cancel()
            # Drain remaining queue entries
            await self._drain_progress_queue()
            self._on_complete(result)
        except Exception as exc:
            poll_timer.cancel()
            self._on_error(str(exc))
        finally:
            self._processing = False
            self._update_process_btn_state()

    async def _drain_progress_queue(self) -> None:
        """Drain the progress queue and update the UI."""
        try:
            while True:
                pct, msg = self._progress_queue.get_nowait()
                self._progress_bar.set_value(pct / 100)
                self._status_label.set_text(msg)
        except queue.Empty:
            pass

    def _on_complete(self, result: dict) -> None:
        """Update the UI after successful processing."""
        self._progress_bar.set_value(1.0)
        self._status_label.set_text(
            f'Complete — {result["total_rows"]:,} rows processed.'
        )

        counts = result.get('match_counts', {})
        exact_count = counts.get('exact-override', 0) + counts.get('segment-match', 0)
        code_count = counts.get('code-match', 0) + counts.get('name-match', 0)
        fuzzy_count = counts.get('fuzzy', 0)
        manual_count = counts.get('manual-review-needed', 0)

        self._chip_exact.set_text(f'Exact/Override: {exact_count}')
        self._chip_code.set_text(f'Code Match: {code_count}')
        self._chip_fuzzy.set_text(f'Fuzzy: {fuzzy_count}')
        self._chip_manual.set_text(f'Manual Review: {manual_count}')

        self._output_path_label.set_text(f'📄 Output: {result["output_path"]}')
        self._log_path_label.set_text(f'📋 Log: {result["log_path"]}')
        self._result_output_path = result['output_path']

        self._results_card.set_visibility(True)
        ui.notify(
            f'Processing complete! {result["total_rows"]:,} rows processed.',
            type='positive'
        )

    def _on_error(self, msg: str) -> None:
        """Update the UI after a processing error."""
        self._status_label.set_text('Processing failed.')
        ui.notify(f'Error: {msg}', type='negative')

    def _on_open_folder(self) -> None:
        """Open the output folder in the system file manager."""
        try:
            output_path = getattr(self, '_result_output_path', '')
            if output_path:
                folder = str(Path(output_path).parent)
                if os.name == 'nt':
                    os.startfile(folder)
                elif os.name == 'posix':
                    import subprocess
                    subprocess.Popen(['xdg-open', folder])
        except Exception as exc:
            ui.notify(f'Could not open folder: {exc}', type='negative')
