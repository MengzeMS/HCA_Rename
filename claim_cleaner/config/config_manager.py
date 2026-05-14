"""Master config loader: reads the single .xlsx file and validates required sheets."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Required sheet names (exact) except HCP_universe which is prefix-matched
REQUIRED_SHEETS = ["indication_rule", "dosage_rule", "BU_rule", "name_rule"]
HCP_UNIVERSE_PREFIX = "HCP_universe"

# Required columns per sheet
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

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            raise ConfigError(f"Master config file not found: {self.path}")

        try:
            xl = pd.ExcelFile(self.path, engine="openpyxl")
        except Exception as exc:
            raise ConfigError(f"Cannot open master config: {exc}") from exc

        sheet_names = xl.sheet_names
        self.sheet_count = len(sheet_names)

        # Check required named sheets
        for sheet in REQUIRED_SHEETS:
            if sheet not in sheet_names:
                raise ConfigError(f"Required sheet '{sheet}' not found in master config.")

        # Find HCP_universe sheet (prefix match)
        hcp_sheets = [s for s in sheet_names if s.startswith(HCP_UNIVERSE_PREFIX)]
        if not hcp_sheets:
            raise ConfigError(
                f"No sheet starting with '{HCP_UNIVERSE_PREFIX}' found in master config."
            )
        self.hcp_sheet_name = hcp_sheets[0]

        # Load each sheet
        self.indication_rules = self._read_sheet(xl, "indication_rule", SHEET_COLUMNS["indication_rule"])
        self.dosage_rules = self._read_sheet(xl, "dosage_rule", SHEET_COLUMNS["dosage_rule"])
        self.bu_rules = self._read_sheet(xl, "BU_rule", SHEET_COLUMNS["BU_rule"])
        self.name_rules = self._read_sheet(xl, "name_rule", SHEET_COLUMNS["name_rule"])
        self.hcp_universe = self._read_sheet(
            xl, self.hcp_sheet_name, SHEET_COLUMNS[HCP_UNIVERSE_PREFIX]
        )

        logger.info(
            "Config loaded: indication=%d, dosage=%d, BU=%d, name_rule=%d, HCP=%d rows",
            len(self.indication_rules),
            len(self.dosage_rules),
            len(self.bu_rules),
            len(self.name_rules),
            len(self.hcp_universe),
        )

    def _read_sheet(
        self, xl: pd.ExcelFile, sheet: str, required_cols: list[str]
    ) -> pd.DataFrame:
        try:
            df = xl.parse(sheet)
        except Exception as exc:
            raise ConfigError(f"Cannot parse sheet '{sheet}': {exc}") from exc

        # Normalise column headers: strip whitespace
        df.columns = [str(c).strip() for c in df.columns]

        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            raise ConfigError(
                f"Sheet '{sheet}' is missing required columns: {missing}. "
                f"Found: {list(df.columns)}"
            )

        # Keep only required columns, drop fully-empty rows
        df = df[required_cols].copy()
        df.dropna(how="all", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df

    # ------------------------------------------------------------------
    def summary(self) -> str:
        return (
            f"sheets: {self.sheet_count} found | "
            f"indication_rule: {len(self.indication_rules)} rows | "
            f"name_rule: {len(self.name_rules)} rows | "
            f"HCP_universe ({self.hcp_sheet_name}): {len(self.hcp_universe)} rows"
        )


# ------------------------------------------------------------------
# SharePoint download helper
# ------------------------------------------------------------------

def download_from_sharepoint(settings: dict, dest_path: Path) -> None:
    """Authenticate via MSAL and download the master xlsx from SharePoint."""
    try:
        import msal  # type: ignore
        import requests  # type: ignore
    except ImportError as exc:
        raise ConfigError(f"SharePoint dependencies not installed: {exc}") from exc

    client_id = settings.get("azure_ad_client_id", "")
    tenant_id = settings.get("azure_ad_tenant_id", "")
    site_url = settings.get("sharepoint_site_url", "")
    folder_path = settings.get("sharepoint_folder_path", "")
    filename = settings.get("sharepoint_filename", "master_config.xlsx")

    if not all([client_id, tenant_id, site_url]):
        raise ConfigError(
            "SharePoint not configured. Set azure_ad_client_id, azure_ad_tenant_id, "
            "and sharepoint_site_url in settings.json."
        )

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    scopes = ["https://graph.microsoft.com/.default"]

    app = msal.PublicClientApplication(client_id, authority=authority)

    # Try silent first, then interactive
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
    if not result:
        result = app.acquire_token_interactive(scopes=scopes)

    if "access_token" not in result:
        raise ConfigError(f"Authentication failed: {result.get('error_description', result)}")

    token = result["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Resolve SharePoint site ID via Graph API
    from urllib.parse import urlparse, quote

    parsed = urlparse(site_url)
    hostname = parsed.netloc
    site_path = parsed.path.rstrip("/")
    graph_site_url = (
        f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}"
    )
    resp = requests.get(graph_site_url, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise ConfigError(f"Cannot resolve SharePoint site: {resp.text}")
    site_id = resp.json()["id"]

    # Get drives
    drives_resp = requests.get(
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives",
        headers=headers,
        timeout=30,
    )
    drives_resp.raise_for_status()
    drives = drives_resp.json().get("value", [])
    if not drives:
        raise ConfigError("No document libraries found on SharePoint site.")
    drive_id = drives[0]["id"]

    # Build file path
    file_graph_path = f"{folder_path}/{filename}".lstrip("/")
    file_url = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
        f"/root:/{quote(file_graph_path)}:/content"
    )
    file_resp = requests.get(file_url, headers=headers, timeout=60, stream=True)
    if file_resp.status_code != 200:
        raise ConfigError(f"Cannot download file from SharePoint: {file_resp.text}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in file_resp.iter_content(chunk_size=8192):
            f.write(chunk)

    logger.info("Downloaded master config from SharePoint → %s", dest_path)
