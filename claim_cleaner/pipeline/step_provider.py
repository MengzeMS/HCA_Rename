"""Step 3: Service Provider matching and cleaning."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from matching.cell_parser import parse_segments
from matching.code_match import CodeMatcher, extract_code
from matching.exact_match import ExactMatcher
from matching.fuzzy_match import FuzzyMatcher
from matching.name_match import NameMatcher, KNOWN_ABBREVS
from matching.normalizer import (
    INSTITUTION_KEYWORDS,
    post_match_cleanup,
)

# Values that mean "empty"
_EMPTY_VALUES = {"", "?", "leer"}


@dataclass
class MatchResult:
    cleaned: str
    match_type: str
    match_details: str = ""


class ProviderStep:
    """
    Orchestrates all sub-steps of Service Provider matching (Step 3a–3i).
    Builds code mapping in a first pass, then processes each row.
    """

    def __init__(
        self,
        name_rules: pd.DataFrame,
        hcp_universe: pd.DataFrame,
        fuzzy_threshold: int = 2,
    ) -> None:
        self._exact = ExactMatcher(name_rules)
        self._code = CodeMatcher(name_rules)
        self._name = NameMatcher(hcp_universe)
        self._fuzzy = FuzzyMatcher(name_rules, threshold=fuzzy_threshold)
        self._known_clean_names: set[str] = set(
            str(row["new_Service Provider"]).strip()
            for _, row in name_rules.iterrows()
            if pd.notna(row["new_Service Provider"])
        )
        # Known hospital abbreviations that map to clean names
        self._abbrev_map: dict[str, str] = {}
        for _, row in name_rules.iterrows():
            old = str(row["old_Service Provider"]).strip() if pd.notna(row["old_Service Provider"]) else ""
            new = str(row["new_Service Provider"]).strip() if pd.notna(row["new_Service Provider"]) else ""
            if KNOWN_ABBREVS.match(old) and new:
                self._abbrev_map[old.upper()] = new

    def build_code_mapping(self, provider_series: pd.Series) -> None:
        """First pass: build within-file code→name mapping."""
        values = [str(v) for v in provider_series if pd.notna(v)]
        self._code.build_mapping(values)

    def process_row(self, raw: str) -> MatchResult:
        """Process a single Service Provider cell value through Steps 3a–3i."""
        raw_str = str(raw) if raw is not None else ""

        # Step 3a: empty / special values
        stripped_lower = raw_str.strip().lower()
        if stripped_lower in _EMPTY_VALUES:
            return MatchResult("Unknown", "empty")

        # Step 3b: exact match against name_rule
        exact = self._exact.match(raw_str)
        if exact is not None:
            # Skip Step 3i — exact-override result is already clean
            return MatchResult(exact, "exact-override", f"matched '{raw_str.strip()}'")

        # Step 3c: alphanumeric code matching
        code = extract_code(raw_str.strip())
        if code:
            code_result = self._code.match(raw_str)
            if code_result:
                cleaned = post_match_cleanup(code_result)
                return MatchResult(cleaned, "code-match", f"code={code}")
            # Code present but not resolvable — fall through to segment parsing

        # Step 3d: parse multi-line/composite cell
        segments = parse_segments(raw_str)

        # Step 3e: check segments against known institutions
        for seg in segments:
            # Check against known clean institution names
            if seg.strip() in self._known_clean_names:
                # segment-match → skip 3i
                return MatchResult(seg.strip(), "segment-match", f"known-institution: {seg.strip()}")

            # Check against known abbreviations (LUKS, HOCH, etc.)
            seg_upper = seg.strip().upper()
            if seg_upper in self._abbrev_map:
                return MatchResult(self._abbrev_map[seg_upper], "segment-match", f"abbrev: {seg.strip()}")

            # Check if segment is a known institution keyword match
            if INSTITUTION_KEYWORDS.search(seg) and not self._looks_like_only_person(seg):
                # Could be an institution not in name_rule — fuzzy match this segment
                fuzzy_seg = self._fuzzy.match(seg)
                if fuzzy_seg:
                    return MatchResult(fuzzy_seg, "segment-match", f"institution-fuzzy: {seg.strip()}")

        # Step 3f: name matching against HCP_universe
        for seg in segments:
            name_result = self._name.match(seg)
            if name_result:
                cleaned = post_match_cleanup(name_result)
                return MatchResult(cleaned, "name-match", f"HCP: {seg.strip()}")

        # Step 3g: fuzzy match against name_rule (whole raw value)
        fuzzy_result = self._fuzzy.match(raw_str)
        if fuzzy_result:
            cleaned = post_match_cleanup(fuzzy_result)
            return MatchResult(cleaned, "fuzzy", f"fuzzy on '{raw_str.strip()}'")

        # Also try fuzzy on individual segments
        for seg in segments:
            fuzzy_seg = self._fuzzy.match(seg)
            if fuzzy_seg:
                cleaned = post_match_cleanup(fuzzy_seg)
                return MatchResult(cleaned, "fuzzy", f"fuzzy-seg: {seg.strip()}")

        # Step 3h: no match
        trimmed = raw_str.strip()
        cleaned = post_match_cleanup(trimmed)
        return MatchResult(cleaned, "manual-review-needed", f"no match for '{trimmed}'")

    def _looks_like_only_person(self, seg: str) -> bool:
        """Return True if segment is purely a person name (no institution keywords)."""
        return not INSTITUTION_KEYWORDS.search(seg)

    def apply(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
        """
        Apply provider matching to DataFrame.
        Returns modified DataFrame and match log entries.
        """
        log_entries: list[dict] = []

        # First pass: build code mapping
        self.build_code_mapping(df["Service Provider"])

        # Second pass: process each row
        cleaned_values: list[str] = []
        for idx, row in df.iterrows():
            raw = str(row["Service Provider"]) if pd.notna(row["Service Provider"]) else ""
            result = self.process_row(raw)
            cleaned_values.append(result.cleaned)
            log_entries.append(
                {
                    "RowID": row.get("RowID", idx + 1),
                    "Raw_Service_Provider": raw,
                    "Clean_Service_Provider": result.cleaned,
                    "Match_Type": result.match_type,
                    "Match_Details": result.match_details,
                }
            )

        df["Service Provider"] = cleaned_values
        return df, log_entries
