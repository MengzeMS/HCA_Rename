"""Parse multi-line / composite Service Provider cell values into candidate segments."""
from __future__ import annotations

import re

# Swiss postal code line: 4 digits + space + non-whitespace (e.g., "8805 Richterswil")
_POSTAL = re.compile(r"^\d{4}\s+\S+")

# Street address patterns (German/French/Italian)
_STREET = re.compile(
    r"(strasse|weg|gasse|platz|route|chemin|avenue|rue|via|piazza)",
    re.IGNORECASE,
)
_STREET_WITH_DIGITS = re.compile(r"\d")

# Salutation lines to discard
_SALUTATIONS = re.compile(
    r"^(Madame|Monsieur|Herr|Frau|Madame\s+la\s+Doctoresse|Monsieur\s+le\s+Docteur)\b",
    re.IGNORECASE,
)


def _is_address_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if _POSTAL.match(stripped):
        return True
    if _STREET.search(stripped) and _STREET_WITH_DIGITS.search(stripped):
        return True
    if _SALUTATIONS.match(stripped):
        return True
    return False


def parse_segments(raw: str) -> list[str]:
    """
    Split a raw cell value into meaningful candidate segments.

    Tries line-breaks first; falls back to comma splitting for patterns like
    "Dr. Name, Institution". Filters out address / salutation lines.
    Returns a list of non-empty candidate strings (stripped).
    """
    if not raw:
        return []

    # Split on line breaks
    lines = re.split(r"\r?\n", raw)

    if len(lines) > 1:
        candidates = [ln.strip() for ln in lines if ln.strip()]
    else:
        # No line breaks — try comma split for "Name, Location" patterns
        # Only split if comma is present
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        candidates = parts if len(parts) > 1 else [raw.strip()]

    # Filter address/salutation lines
    result = [c for c in candidates if not _is_address_line(c)]

    # Fall back to original if everything was filtered
    if not result and raw.strip():
        result = [raw.strip()]

    return result
