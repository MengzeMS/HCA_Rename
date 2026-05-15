"""Shared utilities for pipeline steps."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Only these 3 columns are required (case-insensitive match)
REQUIRED_COLUMNS = ["Indication", "Service Provider", "Pack"]


class InputError(Exception):
    """Raised when the input file cannot be parsed or is missing required columns."""


def _normalise_col(name: str) -> str:
    return name.strip().lower()


def load_input_file(path: str | Path) -> pd.DataFrame:
    """
    Load a CSV or XLSX input file.
    Tries UTF-8, UTF-8-BOM, then Latin-1 for CSV.
    For XLSX, reads the first sheet.
    Validates that the 3 required columns (Indication, Service Provider, Pack) are present.
    Returns a DataFrame with ALL original columns intact, preserving original column order.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(path, sheet_name=0, dtype=str, engine="openpyxl")
        except Exception as exc:
            raise InputError(f"Cannot read XLSX file: {exc}") from exc
    elif suffix == ".csv":
        df = _load_csv(path)
    else:
        # Attempt CSV regardless of extension
        df = _load_csv(path)

    # Strip whitespace from column names
    col_map = {c: c.strip() for c in df.columns}
    df.rename(columns=col_map, inplace=True)

    # Case-insensitive column matching for required columns —
    # rename them to canonical casing so downstream steps find them
    existing_lower = {_normalise_col(c): c for c in df.columns}
    rename_map: dict[str, str] = {}
    for req in REQUIRED_COLUMNS:
        req_lower = _normalise_col(req)
        if req_lower in existing_lower:
            actual = existing_lower[req_lower]
            if actual != req:
                rename_map[actual] = req

    if rename_map:
        df.rename(columns=rename_map, inplace=True)

    # Validate that the 3 required columns are present
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise InputError(
            f"Input file is missing required columns: {missing}.\n"
            f"Found columns: {list(df.columns)}"
        )

    # Fill NaN with empty string for the 3 string processing columns
    for col in REQUIRED_COLUMNS:
        df[col] = df[col].fillna("").astype(str)

    return df


def _load_csv(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            df = pd.read_csv(
                path,
                dtype=str,
                encoding=encoding,
                keep_default_na=False,
                na_values=[],
                quoting=0,  # QUOTE_MINIMAL — pandas handles RFC 4180
            )
            return df
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            raise InputError(f"Cannot parse CSV file: {exc}") from exc
    raise InputError(f"Cannot decode CSV file (tried UTF-8, UTF-8-BOM, Latin-1): {path}")
