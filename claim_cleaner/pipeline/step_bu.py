"""Step 5: BU assignment."""
from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


class BUStep:
    """Assigns BU from BU_rule by Pack value."""

    def __init__(self, bu_rules: pd.DataFrame) -> None:
        self._lookup: dict[str, str] = {}
        for _, row in bu_rules.iterrows():
            pack = str(row["Pack"]).strip() if pd.notna(row["Pack"]) else ""
            bu = str(row["BU"]).strip() if pd.notna(row["BU"]) else ""
            if pack:
                self._lookup[pack] = bu

    def _assign(self, pack: str) -> str:
        pack_stripped = pack.strip()
        if pack_stripped in self._lookup:
            return self._lookup[pack_stripped]
        logger.debug("Pack not found in BU_rule: %s", pack_stripped)
        return "Unknown BU"

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df["BU"] = df["Pack"].apply(self._assign)
        return df
