"""Alphanumeric code matching (Step 3c)."""
from __future__ import annotations

import re

import pandas as pd

# Code pattern: 1-2 letters + digits at start of string
_CODE_RE = re.compile(r"^([A-Za-z]{1,2}\d+)\b")


def extract_code(text: str) -> str | None:
    """Extract leading alphanumeric code from text, or None."""
    m = _CODE_RE.match(text.strip())
    return m.group(1) if m else None


def extract_code_and_remainder(text: str) -> tuple[str, str] | None:
    """
    If text starts with a code AND has meaningful text after it,
    return (code, remainder).  If it's ONLY a code, return (code, "").
    """
    stripped = text.strip()
    m = _CODE_RE.match(stripped)
    if not m:
        return None
    code = m.group(1)
    remainder = stripped[m.end():].strip()
    return code, remainder


class CodeMatcher:
    """
    Two-phase code matcher.

    Phase 1 (build_mapping): scan all Service Provider values in input
                             to build code → name mapping.
    Phase 2 (match):         resolve a single cell value via code lookup.
    """

    def __init__(self, name_rules: pd.DataFrame) -> None:
        # Also seed from name_rule (old → new, keyed by extracted code from old)
        self._file_map: dict[str, str] = {}  # built from input rows
        self._rule_map: dict[str, str] = {}  # built from name_rule

        for _, row in name_rules.iterrows():
            old = str(row["old_Service Provider"]) if pd.notna(row["old_Service Provider"]) else ""
            new = str(row["new_Service Provider"]) if pd.notna(row["new_Service Provider"]) else ""
            result = extract_code_and_remainder(old.strip())
            if result:
                code, _ = result
                if new.strip():
                    self._rule_map[code.upper()] = new.strip()

    def build_mapping(self, provider_values: list[str]) -> None:
        """First pass: scan all raw Service Provider values to build code→name mapping."""
        self._file_map.clear()
        for raw in provider_values:
            if not raw or not str(raw).strip():
                continue
            result = extract_code_and_remainder(str(raw).strip())
            if result is None:
                continue
            code, remainder = result
            if remainder:
                # code + meaningful text → store remainder as the resolved name
                key = code.upper()
                if key not in self._file_map:
                    self._file_map[key] = remainder

    def match(self, raw: str) -> str | None:
        """
        Return resolved name if the raw value starts with a known code, else None.
        Priority: file_map > rule_map.
        """
        result = extract_code_and_remainder(raw.strip())
        if result is None:
            return None
        code, remainder = result
        key = code.upper()

        # If cell is ONLY a code (no remainder), look up in maps
        if not remainder:
            if key in self._file_map:
                return self._file_map[key]
            if key in self._rule_map:
                return self._rule_map[key]
            return None

        # If cell has code + remainder, the remainder itself is the name
        # (we already resolved it in build_mapping, so just return remainder)
        return remainder if remainder else None
