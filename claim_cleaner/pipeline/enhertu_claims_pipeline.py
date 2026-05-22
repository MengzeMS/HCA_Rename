"""Enhertu Claims Data processing pipeline."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from config.config_manager import EnhertuClaimsConfig
from config.settings import get_app_output_dirs
from output.writer import write_output
from pipeline.step_provider import ProviderStep
from pipeline.utils import load_input_file, InputError, REQUIRED_ENHERTU_CLAIMS_COLUMNS

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], None]

_PAREN_SUFFIX_RE = re.compile(r'\s*\([^)]*\)\s*$')
_PAREN_CODE_RE = re.compile(r'\(([^)]+)\)\s*$')


class EnhertuClaimsPipelineError(Exception):
    """Fatal error that stops the Enhertu Claims pipeline."""


def _match_claims_insurance(
    raw: str,
    lookup: dict[str, str],
    cleaned_names: set[str],
) -> tuple[str, str]:
    """
    Match an insurance name with 4-step fallback:
      a. Exact match (case-insensitive, stripped)
      b. Strip parenthetical suffix, try again
      c. Extract parenthetical code, check against cleaned_names set
      d. No match → keep original
    Returns (cleaned_name, match_type).
    """
    stripped = raw.strip()

    result = lookup.get(stripped.lower())
    if result is not None:
        return result, "exact"

    without_paren = _PAREN_SUFFIX_RE.sub("", stripped).strip()
    if without_paren and without_paren.lower() != stripped.lower():
        result = lookup.get(without_paren.lower())
        if result is not None:
            return result, "exact-stripped"

    m = _PAREN_CODE_RE.search(stripped)
    if m:
        code = m.group(1).strip()
        if code in cleaned_names:
            return code, "code-match"

    return stripped if stripped else "", "no-match"


def _match_claims_indication(raw: str, lookup: dict[str, str]) -> tuple[str, str]:
    """Exact match (case-insensitive). Empty string matches "" key if present."""
    stripped = raw.strip()
    result = lookup.get(stripped.lower())
    if result is not None:
        return result, "exact"
    return stripped if stripped else "", "no-match"


def run_enhertu_claims_pipeline(
    input_path: str | Path,
    config: EnhertuClaimsConfig,
    fuzzy_threshold: int = 2,
    progress_cb: Optional[ProgressCallback] = None,
) -> dict:
    """
    Execute the Enhertu Claims Data cleaning pipeline.

    Output column order:
      RowID + ALL original columns in original order (transformations applied) + BU

    Returns a summary dict. Raises EnhertuClaimsPipelineError on fatal errors.
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
        df = load_input_file(input_path, required_columns=REQUIRED_ENHERTU_CLAIMS_COLUMNS)
    except InputError as exc:
        raise EnhertuClaimsPipelineError(str(exc)) from exc

    original_columns = list(df.columns)
    _progress(10, f"Loaded {len(df):,} rows.")

    # ------------------------------------------------------------------ #
    # Step 1: Add RowID
    # ------------------------------------------------------------------ #
    _progress(12, "Adding RowID…")
    df.insert(0, "RowID", range(1, len(df) + 1))

    # ------------------------------------------------------------------ #
    # Determine which columns to transform (handle pandas .1 suffix for duplicates)
    # ------------------------------------------------------------------ #
    versicherung_col = "VERSICHERUNG.1" if "VERSICHERUNG.1" in df.columns else "VERSICHERUNG"
    indikation_col = "INDIKATION.1" if "INDIKATION.1" in df.columns else "INDIKATION"
    logger.debug("Using insurance col: %s, indication col: %s", versicherung_col, indikation_col)

    # ------------------------------------------------------------------ #
    # Step 2: Transform insurance names (VERSICHERUNG.1)
    # ------------------------------------------------------------------ #
    _progress(25, f"Cleaning insurance names ({versicherung_col})…")
    insurance_log: list[dict] = []
    cleaned_insurance: list[str] = []
    for idx, row in df.iterrows():
        raw_val = row.get(versicherung_col, "")
        raw = str(raw_val).strip() if pd.notna(raw_val) else ""
        cleaned, match_type = _match_claims_insurance(
            raw, config.insurance_lookup, config.cleaned_insurance_names
        )
        cleaned_insurance.append(cleaned)
        insurance_log.append({
            "RowID":           row.get("RowID", idx + 1),
            "Raw_VERSICHERUNG": raw,
            "Clean_Insurance": cleaned,
            "Match_Type":      match_type,
        })
    df[versicherung_col] = cleaned_insurance
    _progress(40, "Insurance name cleaning complete.")

    # ------------------------------------------------------------------ #
    # Step 3: Transform indication codes (INDIKATION.1)
    # ------------------------------------------------------------------ #
    _progress(45, f"Matching indication values ({indikation_col})…")
    indication_log: list[dict] = []
    cleaned_indications: list[str] = []
    for idx, row in df.iterrows():
        raw_val = row.get(indikation_col, "")
        raw = str(raw_val).strip() if pd.notna(raw_val) else ""
        cleaned, match_type = _match_claims_indication(raw, config.indication_lookup)
        cleaned_indications.append(cleaned)
        indication_log.append({
            "RowID":           row.get("RowID", idx + 1),
            "Raw_INDIKATION":  raw,
            "Clean_Indication": cleaned,
            "Match_Type":      match_type,
        })
    df[indikation_col] = cleaned_indications
    _progress(55, "Indication matching complete.")

    # ------------------------------------------------------------------ #
    # Step 4: Transform INSTITUT using ProviderStep logic
    # ------------------------------------------------------------------ #
    _progress(60, "Matching institution names (INSTITUT)…")
    # Temporarily rename for ProviderStep which expects "Service Provider"
    df.rename(columns={"INSTITUT": "Service Provider"}, inplace=True)
    provider_step = ProviderStep(
        config.expanded_name_rules,
        pd.DataFrame(columns=["HCA", "LastName_c", "FirstName_c"]),
        fuzzy_threshold=fuzzy_threshold,
    )
    df, inst_log = provider_step.apply(df)
    df.rename(columns={"Service Provider": "INSTITUT"}, inplace=True)
    _progress(75, "Institution matching complete.")

    # ------------------------------------------------------------------ #
    # Step 5: Add fixed BU column
    # ------------------------------------------------------------------ #
    _progress(80, "Adding BU column…")
    df["BU"] = "OBU"

    # ------------------------------------------------------------------ #
    # Reorder: RowID + original cols + BU
    # ------------------------------------------------------------------ #
    _progress(85, "Reordering columns…")
    output_columns = ["RowID"] + original_columns + ["BU"]
    for col in output_columns:
        if col not in df.columns:
            df[col] = ""
    df = df[output_columns]

    # ------------------------------------------------------------------ #
    # Write output files
    # ------------------------------------------------------------------ #
    _progress(88, "Writing output CSV…")
    output_path = write_output(df, input_path)

    _progress(91, "Writing institution log…")
    _, log_dir = get_app_output_dirs()
    inst_log_path = log_dir / f"enhertu_claims_institution_log_{input_path.stem}.csv"
    pd.DataFrame(inst_log).to_csv(inst_log_path, index=False, encoding="utf-8-sig")

    _progress(93, "Writing insurance log…")
    ins_log_path = log_dir / f"enhertu_claims_insurance_log_{input_path.stem}.csv"
    pd.DataFrame(insurance_log).to_csv(ins_log_path, index=False, encoding="utf-8-sig")

    _progress(96, "Writing indication log…")
    ind_log_path = log_dir / f"enhertu_claims_indication_log_{input_path.stem}.csv"
    pd.DataFrame(indication_log).to_csv(ind_log_path, index=False, encoding="utf-8-sig")

    # ------------------------------------------------------------------ #
    # Build summary
    # ------------------------------------------------------------------ #
    _progress(100, "Done.")

    def _counts(log: list[dict]) -> dict[str, int]:
        c: dict[str, int] = {}
        for e in log:
            mt = e.get("Match_Type", "unknown")
            c[mt] = c.get(mt, 0) + 1
        return c

    inst_log_for_counts = [{"Match_Type": e.get("Match_Type")} for e in inst_log]
    match_counts = _counts(inst_log_for_counts)

    return {
        "output_path":          str(output_path),
        "log_path":             str(inst_log_path),
        "institution_log_path": str(inst_log_path),
        "insurance_log_path":   str(ins_log_path),
        "indication_log_path":  str(ind_log_path),
        "total_rows":           len(df),
        "match_counts":         match_counts,
        "insurance_counts":     _counts(insurance_log),
        "indication_counts":    _counts(indication_log),
    }
