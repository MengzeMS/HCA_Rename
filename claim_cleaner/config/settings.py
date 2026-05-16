"""Application settings — loaded from settings.json if present, otherwise defaults."""
import json
from pathlib import Path

APP_NAME = "Claim Data Cleaner"
APP_VERSION = "1.0"

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILES_DIR = BASE_DIR / "config_files"
SETTINGS_FILE = BASE_DIR / "settings.json"

CONFIG_FILES_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULTS = {
    "local_master_config": str(CONFIG_FILES_DIR / "master_config.xlsx"),
    "local_request_config": str(CONFIG_FILES_DIR / "request_comparison.xlsx"),
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
