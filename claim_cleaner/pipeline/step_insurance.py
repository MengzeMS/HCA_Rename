"""Step: Insurance/Versicherung name cleaning (Request and Enhertu modes)."""
from __future__ import annotations

import pandas as pd


class InsuranceStep:
    """
    Exact case-insensitive lookup for insurance name cleaning.

    Default wiring (Request mode):   old_col="old_Krankenkasse", input_col="Krankenkasse"
    Enhertu mode:                    old_col="Versicherung",      input_col="Versicherung"
    """

    def __init__(
        self,
        rules: pd.DataFrame,
        old_col: str = "old_Krankenkasse",
        clean_col: str = "cleaned_insurance_name",
        input_col: str = "Krankenkasse",
        log_raw_col: str = "Raw_Krankenkasse",
    ) -> None:
        self._input_col = input_col
        self._log_raw_col = log_raw_col
        self._lookup: dict[str, str] = {}
        for _, row in rules.iterrows():
            old = str(row[old_col]).strip().lower()
            new = str(row[clean_col]).strip()
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
            raw = str(row[self._input_col]) if pd.notna(row.get(self._input_col)) else ""
            cleaned, match_type = self.transform(raw)
            cleaned_values.append(cleaned)
            log_entries.append(
                {
                    "RowID": row.get("RowID", idx + 1),
                    self._log_raw_col: raw,
                    "Clean_Insurance": cleaned,
                    "Match_Type": match_type,
                }
            )
        df[self._input_col] = cleaned_values
        return df, log_entries
