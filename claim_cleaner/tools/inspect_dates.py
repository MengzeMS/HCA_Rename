"""
Diagnostic: show exactly what the pipeline loader sees in a date column.

Excel displays a stored date according to your regional settings, so what you
read in a cell is not necessarily the text the loader receives. This prints the
raw Python value (via repr, so quoting and hidden times are visible) alongside
what the Enhertu SL rule turns it into.

Usage, from the claim_cleaner/ directory:

    python tools/inspect_dates.py "C:\\path\\to\\your_file.xlsx"
    python tools/inspect_dates.py "C:\\path\\to\\your_file.xlsx" Behandlungsdatum
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.utils import load_input_file, normalize_date  # noqa: E402

# The rule the Enhertu SL pipeline applies to Behandlungsdatum.
SL_RULE = {"/": False, ".": True}

MAX_ROWS = 15


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    path = Path(sys.argv[1])
    wanted = sys.argv[2] if len(sys.argv) > 2 else "Behandlungsdatum"

    if not path.exists():
        print(f"File not found: {path}")
        return 1

    # required_columns=[] skips validation so this works on any file.
    df = load_input_file(path, required_columns=[])

    print(f"File     : {path}")
    print(f"Suffix   : {path.suffix.lower()}")
    print(f"Rows     : {len(df):,}")
    print(f"Columns  : {list(df.columns)}")
    print()

    matches = [c for c in df.columns if c == wanted or c.startswith(wanted + ".")]
    if not matches:
        print(f"No column named {wanted!r} (or {wanted}.1, .2, ...) in this file.")
        return 1

    print(f"Found {len(matches)} matching column(s): {matches}")
    print()

    for col in matches:
        normalized = col == wanted  # only the exact name is normalized by the pipeline
        print("=" * 78)
        print(f"COLUMN {col!r} — {'normalized by pipeline' if normalized else 'passed through raw'}")
        print("=" * 78)
        print(f"{'row':>4}  {'raw value as loaded (repr)':38}  {'-> pipeline output'}")
        for i, val in enumerate(df[col].head(MAX_ROWS), start=1):
            out = normalize_date(val, sep_dayfirst=SL_RULE) if normalized else str(val)
            print(f"{i:>4}  {val!r:38}  -> {out}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
