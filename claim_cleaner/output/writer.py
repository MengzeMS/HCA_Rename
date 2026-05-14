"""CSV output writer."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_output(df: pd.DataFrame, input_path: Path) -> Path:
    """
    Write cleaned DataFrame to CSV in the same folder as input_path.
    Filename: cleaned_{original_filename}.csv
    """
    stem = input_path.stem
    out_name = f"cleaned_{stem}.csv"
    out_path = input_path.parent / out_name
    df.to_csv(out_path, index=False, encoding="utf-8")
    return out_path
