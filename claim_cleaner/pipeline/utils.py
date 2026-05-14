"""Shared utilities for pipeline steps."""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Required input columns (case-insensitive, whitespace-stripped)
REQUIRED_INPUT_COLUMNS = [
    "Insurance ID",
    "Insurance carrier",
    "Invoice-ID",
    "Invoice Type",
    "Patient-ID",
    "Patient ID insurance",
    "Brand",
    "Indication Code",
    "Indication",
    "Indication original",
    "Service Provider",
    "Pack",
    "Invoice Date",
    "Treatment Date",
    "Amount",
    "Price basis",
    "Price total",
    "Discount total",
    "Discount %",
    "Art 71 Rating",
    "Line Invoice",
    "Invoice status",
]

OUTPUT_COLUMNS = [
    "RowID",
    "Insurance ID",
    "Insurance carrier",
    "Invoice-ID",
    "Invoice Type",
    "Patient-ID",
    "Patient ID insurance",
    "Brand",
    "Indication Code",
    "Indication",
    "Indication original",
    "Service Provider",
    "Pack",
    "Invoice Date",
    "Treatment Date",
    "Amount",
    "Price basis",
    "Price total",
    "Discount total",
    "Discount %",
    "Art 71 Rating",
    "Line Invoice",
    "Invoice status",
    "Dosage Amount",
    "BU",
]


class InputError(Exception):
    """Raised when the input file cannot be parsed or is missing required columns."""


def _normalise_col(name: str) -> str:
    return name.strip().lower()


def load_input_file(path: str | Path) -> pd.DataFrame:
    """
    Load a CSV or XLSX input file.
    Tries UTF-8, UTF-8-BOM, then Latin-1 for CSV.
    For XLSX, reads the first sheet.
    Validates that all required columns are present.
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

    # Normalize column names
    col_map = {c: c.strip() for c in df.columns}
    df.rename(columns=col_map, inplace=True)

    # Case-insensitive column matching
    existing_lower = {_normalise_col(c): c for c in df.columns}
    rename_map: dict[str, str] = {}
    for req in REQUIRED_INPUT_COLUMNS:
        req_lower = _normalise_col(req)
        if req_lower in existing_lower:
            actual = existing_lower[req_lower]
            if actual != req:
                rename_map[actual] = req
        # else: will be caught below

    if rename_map:
        df.rename(columns=rename_map, inplace=True)

    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in df.columns]
    if missing:
        raise InputError(
            f"Input file is missing required columns: {missing}.\n"
            f"Found columns: {list(df.columns)}"
        )

    # Fill NaN with empty string for string processing columns
    for col in ["Indication", "Service Provider", "Pack"]:
        if col in df.columns:
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
