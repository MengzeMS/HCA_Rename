"""Enhertu Data processing pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from config.config_manager import EnhertuConfig
from output.writer import write_output
from output.log_writer import write_insurance_log, write_indication_log
from pipeline.step_insurance import InsuranceStep
from pipeline.utils import load_input_file, InputError, REQUIRED_ENHERTU_COLUMNS

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]


class EnhertuPipelineError(Exception):
    """Fatal error that stops the Enhertu pipeline."""


def _normalize_code(value: str) -> str:
    """
    Normalize numeric indication codes for consistent matching.
    "21338.020" and "21338.02" both normalize to "21338.02".
    Non-numeric values are returned as-is (lowercased + stripped).
    """
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return ""
    try:
        num = float(s)
        # Use 10 significant figures — enough precision for medical codes like 21338.02
        return f"{num:.10g}"
    except ValueError:
        return s.lower()


def run_enhertu_pipeline(
    input_path: str | Path,
    config: EnhertuConfig,
    progress_cb: Optional[ProgressCallback] = None,
) -> dict:
    """
    Execute the Enhertu Data cleaning pipeline.

    Output column order:
      RowID + ALL original columns in original order (transformations applied)
      + Brand (fixed "Enhertu") + BU (fixed "OBU")

    Returns a summary dict. Raises EnhertuPipelineError on fatal errors.
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
        df = load_input_file(input_path, required_columns=REQUIRED_ENHERTU_COLUMNS)
    except InputError as exc:
        raise EnhertuPipelineError(str(exc)) from exc

    original_columns = list(df.columns)
    _progress(10, f"Loaded {len(df):,} rows.")

    # ------------------------------------------------------------------ #
    # Step 1: Add RowID
    # ------------------------------------------------------------------ #
    _progress(12, "Adding RowID…")
    df.insert(0, "RowID", range(1, len(df) + 1))

    # ------------------------------------------------------------------ #
    # Step 2: Insurance name cleaning (Versicherung)
    # ------------------------------------------------------------------ #
    _progress(30, "Cleaning insurance names (Versicherung)…")
    insurance_step = InsuranceStep(
        config.insurance_rules,
        old_col="Versicherung",
        clean_col="cleaned_insurance_name",
        input_col="Versicherung",
        log_raw_col="Raw_Versicherung",
    )
    df, insurance_log = insurance_step.apply(df)
    _progress(50, "Insurance name cleaning complete.")

    # ------------------------------------------------------------------ #
    # Step 3: Indication code matching (Indikationscode)
    # ------------------------------------------------------------------ #
    _progress(55, "Matching indication codes…")

    # Build normalized lookup: normalized_code → cleaned_indication
    indication_lookup: dict[str, str] = {}
    for _, row in config.indication_rules.iterrows():
        key = _normalize_code(str(row["Indikationscode"]))
        val = str(row["cleaned_indication"]).strip()
        if key:
            indication_lookup[key] = val

    indication_log: list[dict] = []
    cleaned_indications: list[str] = []
    for idx, row in df.iterrows():
        raw = str(row["Indikationscode"]) if pd.notna(row.get("Indikationscode")) else ""
        norm_key = _normalize_code(raw)
        if norm_key and norm_key in indication_lookup:
            cleaned = indication_lookup[norm_key]
            match_type = "exact"
        else:
            cleaned = raw.strip()
            match_type = "no-match"
        cleaned_indications.append(cleaned)
        indication_log.append(
            {
                "RowID": row.get("RowID", idx + 1),
                "Raw_Indikationscode": raw,
                "Clean_Indication": cleaned,
                "Match_Type": match_type,
            }
        )
    df["Indikationscode"] = cleaned_indications
    _progress(70, "Indication code matching complete.")

    # ------------------------------------------------------------------ #
    # Step 4: Add fixed Brand and BU columns
    # ------------------------------------------------------------------ #
    _progress(80, "Adding Brand and BU columns…")
    df["Brand"] = "Enhertu"
    df["BU"] = "OBU"

    # ------------------------------------------------------------------ #
    # Reorder: RowID + original cols + Brand + BU
    # ------------------------------------------------------------------ #
    _progress(85, "Reordering columns…")
    output_columns = ["RowID"] + original_columns + ["Brand", "BU"]
    for col in output_columns:
        if col not in df.columns:
            df[col] = ""
    df = df[output_columns]

    # ------------------------------------------------------------------ #
    # Write output files
    # ------------------------------------------------------------------ #
    _progress(90, "Writing output CSV…")
    output_path = write_output(df, input_path)

    _progress(93, "Writing insurance log…")
    insurance_log_path = write_insurance_log(
        insurance_log, input_path, raw_col="Raw_Versicherung"
    )

    _progress(96, "Writing indication log…")
    indication_log_path = write_indication_log(indication_log, input_path)

    # ------------------------------------------------------------------ #
    # Build summary
    # ------------------------------------------------------------------ #
    _progress(100, "Done.")
    insurance_counts: dict[str, int] = {}
    for entry in insurance_log:
        mt = entry.get("Match_Type", "unknown")
        insurance_counts[mt] = insurance_counts.get(mt, 0) + 1

    indication_counts: dict[str, int] = {}
    for entry in indication_log:
        mt = entry.get("Match_Type", "unknown")
        indication_counts[mt] = indication_counts.get(mt, 0) + 1

    return {
        "output_path": str(output_path),
        "log_path": str(insurance_log_path),
        "insurance_log_path": str(insurance_log_path),
        "indication_log_path": str(indication_log_path),
        "total_rows": len(df),
        "match_counts": {},
        "insurance_counts": insurance_counts,
        "indication_counts": indication_counts,
    }
