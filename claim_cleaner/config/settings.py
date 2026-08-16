"""Application settings — loaded from settings.json if present, otherwise defaults."""
import json
import sys
from pathlib import Path

APP_NAME = "Claim Data Cleaner"
APP_VERSION = "1.0"

# When frozen by PyInstaller, __file__ points inside the one-file extraction
# directory, which is deleted when the app exits. Anything the user needs to keep
# — settings.json, their config workbooks, processed_data/ and Logs/ — must live
# next to the .exe instead, so paths are resolved from sys.executable.
FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    BASE_DIR = Path(sys.executable).resolve().parent
    # Read-only assets bundled into the executable are unpacked here.
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    # Outputs sit beside the .exe, where the user can find them.
    _APP_BASE_DIR = BASE_DIR
else:
    BASE_DIR = Path(__file__).resolve().parent.parent   # = claim_cleaner/
    BUNDLE_DIR = BASE_DIR
    # Output directories live one level above claim_cleaner/ (the "Dashboard_APP" folder)
    _APP_BASE_DIR = BASE_DIR.parent

CONFIG_FILES_DIR = BASE_DIR / "config_files"
SETTINGS_FILE = BASE_DIR / "settings.json"

CONFIG_FILES_DIR.mkdir(parents=True, exist_ok=True)


def _default_config_path(filename: str) -> str:
    """
    Prefer a workbook the user has placed in config_files/ next to the app. Fall
    back to a copy bundled into the executable, if one was shipped. The returned
    path may not exist — the user picks the real file in the UI.
    """
    local = CONFIG_FILES_DIR / filename
    if local.exists() or not FROZEN:
        return str(local)
    bundled = BUNDLE_DIR / "config_files" / filename
    return str(bundled if bundled.exists() else local)


_DEFAULTS = {
    "local_master_config":         _default_config_path("master_config.xlsx"),
    "local_request_config":        _default_config_path("request_comparison.xlsx"),
    "local_enhertu_config":        _default_config_path("enhertu_config.xlsx"),
    "local_enhertu_claims_config": _default_config_path("enhertu_claims_config.xlsx"),
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
