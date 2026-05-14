"""Step 4: Dosage extraction."""
from __future__ import annotations

import re

import pandas as pd

# Fallback regex: first number before "mg"
_MG_RE = re.compile(r"(\d+\.?\d*)\s*mg", re.IGNORECASE)


class DosageStep:
    """Looks up Dosage Amount from dosage_rule by Pack, with regex fallback."""

    def __init__(self, dosage_rules: pd.DataFrame) -> None:
        self._lookup: dict[str, str] = {}
        for _, row in dosage_rules.iterrows():
            pack = str(row["Pack"]).strip() if pd.notna(row["Pack"]) else ""
            dosage = row["Dosage Amount"]
            if pack:
                # Store as string to avoid float formatting issues
                self._lookup[pack] = str(dosage) if pd.notna(dosage) else ""

    def _extract(self, pack: str) -> str:
        pack_stripped = pack.strip()

        # Exact match (trim both sides)
        if pack_stripped in self._lookup:
            val = self._lookup[pack_stripped]
            # Strip trailing .0 for integers stored as float
            if val.endswith(".0"):
                val = val[:-2]
            return val

        # Regex fallback
        m = _MG_RE.search(pack_stripped)
        if m:
            val = m.group(1)
            if val.endswith(".0"):
                val = val[:-2]
            return val

        return ""

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df["Dosage Amount"] = df["Pack"].apply(self._extract)
        return df
