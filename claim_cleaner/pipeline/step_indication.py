"""Step 2: Indication conversion."""
from __future__ import annotations

import pandas as pd


class IndicationStep:
    """Converts raw Indication values to cleaned values using indication_rule."""

    def __init__(self, indication_rules: pd.DataFrame) -> None:
        # Build exact-match lookup: raw_value → cleaned_value
        # Keys are NOT trimmed (table contains whitespace variants intentionally)
        self._lookup: dict[str, str] = {}
        for _, row in indication_rules.iterrows():
            old = str(row["old_Indication"]) if pd.notna(row["old_Indication"]) else ""
            new = str(row["new_Indication"]) if pd.notna(row["new_Indication"]) else ""
            # Store as-is (no trimming) for exact match
            self._lookup[old] = new

    def transform(self, raw: str) -> str:
        """
        Convert raw indication to cleaned value.

        1. Exact match on raw value (including whitespace)
        2. If no match: trim, if blank → "Unknown"
        3. If still no match after trim → keep trimmed value
        """
        if not isinstance(raw, str):
            raw = str(raw) if raw is not None else ""

        # Step 1: exact match (do NOT trim)
        if raw in self._lookup:
            return self._lookup[raw]

        # Step 2: trim and check
        trimmed = raw.strip()
        if not trimmed:
            return "Unknown"

        # Check trimmed value in lookup as well
        if trimmed in self._lookup:
            return self._lookup[trimmed]

        # Step 3: keep trimmed value
        return trimmed

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply indication transformation to DataFrame in-place."""
        df["Indication"] = df["Indication"].apply(self.transform)
        return df
