"""Exact match against name_rule (Step 3b)."""
from __future__ import annotations

import pandas as pd


class ExactMatcher:
    """Builds a lookup dict from old_Service_Provider → new_Service_Provider (case-insensitive)."""

    def __init__(self, name_rules: pd.DataFrame) -> None:
        # Keys are lowercase for case-insensitive matching (Bug 4)
        self._lookup: dict[str, str] = {}
        for _, row in name_rules.iterrows():
            old = str(row["old_Service Provider"]) if pd.notna(row["old_Service Provider"]) else ""
            new = str(row["new_Service Provider"]) if pd.notna(row["new_Service Provider"]) else ""
            key = old.strip().lower()
            if key:
                self._lookup[key] = new

        # Lowercase-keyed set of known clean names for segment matching
        self._clean_lower: dict[str, str] = {v.lower(): v for v in self._lookup.values()}

    def match(self, raw: str) -> str | None:
        """Return cleaned name if exact match (case-insensitive), else None."""
        return self._lookup.get(raw.strip().lower())

    def match_segment(self, segment: str) -> str | None:
        """Check if a segment IS a known clean institution name (case-insensitive)."""
        seg = segment.strip().lower()
        if seg in self._clean_lower:
            return self._clean_lower[seg]
        return None
