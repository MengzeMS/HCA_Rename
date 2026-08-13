"""Main processing pipeline orchestrator."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from config.config_manager import MasterConfig, RequestConfig, EnhertuConfig, EnhertuClaimsConfig
from output.writer import write_output
from output.log_writer import write_match_log
from pipeline.step_indication import IndicationStep
from pipeline.step_provider import ProviderStep
from pipeline.step_dosage import DosageStep
from pipeline.step_bu import BUStep
from pipeline.utils import load_input_file, InputError, normalize_date_columns, normalize_brand_column
from pipeline.request_pipeline import run_request_pipeline, RequestPipelineError
from pipeline.enhertu_pipeline import run_enhertu_pipeline, EnhertuPipelineError
from pipeline.enhertu_claims_pipeline import run_enhertu_claims_pipeline, EnhertuClaimsPipelineError

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]


class PipelineError(Exception):
    """Fatal error that stops the pipeline."""


def run_pipeline(
    input_path: str | Path,
    config: MasterConfig | RequestConfig | EnhertuConfig | EnhertuClaimsConfig,
    fuzzy_threshold: int = 2,
    progress_cb: Optional[ProgressCallback] = None,
    mode: str = "claim",
) -> dict:
    """
    Execute the full cleaning pipeline.

    mode='claim'          → Claim Data pipeline (default)
    mode='request'        → Request Data pipeline
    mode='enhertu'        → Enhertu Data pipeline
    mode='enhertu_claims' → Enhertu Claims Data pipeline

    Returns a summary dict with output paths and match type counts.
    Raises PipelineError on fatal errors.
    """
    if mode == "request":
        if not isinstance(config, RequestConfig):
            raise PipelineError("Request mode requires a RequestConfig object.")
        try:
            return run_request_pipeline(input_path, config, fuzzy_threshold, progress_cb)
        except RequestPipelineError as exc:
            raise PipelineError(str(exc)) from exc

    if mode == "enhertu":
        if not isinstance(config, EnhertuConfig):
            raise PipelineError("Enhertu mode requires an EnhertuConfig object.")
        try:
            return run_enhertu_pipeline(input_path, config, progress_cb)
        except EnhertuPipelineError as exc:
            raise PipelineError(str(exc)) from exc

    if mode == "enhertu_claims":
        if not isinstance(config, EnhertuClaimsConfig):
            raise PipelineError("Enhertu Claims mode requires an EnhertuClaimsConfig object.")
        try:
            return run_enhertu_claims_pipeline(input_path, config, fuzzy_threshold, progress_cb)
        except EnhertuClaimsPipelineError as exc:
            raise PipelineError(str(exc)) from exc

    # ── Claim Data pipeline ──────────────────────────────────────────────────
    if not isinstance(config, MasterConfig):
        raise PipelineError("Claim mode requires a MasterConfig object.")

    def _progress(pct: int, msg: str) -> None:
        if progress_cb:
            progress_cb(pct, msg)
        logger.info("[%d%%] %s", pct, msg)

    input_path = Path(input_path)

    _progress(5, "Loading input file…")
    try:
        df = load_input_file(input_path)
    except InputError as exc:
        raise PipelineError(str(exc)) from exc

    original_columns = list(df.columns)
    _progress(10, f"Loaded {len(df):,} rows. Columns: {list(df.columns)}")

    for col in ("Indication", "Service Provider", "Pack"):
        if col in df.columns:
            sample = df[col].head(5).tolist()
            logger.debug("DEBUG first-5 raw [%s]: %s", col, sample)

    _progress(12, "Adding RowID…")
    df.insert(0, "RowID", range(1, len(df) + 1))

    _progress(14, "Normalizing date columns…")
    df = normalize_date_columns(df, ["Invoice Date", "Treatment Date"])
    df = normalize_brand_column(df, "Brand")

    _progress(20, "Converting Indication values…")
    indication_step = IndicationStep(config.indication_rules)
    df = indication_step.apply(df)
    logger.debug("DEBUG first-5 Indication after step2: %s", df["Indication"].head(5).tolist())

    _progress(30, "Building code mapping (first pass)…")
    provider_step = ProviderStep(
        config.name_rules,
        config.hcp_universe,
        fuzzy_threshold=fuzzy_threshold,
    )

    _progress(40, "Matching Service Providers…")
    df, log_entries = provider_step.apply(df)
    _progress(70, "Service Provider matching complete.")
    logger.debug(
        "DEBUG first-5 match results: %s",
        [(e["Raw_Service_Provider"], e["Clean_Service_Provider"], e["Match_Type"])
         for e in log_entries[:5]],
    )

    _progress(75, "Extracting dosage amounts…")
    dosage_step = DosageStep(config.dosage_rules)
    df = dosage_step.apply(df)

    _progress(80, "Assigning Business Units…")
    bu_step = BUStep(config.bu_rules)
    df = bu_step.apply(df)

    _progress(85, "Reordering columns…")
    output_columns = ["RowID"] + original_columns + ["Dosage Amount", "BU"]

    for col in output_columns:
        if col not in df.columns:
            df[col] = ""

    df = df[output_columns]

    _progress(90, "Writing output CSV…")
    output_path = write_output(df, input_path)

    _progress(95, "Writing match log…")
    log_path = write_match_log(log_entries, input_path)

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
