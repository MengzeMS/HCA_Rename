"""Exact match against name_rule (Step 3b)."""
from __future__ import annotations

import pandas as pd


class ExactMatcher:
    """Builds a lookup dict from old_Service_Provider → new_Service_Provider."""

    def __init__(self, name_rules: pd.DataFrame) -> None:
        # Key: raw value stripped of leading/trailing whitespace only
        self._lookup: dict[str, str] = {}
        for _, row in name_rules.iterrows():
            old = str(row["old_Service Provider"]) if pd.notna(row["old_Service Provider"]) else ""
            new = str(row["new_Service Provider"]) if pd.notna(row["new_Service Provider"]) else ""
            key = old.strip()
            if key:
                self._lookup[key] = new

    def match(self, raw: str) -> str | None:
        """Return cleaned name if exact match, else None."""
        return self._lookup.get(raw.strip())

    def match_segment(self, segment: str) -> str | None:
        """Check if a segment matches any new_Service_Provider value (known clean institutions)."""
        # We want to detect if a segment IS a known clean institution name
        clean_names = set(self._lookup.values())
        seg = segment.strip()
        if seg in clean_names:
            return seg
        return None
