"""Master config loader — reads the .xlsx file and validates required sheets.
SharePoint sync removed; users select the file locally (works with OneDrive-synced paths).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_SHEETS = ["indication_rule", "dosage_rule", "BU_rule", "name_rule"]
HCP_UNIVERSE_PREFIX = "HCP_universe"

SHEET_COLUMNS = {
    "indication_rule": ["old_Indication", "new_Indication"],
    "dosage_rule": ["Pack", "Dosage Amount"],
    "BU_rule": ["Pack", "BU"],
    "name_rule": ["old_Service Provider", "new_Service Provider"],
    HCP_UNIVERSE_PREFIX: ["HCA", "LastName_c", "FirstName_c"],
}


class ConfigError(Exception):
    """Raised when the master config file is missing, corrupt, or incomplete."""


class MasterConfig:
    """Loaded and validated master configuration."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.indication_rules: pd.DataFrame = pd.DataFrame()
        self.dosage_rules: pd.DataFrame = pd.DataFrame()
        self.bu_rules: pd.DataFrame = pd.DataFrame()
        self.name_rules: pd.DataFrame = pd.DataFrame()
        self.hcp_universe: pd.DataFrame = pd.DataFrame()
        self.hcp_sheet_name: str = ""
        self.sheet_count: int = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            raise ConfigError(f"Master config file not found: {self.path}")

        try:
            xl = pd.ExcelFile(self.path, engine="openpyxl")
        except Exception as exc:
            raise ConfigError(f"Cannot open master config: {exc}") from exc

        sheet_names = xl.sheet_names
        self.sheet_count = len(sheet_names)

        for sheet in REQUIRED_SHEETS:
            if sheet not in sheet_names:
                raise ConfigError(
                    f"Required sheet '{sheet}' not found in master config.\n"
                    f"Available sheets: {sheet_names}"
                )

        hcp_sheets = [s for s in sheet_names if s.startswith(HCP_UNIVERSE_PREFIX)]
        if not hcp_sheets:
            raise ConfigError(
                f"No sheet starting with '{HCP_UNIVERSE_PREFIX}' found.\n"
                f"Available sheets: {sheet_names}"
            )
        self.hcp_sheet_name = hcp_sheets[0]

        self.indication_rules = self._read_sheet(xl, "indication_rule", SHEET_COLUMNS["indication_rule"])
        self.dosage_rules     = self._read_sheet(xl, "dosage_rule",     SHEET_COLUMNS["dosage_rule"])
        self.bu_rules         = self._read_sheet(xl, "BU_rule",         SHEET_COLUMNS["BU_rule"])
        self.name_rules       = self._read_sheet(xl, "name_rule",       SHEET_COLUMNS["name_rule"])
        self.hcp_universe     = self._read_sheet(xl, self.hcp_sheet_name, SHEET_COLUMNS[HCP_UNIVERSE_PREFIX])

        logger.info(
            "Config loaded: indication=%d, dosage=%d, BU=%d, name_rule=%d, HCP=%d rows",
            len(self.indication_rules), len(self.dosage_rules), len(self.bu_rules),
            len(self.name_rules), len(self.hcp_universe),
        )

    def _read_sheet(self, xl: pd.ExcelFile, sheet: str, required_cols: list[str]) -> pd.DataFrame:
        try:
            df = xl.parse(sheet, dtype=str)  # read everything as str to avoid float coercion
        except Exception as exc:
            raise ConfigError(f"Cannot parse sheet '{sheet}': {exc}") from exc

        # Strip whitespace from column headers
        df.columns = [str(c).strip() for c in df.columns]

        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ConfigError(
                f"Sheet '{sheet}' is missing columns: {missing}. Found: {list(df.columns)}"
            )

        df = df[required_cols].copy()
        df.dropna(how="all", inplace=True)

        # Replace NaN with empty string so lookups never see float('nan')
        for col in required_cols:
            df[col] = df[col].fillna("").astype(str)

        # Strip leading/trailing whitespace from the Dosage Amount column if numeric-looking
        # (dtype=str means "30.0" can appear — normalise to "30")
        if "Dosage Amount" in df.columns:
            def _clean_dosage(val: str) -> str:
                v = val.strip()
                try:
                    f = float(v)
                    return str(int(f)) if f == int(f) else str(f)
                except ValueError:
                    return v
            df["Dosage Amount"] = df["Dosage Amount"].apply(_clean_dosage)

        df.reset_index(drop=True, inplace=True)
        return df

    def summary(self) -> str:
        return (
            f"indication_rule: {len(self.indication_rules)} rows | "
            f"name_rule: {len(self.name_rules)} rows | "
            f"dosage_rule: {len(self.dosage_rules)} rows | "
            f"BU_rule: {len(self.bu_rules)} rows | "
            f"{self.hcp_sheet_name}: {len(self.hcp_universe)} rows"
        )

    def sheet_previews(self) -> dict[str, pd.DataFrame]:
        """Return first 3 rows of each sheet for debug display."""
        return {
            "indication_rule": self.indication_rules.head(3),
            "name_rule":       self.name_rules.head(3),
            "dosage_rule":     self.dosage_rules.head(3),
            "BU_rule":         self.bu_rules.head(3),
            self.hcp_sheet_name: self.hcp_universe.head(3),
        }
