"""Main processing pipeline orchestrator."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from config.config_manager import MasterConfig
from output.writer import write_output
from output.log_writer import write_match_log
from pipeline.step_indication import IndicationStep
from pipeline.step_provider import ProviderStep
from pipeline.step_dosage import DosageStep
from pipeline.step_bu import BUStep
from pipeline.utils import load_input_file, OUTPUT_COLUMNS, InputError

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]  # (percent 0-100, message)


class PipelineError(Exception):
    """Fatal error that stops the pipeline."""


def run_pipeline(
    input_path: str | Path,
    config: MasterConfig,
    fuzzy_threshold: int = 2,
    progress_cb: Optional[ProgressCallback] = None,
) -> dict:
    """
    Execute the full cleaning pipeline.

    Returns a summary dict with output paths and match type counts.
    Raises PipelineError on fatal errors.
    """

    def _progress(pct: int, msg: str) -> None:
        if progress_cb:
            progress_cb(pct, msg)
        logger.info("[%d%%] %s", pct, msg)

    input_path = Path(input_path)

    # ------------------------------------------------------------------ #
    # Step 0: Load input
    # ------------------------------------------------------------------ #
    _progress(5, "Loading input file…")
    try:
        df = load_input_file(input_path)
    except InputError as exc:
        raise PipelineError(str(exc)) from exc

    _progress(10, f"Loaded {len(df):,} rows.")

    # ------------------------------------------------------------------ #
    # Step 1: Add RowID
    # ------------------------------------------------------------------ #
    _progress(12, "Adding RowID…")
    df.insert(0, "RowID", range(1, len(df) + 1))

    # ------------------------------------------------------------------ #
    # Step 2: Indication conversion
    # ------------------------------------------------------------------ #
    _progress(20, "Converting Indication values…")
    indication_step = IndicationStep(config.indication_rules)
    df = indication_step.apply(df)

    # ------------------------------------------------------------------ #
    # Step 3: Service Provider matching
    # ------------------------------------------------------------------ #
    _progress(30, "Building code mapping (first pass)…")
    provider_step = ProviderStep(
        config.name_rules,
        config.hcp_universe,
        fuzzy_threshold=fuzzy_threshold,
    )
    # First pass is handled inside apply()

    _progress(40, "Matching Service Providers…")
    df, log_entries = provider_step.apply(df)
    _progress(70, "Service Provider matching complete.")

    # ------------------------------------------------------------------ #
    # Step 4: Dosage extraction
    # ------------------------------------------------------------------ #
    _progress(75, "Extracting dosage amounts…")
    dosage_step = DosageStep(config.dosage_rules)
    df = dosage_step.apply(df)

    # ------------------------------------------------------------------ #
    # Step 5: BU assignment
    # ------------------------------------------------------------------ #
    _progress(80, "Assigning Business Units…")
    bu_step = BUStep(config.bu_rules)
    df = bu_step.apply(df)

    # ------------------------------------------------------------------ #
    # Reorder to output column spec
    # ------------------------------------------------------------------ #
    _progress(85, "Reordering columns…")
    # Add any missing columns with empty values
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[OUTPUT_COLUMNS]

    # ------------------------------------------------------------------ #
    # Write output files
    # ------------------------------------------------------------------ #
    _progress(90, "Writing output CSV…")
    output_path = write_output(df, input_path)

    _progress(95, "Writing match log…")
    log_path = write_match_log(log_entries, input_path)

    # ------------------------------------------------------------------ #
    # Build summary
    # ------------------------------------------------------------------ #
    _progress(100, "Done.")
    match_counts: dict[str, int] = {}
    for entry in log_entries:
        mt = entry.get("Match_Type", "unknown")
        match_counts[mt] = match_counts.get(mt, 0) + 1

    return {
        "output_path": str(output_path),
        "log_path": str(log_path),
        "total_rows": len(df),
        "match_counts": match_counts,
    }
