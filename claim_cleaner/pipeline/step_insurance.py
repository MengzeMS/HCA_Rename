"""Step: Insurance name cleaning (Request Data mode only)."""
from __future__ import annotations

import pandas as pd


class InsuranceStep:
    """Exact case-insensitive lookup: old_Krankenkasse → cleaned_insurance_name."""

    def __init__(self, insurance_rules: pd.DataFrame) -> None:
        self._lookup: dict[str, str] = {}
        for _, row in insurance_rules.iterrows():
            old = str(row["old_Krankenkasse"]).strip().lower()
            new = str(row["cleaned_insurance_name"]).strip()
            if old:
                self._lookup[old] = new

    def transform(self, raw: str) -> tuple[str, str]:
        """Return (cleaned_name, match_type). match_type is 'exact' or 'no-match'."""
        stripped = str(raw).strip()
        result = self._lookup.get(stripped.lower())
        if result is not None:
            return result, "exact"
        return stripped, "no-match"

    def apply(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
        log_entries: list[dict] = []
        cleaned_values: list[str] = []
        for idx, row in df.iterrows():
            raw = str(row["Krankenkasse"]) if pd.notna(row.get("Krankenkasse")) else ""
            cleaned, match_type = self.transform(raw)
            cleaned_values.append(cleaned)
            log_entries.append(
                {
                    "RowID": row.get("RowID", idx + 1),
                    "Raw_Krankenkasse": raw,
                    "Clean_Insurance": cleaned,
                    "Match_Type": match_type,
                }
            )
        df["Krankenkasse"] = cleaned_values
        return df, log_entries
