"""Entry point for Claim Data Cleaner — NiceGUI native mode."""
import sys
import os
from pathlib import Path

# PyInstaller frozen-app path fixup
if getattr(sys, 'frozen', False):
    os.chdir(Path(sys.executable).parent)

sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui
from ui.app_ui import AppUI
from ui.styles import add_styles


def main():
    add_styles()
    AppUI()
    ui.run(
        native=True,
        window_size=(1000, 750),
        title='Claim Data Cleaner',
        reload=False,
        favicon='🧹',
    )


if __name__ == '__main__':
    main()
