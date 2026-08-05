"""Request Data processing pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from config.config_manager import RequestConfig
from output.writer import write_output
from output.log_writer import write_match_log, write_insurance_log
from pipeline.step_indication import IndicationStep
from pipeline.step_provider import ProviderStep
from pipeline.step_insurance import InsuranceStep
from pipeline.utils import load_input_file, InputError, REQUIRED_REQUEST_COLUMNS, normalize_date_columns, normalize_brand_column

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]


class RequestPipelineError(Exception):
    """Fatal error that stops the request pipeline."""


def run_request_pipeline(
    input_path: str | Path,
    config: RequestConfig,
    fuzzy_threshold: int = 2,
    progress_cb: Optional[ProgressCallback] = None,
) -> dict:
    """
    Execute the Request Data cleaning pipeline.

    Output column order:
      RowID + ALL original columns in original order
      ("Insitution" renamed to "Institution" in output)
      + BU (last)

    Returns a summary dict. Raises RequestPipelineError on fatal errors.
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
        df = load_input_file(input_path, required_columns=REQUIRED_REQUEST_COLUMNS)
    except InputError as exc:
        raise RequestPipelineError(str(exc)) from exc

    original_columns = list(df.columns)
    _progress(10, f"Loaded {len(df):,} rows.")

    # ------------------------------------------------------------------ #
    # Step 1: Add RowID
    # ------------------------------------------------------------------ #
    _progress(12, "Adding RowID…")
    df.insert(0, "RowID", range(1, len(df) + 1))

    _progress(14, "Normalizing date columns…")
    df = normalize_date_columns(df, ["Decision Date"])
    df = normalize_brand_column(df, "Brand")

    # ------------------------------------------------------------------ #
    # Step 2: Indication conversion
    # ------------------------------------------------------------------ #
    _progress(20, "Converting Indication values…")
    indication_step = IndicationStep(config.indication_rules)
    df = indication_step.apply(df)

    # ------------------------------------------------------------------ #
    # Step 3: Insurance name cleaning
    # ------------------------------------------------------------------ #
    _progress(35, "Cleaning insurance names (Krankenkasse)…")
    insurance_step = InsuranceStep(config.insurance_rules)
    df, insurance_log = insurance_step.apply(df)
    _progress(50, "Insurance name cleaning complete.")

    # ------------------------------------------------------------------ #
    # Step 4: Institution matching
    # Temporarily rename Insitution → Service Provider so ProviderStep works.
    # ------------------------------------------------------------------ #
    _progress(55, "Matching institution names…")
    df.rename(columns={"Insitution": "Service Provider"}, inplace=True)

    empty_hcp = pd.DataFrame(columns=["HCA", "LastName_c", "FirstName_c"])
    provider_step = ProviderStep(
        config.name_rules,
        empty_hcp,
        fuzzy_threshold=fuzzy_threshold,
    )
    df, institution_log = provider_step.apply(df)

    # Rename back; will be renamed "Institution" (fixed typo) in output
    df.rename(columns={"Service Provider": "Insitution"}, inplace=True)
    _progress(75, "Institution matching complete.")

    # Rename log column headers to Institution context
    for entry in institution_log:
        entry["Raw_Institution"] = entry.pop("Raw_Service_Provider")
        entry["Clean_Institution"] = entry.pop("Clean_Service_Provider")

    # ------------------------------------------------------------------ #
    # Step 5: BU from Brand
    # ------------------------------------------------------------------ #
    _progress(80, "Assigning Business Units…")
    df["BU"] = df["Brand"].apply(
        lambda x: config.bu_lookup.get(str(x).strip().lower(), "")
    )

    # ------------------------------------------------------------------ #
    # Reorder columns and fix "Insitution" → "Institution" typo
    # ------------------------------------------------------------------ #
    _progress(85, "Reordering columns…")
    output_original = ["Institution" if c == "Insitution" else c for c in original_columns]
    df.rename(columns={"Insitution": "Institution"}, inplace=True)
    output_columns = ["RowID"] + output_original + ["BU"]

    for col in output_columns:
        if col not in df.columns:
            df[col] = ""
    df = df[output_columns]

    # ------------------------------------------------------------------ #
    # Write output files
    # ------------------------------------------------------------------ #
    _progress(90, "Writing output CSV…")
    output_path = write_output(df, input_path)

    _progress(93, "Writing institution match log…")
    institution_log_path = write_match_log(
        institution_log, input_path,
        columns=["RowID", "Raw_Institution", "Clean_Institution", "Match_Type", "Match_Details"],
        prefix="institution_log",
    )

    _progress(96, "Writing insurance match log…")
    insurance_log_path = write_insurance_log(insurance_log, input_path)

    # ------------------------------------------------------------------ #
    # Build summary
    # ------------------------------------------------------------------ #
    _progress(100, "Done.")
    match_counts: dict[str, int] = {}
    for entry in institution_log:
        mt = entry.get("Match_Type", "unknown")
        match_counts[mt] = match_counts.get(mt, 0) + 1

    insurance_counts: dict[str, int] = {}
    for entry in insurance_log:
        mt = entry.get("Match_Type", "unknown")
        insurance_counts[mt] = insurance_counts.get(mt, 0) + 1

    return {
        "output_path": str(output_path),
        "log_path": str(institution_log_path),
        "insurance_log_path": str(insurance_log_path),
        "total_rows": len(df),
        "match_counts": match_counts,
        "insurance_counts": insurance_counts,
    }
