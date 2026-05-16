"""Shared utilities for pipeline steps."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Claim Data: only these 3 columns are required
REQUIRED_COLUMNS = ["Indication", "Service Provider", "Pack"]

# Request Data: these 4 columns are required
REQUIRED_REQUEST_COLUMNS = ["Indication", "Krankenkasse", "Insitution", "Brand"]

# Mojibake markers produced when a UTF-8 file is read as latin-1
_MOJIBAKE_MARKERS = ("Ã¼", "Ã¶", "Ã¤", "Ã©", "Ã", "â€")


class InputError(Exception):
    """Raised when the input file cannot be parsed or is missing required columns."""


def _normalise_col(name: str) -> str:
    return name.strip().lower()


def load_input_file(
    path: str | Path,
    required_columns: list[str] | None = None,
) -> pd.DataFrame:
    """
    Load a CSV or XLSX input file.
    Uses chardet for encoding detection on CSV files; falls back to utf-8-sig / latin-1.
    For XLSX, reads the first sheet.
    Validates that the required columns are present (defaults to REQUIRED_COLUMNS).
    Returns a DataFrame with ALL original columns intact, preserving original column order.
    """
    if required_columns is None:
        required_columns = REQUIRED_COLUMNS

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
        df = _load_csv(path)

    # Strip whitespace from column names
    col_map = {c: c.strip() for c in df.columns}
    df.rename(columns=col_map, inplace=True)

    # Case-insensitive column matching for required columns
    existing_lower = {_normalise_col(c): c for c in df.columns}
    rename_map: dict[str, str] = {}
    for req in required_columns:
        req_lower = _normalise_col(req)
        if req_lower in existing_lower:
            actual = existing_lower[req_lower]
            if actual != req:
                rename_map[actual] = req

    if rename_map:
        df.rename(columns=rename_map, inplace=True)

    # Validate required columns
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise InputError(
            f"Input file is missing required columns: {missing}.\n"
            f"Found columns: {list(df.columns)}"
        )

    # Fill NaN with empty string for required string processing columns
    for col in required_columns:
        df[col] = df[col].fillna("").astype(str)

    return df


def _has_mojibake(df: pd.DataFrame) -> bool:
    """Check if a DataFrame's text content contains UTF-8-as-latin-1 mojibake markers."""
    sample_parts = list(df.columns)
    for _, row in df.head(5).iterrows():
        for val in row:
            if isinstance(val, str):
                sample_parts.append(val)
    sample_text = " ".join(sample_parts)
    return any(marker in sample_text for marker in _MOJIBAKE_MARKERS)


def _load_csv(path: Path) -> pd.DataFrame:
    """Load CSV with automatic encoding detection via chardet, with mojibake fallback."""
    raw_bytes = path.read_bytes()

    if raw_bytes[:3] == b'\xef\xbb\xbf':
        primary_encoding = "utf-8-sig"
    else:
        try:
            import chardet  # type: ignore
            detected = chardet.detect(raw_bytes[:100_000])
            primary_encoding = detected.get("encoding") or "utf-8"
            logger.debug("chardet detected encoding: %s (confidence %.2f)",
                         primary_encoding, detected.get("confidence", 0))
        except ImportError:
            primary_encoding = "utf-8"

    encodings: list[str] = [primary_encoding]
    for fallback in ("utf-8-sig", "utf-8", "latin-1"):
        if fallback.lower() != primary_encoding.lower():
            encodings.append(fallback)

    for encoding in encodings:
        try:
            candidate = pd.read_csv(
                path,
                dtype=str,
                encoding=encoding,
                keep_default_na=False,
                na_values=[],
                quoting=0,
            )
            if _has_mojibake(candidate) and encoding.lower() not in ("utf-8", "utf-8-sig"):
                logger.debug("Mojibake detected with encoding %s — trying next", encoding)
                continue
            return candidate
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            raise InputError(f"Cannot parse CSV file: {exc}") from exc

    raise InputError(f"Cannot decode CSV file (tried {encodings}): {path}")
