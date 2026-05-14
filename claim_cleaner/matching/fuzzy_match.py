"""Fuzzy matching using rapidfuzz Levenshtein distance (Step 3g)."""
from __future__ import annotations

import pandas as pd

try:
    from rapidfuzz.distance import Levenshtein  # type: ignore
except ImportError:
    Levenshtein = None  # type: ignore

from .normalizer import normalize_for_fuzzy


class FuzzyMatcher:
    """Match normalized provider name against name_rule using edit distance."""

    def __init__(self, name_rules: pd.DataFrame, threshold: int = 2) -> None:
        self.threshold = threshold
        # Build list of (normalized_old, new) tuples
        self._entries: list[tuple[str, str]] = []
        for _, row in name_rules.iterrows():
            old = str(row["old_Service Provider"]) if pd.notna(row["old_Service Provider"]) else ""
            new = str(row["new_Service Provider"]) if pd.notna(row["new_Service Provider"]) else ""
            norm = normalize_for_fuzzy(old)
            if norm:
                self._entries.append((norm, new.strip()))

    def match(self, raw: str) -> str | None:
        """Return best matching new_Service_Provider within threshold, else None."""
        if Levenshtein is None:
            return None  # rapidfuzz not installed

        normalized = normalize_for_fuzzy(raw)
        if not normalized:
            return None

        best_dist = self.threshold + 1
        best_new = None

        for norm_old, new in self._entries:
            dist = Levenshtein.distance(
                normalized,
                norm_old,
                score_cutoff=self.threshold,
            )
            if dist <= self.threshold and dist < best_dist:
                best_dist = dist
                best_new = new

        return best_new
