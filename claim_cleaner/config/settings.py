"""Application settings — loaded from settings.json if present, otherwise defaults."""
import json
import os
from pathlib import Path

APP_NAME = "Claim Data Cleaner"
APP_VERSION = "1.0"

# Directory layout
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILES_DIR = BASE_DIR / "config_files"
SETTINGS_FILE = BASE_DIR / "settings.json"

CONFIG_FILES_DIR.mkdir(parents=True, exist_ok=True)

# Defaults — override via settings.json
_DEFAULTS = {
    "sharepoint_site_url": "",
    "sharepoint_folder_path": "",
    "sharepoint_filename": "master_config.xlsx",
    "azure_ad_client_id": "",
    "azure_ad_tenant_id": "",
    "local_master_config": str(CONFIG_FILES_DIR / "master_config.xlsx"),
    "last_sharepoint_sync": "",
    "fuzzy_threshold": 2,
}


def load() -> dict:
    settings = dict(_DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            settings.update(overrides)
        except Exception:
            pass
    return settings


def save(data: dict) -> None:
    current = load()
    current.update(data)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
