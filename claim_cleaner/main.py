"""Entry point for Claim Data Cleaner — NiceGUI native mode."""
import logging
import multiprocessing
import os
import sys
import traceback
from pathlib import Path

# PyInstaller frozen-app path fixup
if getattr(sys, 'frozen', False):
    os.chdir(Path(sys.executable).parent)

sys.path.insert(0, str(Path(__file__).parent))

from nicegui import native, ui
from ui.app_ui import AppUI
from ui.styles import add_styles

LOG_NAME = 'ClaimDataCleaner.log'


def _app_dir() -> Path:
    """Folder holding the .exe when frozen, else the source folder."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _setup_logging() -> Path:
    """
    Log to a file beside the app. A windowed build has no console, so without
    this any startup or request error is invisible and the window just shows
    "Internal Server Error".
    """
    log_path = _app_dir() / LOG_NAME
    try:
        logging.basicConfig(
            filename=str(log_path),
            filemode='a',
            level=logging.INFO,
            format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
        )
    except Exception:
        logging.basicConfig(level=logging.INFO)
    return log_path


def _install_excepthook(log_path: Path) -> None:
    def _hook(exc_type, exc, tb) -> None:
        logging.error('Unhandled exception:\n%s',
                      ''.join(traceback.format_exception(exc_type, exc, tb)))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = _hook


def main() -> None:
    log_path = _setup_logging()
    _install_excepthook(log_path)
    logging.info('Starting Claim Data Cleaner (frozen=%s) from %s',
                 getattr(sys, 'frozen', False), _app_dir())

    add_styles()
    AppUI()
    ui.run(
        native=True,
        window_size=(1000, 750),
        title='Claim Data Cleaner',
        reload=False,
        # Port 8080 is a common conflict; pick a free one instead.
        port=native.find_open_port(),
        favicon='🧹',
    )


if __name__ == '__main__':
    # Required on Windows: a frozen app re-executes itself to spawn the webview
    # subprocess, and without this the child re-runs main() instead.
    multiprocessing.freeze_support()
    main()
