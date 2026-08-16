import os
import sys
import nicegui

from PyInstaller.utils.hooks import collect_submodules

nicegui_dir = os.path.dirname(nicegui.__file__)

# NiceGUI resolves element classes dynamically, so PyInstaller's static analysis
# misses most of nicegui.elements.*. Listing them by hand is how this build ended
# up shipping only a handful (button, card, label, ...) — any page using an
# element that was not listed fails to render with "Internal Server Error".
# Collect every submodule instead. Same for pywebview's platform backends.
nicegui_imports = collect_submodules('nicegui')
webview_imports = collect_submodules('webview')
print(f"build.spec: collected {len(nicegui_imports)} nicegui + "
      f"{len(webview_imports)} webview submodules")

block_cipher = None

# Only bundle the config workbooks that are actually present. Most of them are
# site-specific and are not committed to the repository, and PyInstaller aborts
# the whole build on a missing data file rather than skipping it.
_config_files = [
    'master_config.xlsx',
    'request_comparison.xlsx',
    'enhertu_config.xlsx',
    'enhertu_claims_config.xlsx',
]
config_datas = [
    (os.path.join('config_files', name), 'config_files')
    for name in _config_files
    if os.path.isfile(os.path.join('config_files', name))
]
print(f"build.spec: bundling {len(config_datas)} of {len(_config_files)} config files")

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        (nicegui_dir, 'nicegui'),  # bundle all NiceGUI assets
    ] + config_datas,
    hiddenimports=nicegui_imports + webview_imports + [
        # Explicit fallbacks in case collect_submodules finds nothing (e.g. the
        # package is not importable at spec-evaluation time).
        'nicegui',
        'webview',
        'webview.platforms.winforms',
        'clr',
        # File-picker dialogs in ui/app_ui.py.
        'tkinter',
        'tkinter.filedialog',
        'pandas',
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'rapidfuzz',
        'rapidfuzz.distance',
        'rapidfuzz.distance.Levenshtein',
        'ui',
        'ui.app_ui',
        'ui.styles',
        'config',
        'config.config_manager',
        'config.settings',
        'pipeline',
        'pipeline.orchestrator',
        'pipeline.step_indication',
        'pipeline.step_provider',
        'pipeline.step_dosage',
        'pipeline.step_bu',
        'pipeline.step_insurance',
        'pipeline.utils',
        'pipeline.request_pipeline',
        'pipeline.enhertu_pipeline',
        'pipeline.enhertu_claims_pipeline',
        'matching',
        'matching.normalizer',
        'matching.cell_parser',
        'matching.exact_match',
        'matching.code_match',
        'matching.name_match',
        'matching.fuzzy_match',
        'output',
        'output.writer',
        'output.log_writer',
        'chardet',
    ],
    hookspath=[],
    runtime_hooks=[],
    # tkinter must NOT be excluded — the file pickers depend on it.
    excludes=['matplotlib', 'scipy', 'notebook', 'IPython'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ClaimDataCleaner',
    debug=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    windowed=True,
    icon=None,
)
