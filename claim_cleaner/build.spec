# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for ClaimDataCleaner
# Build: pyinstaller build.spec
# Or:    pyinstaller --onefile --windowed --name "ClaimDataCleaner" main.py

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Bundle sample config if present
        ('config_files/master_config.xlsx', 'config_files'),
    ],
    hiddenimports=[
        # Pandas and openpyxl internals
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.utils',
        'pandas',
        'pandas._libs.tslibs.timedeltas',
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.skiplist',
        # Rapidfuzz
        'rapidfuzz',
        'rapidfuzz.distance',
        'rapidfuzz.distance.Levenshtein',
        # MSAL / requests for SharePoint
        'msal',
        'msal.application',
        'requests',
        # tkinter (usually auto-detected but listed for safety)
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        # Local packages
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
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude large/unnecessary packages
        'matplotlib',
        'scipy',
        'numpy.testing',
        'IPython',
        'notebook',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # --windowed: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows 11 icon (place a .ico file here to use it)
    # icon='assets/icon.ico',
)
