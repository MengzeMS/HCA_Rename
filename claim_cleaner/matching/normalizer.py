"""Character equivalence normalization and legal suffix removal."""
from __future__ import annotations

import re

# Character equivalence map (bidirectional: apply both directions when comparing)
CHAR_EQUIV: list[tuple[str, str]] = [
    ("ü", "ue"),
    ("ö", "oe"),
    ("ä", "ae"),
    ("ß", "ss"),
    ("é", "e"),
    ("è", "e"),
    ("ê", "e"),
    ("à", "a"),
    ("â", "a"),
    ("ç", "c"),
    ("ô", "o"),
    ("î", "i"),
    ("ù", "u"),
]

# Legal suffix patterns to strip (case-insensitive, at end of string)
_LEGAL_SUFFIXES = re.compile(
    r"\s*\b(AG|SA|GmbH|S\.A\.|Sàrl|Sarl|sàrl)\s*$", re.IGNORECASE
)

# Location-after-comma pattern (strip ", City" from end) — skip for pharmacies
_LOCATION_COMMA = re.compile(r",\s*[A-Za-züöäÜÖÄéàâêèùôî\s\-]+$")

# Trailing dash pattern (e.g. "Lindenhofgruppe AG -" → strip " -" at end)
_TRAILING_DASH = re.compile(r"\s*-\s*$")

# Hyphen in compound names
_COMPOUND_HYPHEN = re.compile(r"(?<=[A-Za-züöä])-(?=[A-Za-züöä])")

# Bilingual → German
_BILINGUALS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bBienne\b", re.IGNORECASE), "Biel"),
    (re.compile(r"\bValais\b", re.IGNORECASE), "Wallis"),
    (re.compile(r"\bFribourg\b", re.IGNORECASE), "Freiburg"),
    (re.compile(r"\bGen[eè]ve\b", re.IGNORECASE), "Genf"),
    (re.compile(r"\bNeuch[aâ]tel\b", re.IGNORECASE), "Neuenburg"),
    (re.compile(r"\bLucerne\b", re.IGNORECASE), "Luzern"),
]

# HOCH hospital group facilities
HOCH_FACILITIES: list[str] = [
    "Kantonsspital St. Gallen",
    "Spital Altstätten",
    "Spital Linth",
    "Spital Grabs",
    "Spital Wil",
    "Ambi Flawil",
    "Ambulatorium Rorschach",
    "Gesundheitszentrum Rorschach",
    "Spezialarztpraxis Sargans",
    "Spitalregion Fürstenland Toggenburg",
]

# Keywords identifying pharmacies (location-suffix removal is skipped for these)
_PHARMACY_KEYWORDS = re.compile(
    r"\b(Apotheke|Pharmacie|Farmacia|Drogerie)\b", re.IGNORECASE
)

# Known institution keyword patterns (used to detect non-person segments)
INSTITUTION_KEYWORDS = re.compile(
    r"\b(Spital|Klinik|Apotheke|Pharmacie|Farmacia|Kantonsspital|Praxis|Zentrum|"
    r"Centre|Drogerie|Ambulatorium|Gesundheitszentrum|H[oô]pital|Ospedale|"
    r"Groupe|Gruppenpraxis|Institut|Polyklinik|Ambulanz)\b",
    re.IGNORECASE,
)

# Title patterns for person-name detection (used in _looks_like_person)
TITLE_PATTERN = re.compile(
    r"\b(Dr\.?\s*m[eé]d\.|Dr\.?\s*phil\.|Dr\.|Prof\.|med\.?\s*pract\.|dipl\.|"
    r"Doctoresse|Docteur|PD)\b",
    re.IGNORECASE,
)


def remove_legal_suffixes(text: str) -> str:
    return _LEGAL_SUFFIXES.sub("", text).strip()


def _strip_trailing_period(text: str) -> str:
    """Strip a single trailing period only if it's the very last character."""
    if text.endswith("."):
        return text[:-1].rstrip()
    return text


def apply_char_equivalence(text: str) -> str:
    """Fold special characters to ASCII equivalents (lowercase)."""
    t = text.lower()
    for special, equiv in CHAR_EQUIV:
        t = t.replace(special, equiv)
        t = t.replace(equiv, special)  # normalise back to special form (pick one direction)
    # Actually just fold to the ascii form for comparison purposes
    t = text.lower()
    for special, equiv in CHAR_EQUIV:
        t = t.replace(special, equiv)
    return t


def normalize_for_fuzzy(text: str) -> str:
    """Normalize text for fuzzy comparison: lowercase, strip, remove legal suffixes, collapse whitespace."""
    t = text.strip().lower()
    t = remove_legal_suffixes(t)
    t = re.sub(r"\s+", " ", t)
    return t


def _check_hoch(name: str) -> bool:
    """Return True if name matches a HOCH facility (case-insensitive prefix/exact)."""
    name_lower = name.lower().strip()
    for facility in HOCH_FACILITIES:
        if name_lower == facility.lower() or name_lower.startswith(facility.lower()):
            return True
    return False


def post_match_cleanup(name: str) -> str:
    """
    Apply Step 3i post-matching cleanup to a resolved provider name.
    Applied only for code-match, name-match, fuzzy, manual-review-needed.
    """
    if not name or not name.strip():
        return name

    result = name.strip()

    # Check HOCH membership on original value before any stripping truncates it
    if _check_hoch(result):
        return "HOCH"

    # Strip trailing " -" or "-" before suffix removal (Bug 3)
    result = _TRAILING_DASH.sub("", result).strip()

    # Remove legal suffixes
    result = remove_legal_suffixes(result)

    # Strip trailing " -" again after suffix removal (Bug 3)
    result = _TRAILING_DASH.sub("", result).strip()

    # Strip trailing period only (Bug 1: never split on mid-string periods)
    result = _strip_trailing_period(result)

    # Remove location after comma — skip for pharmacies
    if not _PHARMACY_KEYWORDS.search(result):
        result = _LOCATION_COMMA.sub("", result).strip()
        # Check HOCH again after comma removal (e.g., "Kantonsspital St. Gallen, ...")
        if _check_hoch(result):
            return "HOCH"

    # Remove hyphens in compound names
    result = _COMPOUND_HYPHEN.sub(" ", result)

    # Bilingual → German
    for pattern, replacement in _BILINGUALS:
        result = pattern.sub(replacement, result)

    # Hospital group mapping (LAST step)
    if _check_hoch(result):
        return "HOCH"

    return result
