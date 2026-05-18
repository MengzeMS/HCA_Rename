"""Match log / report writer."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

LOG_COLUMNS = [
    "RowID",
    "Raw_Service_Provider",
    "Clean_Service_Provider",
    "Match_Type",
    "Match_Details",
]

INSURANCE_LOG_COLUMNS = [
    "RowID",
    "Raw_Krankenkasse",
    "Clean_Insurance",
    "Match_Type",
]

INDICATION_LOG_COLUMNS = [
    "RowID",
    "Raw_Indikationscode",
    "Clean_Indication",
    "Match_Type",
]


def write_match_log(
    log_entries: list[dict],
    input_path: Path,
    columns: list[str] | None = None,
    prefix: str = "match_log",
    log_dir: Path | None = None,
) -> Path:
    """Write a match log CSV to the Logs/ directory (or log_dir if given)."""
    if columns is None:
        columns = LOG_COLUMNS
    if log_dir is None:
        from config.settings import get_app_output_dirs
        _, log_dir = get_app_output_dirs()

    log_path = log_dir / f"{prefix}_{input_path.stem}.csv"
    pd.DataFrame(log_entries, columns=columns).to_csv(log_path, index=False, encoding="utf-8-sig")
    return log_path


def write_insurance_log(
    log_entries: list[dict],
    input_path: Path,
    raw_col: str = "Raw_Krankenkasse",
    log_dir: Path | None = None,
) -> Path:
    """Write insurance match log CSV."""
    if log_dir is None:
        from config.settings import get_app_output_dirs
        _, log_dir = get_app_output_dirs()

    columns = ["RowID", raw_col, "Clean_Insurance", "Match_Type"]
    log_path = log_dir / f"insurance_log_{input_path.stem}.csv"
    pd.DataFrame(log_entries, columns=columns).to_csv(log_path, index=False, encoding="utf-8-sig")
    return log_path


def write_indication_log(
    log_entries: list[dict],
    input_path: Path,
    log_dir: Path | None = None,
) -> Path:
    """Write indication match log CSV (Enhertu mode)."""
    if log_dir is None:
        from config.settings import get_app_output_dirs
        _, log_dir = get_app_output_dirs()

    log_path = log_dir / f"indication_log_{input_path.stem}.csv"
    pd.DataFrame(log_entries, columns=INDICATION_LOG_COLUMNS).to_csv(
        log_path, index=False, encoding="utf-8-sig"
    )
    return log_path
