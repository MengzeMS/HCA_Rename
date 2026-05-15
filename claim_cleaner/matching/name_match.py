"""HCP universe name matching (Step 3f)."""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from .normalizer import apply_char_equivalence, TITLE_PATTERN, INSTITUTION_KEYWORDS

# Known business abbreviations that identify institutions (not persons)
KNOWN_ABBREVS = re.compile(
    r"\b(LUKS|HUG|CHUV|HIB|SRO|EOC|ZIO|USZ|KSSG|UKBB|USB|InselH?|KSA|KSB|KSBL)\b",
    re.IGNORECASE,
)

# Comprehensive title strip pattern (superset of TITLE_PATTERN — for stripping, not detection)
_FULL_TITLE_STRIP = re.compile(
    r"(?:"
    r"Dr\.?\s*m[eé]d\."
    r"|Dr\.?\s*phil\."
    r"|Dr\.?\s*sc\.?\s*nat\."
    r"|Dr\.?\s*iur\."
    r"|Dr\.?\s*rer\.?\s*nat\."
    r"|med\.?\s*pract\."
    r"|PD\s+Dr\."
    r"|Prof\.?\s+Dr\."
    r"|Prof\."
    r"|Dr\."
    r"|PD"
    r"|dipl\."
    r"|Doctoresse"
    r"|Docteur"
    r"|Frau\s+Dr\."
    r"|Herr\s+Dr\."
    r"|Frau"
    r"|Herr"
    r")\s*",
    re.IGNORECASE,
)

# BEG prefix pattern: "BEG123 (Name)" or "123 (Name)"
_BEG_PATTERN = re.compile(r'^(?:BEG)?\d+\s*\((.+)\)\s*$', re.IGNORECASE)


def _strip_titles(text: str) -> str:
    """Remove medical/honorific titles from a name string."""
    cleaned = _FULL_TITLE_STRIP.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _looks_like_person(segment: str) -> bool:
    """Heuristic: does this segment look like a person name?"""
    if INSTITUTION_KEYWORDS.search(segment):
        return False
    if KNOWN_ABBREVS.search(segment):
        return False
    # Use both patterns: TITLE_PATTERN (imported) + _FULL_TITLE_STRIP (local, more comprehensive)
    if TITLE_PATTERN.search(segment) or _FULL_TITLE_STRIP.search(segment):
        return True
    # ≤3 words and no institution keywords
    words = segment.strip().split()
    if len(words) <= 3:
        return True
    return False


class NameMatcher:
    """Match segments against HCP_universe table using multiple strategies."""

    def __init__(self, hcp_universe: pd.DataFrame) -> None:
        self._records: list[dict] = []
        for _, row in hcp_universe.iterrows():
            hca = str(row["HCA"]).strip() if pd.notna(row["HCA"]) else ""
            last = str(row["LastName_c"]).strip() if pd.notna(row["LastName_c"]) else ""
            first = str(row["FirstName_c"]).strip() if pd.notna(row["FirstName_c"]) else ""
            if hca or last or first:
                self._records.append({"hca": hca, "last": last, "first": first})

        # Build lookup indices for fast matching
        self._by_full: dict[str, str] = {}   # "First Last" → HCA
        self._by_rev: dict[str, str] = {}    # "Last First" → HCA
        self._by_last: dict[str, list[dict]] = {}  # last → records

        for rec in self._records:
            hca, last, first = rec["hca"], rec["last"], rec["first"]
            full = f"{first} {last}".strip()
            rev = f"{last} {first}".strip()
            if full:
                self._by_full[full.lower()] = hca
                self._by_full[apply_char_equivalence(full)] = hca
            if rev:
                self._by_rev[rev.lower()] = hca
                self._by_rev[apply_char_equivalence(rev)] = hca
            if last:
                self._by_last.setdefault(last.lower(), []).append(rec)
                self._by_last.setdefault(apply_char_equivalence(last), []).append(rec)

    def match(self, segment: str) -> Optional[str]:
        """Return HCA value if segment matches a person in HCP_universe, else None."""
        seg = segment.strip()

        # BEG prefix pattern: "BEG123 (Name)" or "123 (Name)" — extract inner name
        beg_m = _BEG_PATTERN.match(seg)
        if beg_m:
            inner = beg_m.group(1).strip()
            result = self._match_candidate(inner) or self._match_candidate(_strip_titles(inner))
            if result:
                return result

        if not _looks_like_person(seg):
            return None

        stripped = _strip_titles(seg)
        candidates = [seg, stripped]

        for cand in candidates:
            result = self._match_candidate(cand)
            if result:
                return result
        return None

    def _match_candidate(self, name: str) -> Optional[str]:
        name_stripped = name.strip()
        name_lower = name_stripped.lower()
        name_equiv = apply_char_equivalence(name_stripped)

        # Strategy 1 & 2: exact full name (both orders)
        for key in (name_lower, name_equiv):
            if key in self._by_full:
                return self._by_full[key]
            if key in self._by_rev:
                return self._by_rev[key]

        # Strategy 4: abbreviated first name — "G. Rüttimann" → initial + last
        words = name_stripped.split()
        if len(words) >= 2:
            # Last word as last name, first word as abbreviated first name
            potential_last = words[-1]
            potential_first_abbrev = words[0].rstrip(".")
            last_key = potential_last.lower()
            last_equiv = apply_char_equivalence(potential_last)

            for lk in (last_key, last_equiv):
                records = self._by_last.get(lk, [])
                for rec in records:
                    if (
                        rec["first"]
                        and potential_first_abbrev
                        and rec["first"][0].lower() == potential_first_abbrev[0].lower()
                    ):
                        return rec["hca"]

        return None
