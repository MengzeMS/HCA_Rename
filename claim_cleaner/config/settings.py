"""Application settings — loaded from settings.json if present, otherwise defaults."""
import json
from pathlib import Path

APP_NAME = "Claim Data Cleaner"
APP_VERSION = "1.0"

BASE_DIR = Path(__file__).resolve().parent.parent   # = claim_cleaner/
CONFIG_FILES_DIR = BASE_DIR / "config_files"
SETTINGS_FILE = BASE_DIR / "settings.json"

# Output directories live one level above claim_cleaner/ (the "Dashboard_APP" folder)
_APP_BASE_DIR = BASE_DIR.parent

CONFIG_FILES_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULTS = {
    "local_master_config":  str(CONFIG_FILES_DIR / "master_config.xlsx"),
    "local_request_config": str(CONFIG_FILES_DIR / "request_comparison.xlsx"),
    "local_enhertu_config":        str(CONFIG_FILES_DIR / "enhertu_config.xlsx"),
    "local_enhertu_claims_config": str(CONFIG_FILES_DIR / "enhertu_claims_config.xlsx"),
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


def get_app_output_dirs() -> tuple[Path, Path]:
    """Return (processed_data_dir, logs_dir), creating them if needed."""
    processed = _APP_BASE_DIR / "processed_data"
    logs = _APP_BASE_DIR / "Logs"
    processed.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    return processed, logs
