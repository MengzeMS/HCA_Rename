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


def write_match_log(log_entries: list[dict], input_path: Path) -> Path:
    """
    Write match log CSV to same folder as input_path.
    Filename: match_log_{original_filename}.csv
    """
    stem = input_path.stem
    log_name = f"match_log_{stem}.csv"
    log_path = input_path.parent / log_name

    df = pd.DataFrame(log_entries, columns=LOG_COLUMNS)
    df.to_csv(log_path, index=False, encoding="utf-8")
    return log_path
