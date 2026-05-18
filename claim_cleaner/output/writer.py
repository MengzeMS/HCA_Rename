"""CSV output writer."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_output(df: pd.DataFrame, input_path: Path, output_dir: Path | None = None) -> Path:
    """
    Write cleaned DataFrame to CSV.
    By default writes to {APP_BASE}/processed_data/; pass output_dir to override.
    Encoding: UTF-8 with BOM (utf-8-sig) so Excel opens it correctly on Windows.
    """
    if output_dir is None:
        from config.settings import get_app_output_dirs
        output_dir, _ = get_app_output_dirs()

    stem = input_path.stem
    out_path = output_dir / f"cleaned_{stem}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return out_path
