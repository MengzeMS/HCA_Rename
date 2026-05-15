import os
import sys
import nicegui

nicegui_dir = os.path.dirname(nicegui.__file__)

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        (nicegui_dir, 'nicegui'),  # bundle all NiceGUI assets
        ('config_files/master_config.xlsx', 'config_files'),
    ],
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
        'pipeline.utils',
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
