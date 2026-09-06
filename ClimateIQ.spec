# ClimateIQ.spec  —  PyInstaller build specification
# ══════════════════════════════════════════════════════
# Run from project root:
#     pyinstaller ClimateIQ.spec
#
# Output:  dist/ClimateIQ/ClimateIQ.exe   (folder mode)
#          dist/ClimateIQ.exe             (one-file mode — see note below)
# ══════════════════════════════════════════════════════

import sys
from pathlib import Path

ROOT = Path(SPECPATH)          # project root (where this .spec lives)

block_cipher = None

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Embed the SQLite database inside the package
        (str(ROOT / 'database' / 'climate_data.db'), 'database'),
        # Include the icon
        (str(ROOT / 'climateiq.ico'), '.'),
    ],
    hiddenimports=[
        'urllib',
        'urllib.request',
        'urllib.parse',
        'html',
        'html.parser',
        'html.entities',
        # PyQt6 modules that PyInstaller sometimes misses
        'PyQt6.QtPrintSupport',
        'PyQt6.QtSvg',
        # Data science
        'pandas',
        'numpy',
        'matplotlib',
        'matplotlib.backends.backend_qt5agg',
        'matplotlib.backends.backend_agg',
        # Sentiment
        'vaderSentiment',
        'vaderSentiment.vaderSentiment',
        # PDF
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.lib',
        'reportlab.platypus',
        # AI (optional — comment out if not using)
        'anthropic',
        # SQLite (stdlib — always available)
        'sqlite3',
        # unittest + pyparsing needed by matplotlib — Python 3.14 fix
        'unittest',
        'unittest.mock',
        'unittest.case',
        'unittest.util',
        'unittest.result',
        'unittest.suite',
        'pyparsing',
        'pyparsing.testing',
        'pyparsing.core',
        'pyparsing.helpers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused large packages to reduce .exe size
        'tkinter',
        'xmlrpc',
        'multiprocessing',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── One-folder EXE (recommended for FYP demo) ────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ClimateIQ',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # compress — requires UPX installed (optional)
    console=False,               # no black console window
    icon=str(ROOT / 'climateiq.ico'),
    version='version_info.txt',  # Windows version metadata (see below)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ClimateIQ',
)

# ── Uncomment below for SINGLE .exe (slower startup, larger file) ─────────────
# exe_onefile = EXE(
#     pyz,
#     a.scripts,
#     a.binaries,
#     a.zipfiles,
#     a.datas,
#     name='ClimateIQ',
#     debug=False,
#     strip=False,
#     upx=True,
#     console=False,
#     icon=str(ROOT / 'climateiq.ico'),
# )
