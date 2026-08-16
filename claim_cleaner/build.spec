import os
import sys
import nicegui

nicegui_dir = os.path.dirname(nicegui.__file__)

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
    hiddenimports=[
        'nicegui',
        'nicegui.elements',
        'nicegui.elements.button',
        'nicegui.elements.card',
        'nicegui.elements.label',
        'nicegui.elements.progress',
        'nicegui.elements.number',
        'nicegui.elements.notify',
        'webview',
        'webview.platforms.winforms',
        'clr',
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
