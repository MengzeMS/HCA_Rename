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


def write_match_log(
    log_entries: list[dict],
    input_path: Path,
    columns: list[str] | None = None,
    prefix: str = "match_log",
) -> Path:
    """
    Write a match log CSV to the same folder as input_path.
    Filename: {prefix}_{original_filename}.csv
    """
    if columns is None:
        columns = LOG_COLUMNS

    stem = input_path.stem
    log_name = f"{prefix}_{stem}.csv"
    log_path = input_path.parent / log_name

    df = pd.DataFrame(log_entries, columns=columns)
    df.to_csv(log_path, index=False, encoding="utf-8-sig")
    return log_path


def write_insurance_log(log_entries: list[dict], input_path: Path) -> Path:
    """Write insurance match log CSV."""
    stem = input_path.stem
    log_name = f"insurance_log_{stem}.csv"
    log_path = input_path.parent / log_name

    df = pd.DataFrame(log_entries, columns=INSURANCE_LOG_COLUMNS)
    df.to_csv(log_path, index=False, encoding="utf-8-sig")
    return log_path
