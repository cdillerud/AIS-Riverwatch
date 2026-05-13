# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for RiverWatchAISBridge.exe.

Build (on Windows, in a Python 3.10+ venv with PyInstaller installed):

    pyinstaller --clean -y riverwatch_ais_bridge.spec

Output:
    dist\\RiverWatchAISBridge\\RiverWatchAISBridge.exe
    dist\\RiverWatchAISBridge\\riverwatch_bridge.example.ini
    dist\\RiverWatchAISBridge\\README.txt
"""
from pathlib import Path

block_cipher = None

HERE = Path(SPECPATH).resolve()
SCRIPTS_DIR = HERE.parent  # /app/scripts on dev, /scripts in repo

a = Analysis(
    [str(HERE / 'riverwatch_ais_bridge.py')],
    pathex=[str(SCRIPTS_DIR)],
    binaries=[],
    datas=[
        (str(HERE / 'riverwatch_bridge.example.ini'), '.'),
        (str(HERE / 'README.md'), '.'),
        # Bundle the upstream sender as a regular Python module so the
        # frozen exe can `import ais_relay` from the bundle's _MEIPASS.
        (str(SCRIPTS_DIR / 'ais_relay.py'), '.'),
    ],
    hiddenimports=['ais_relay'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter', 'unittest', 'email', 'http.server',
        'xml', 'pydoc_data', 'distutils',
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
    [],
    exclude_binaries=True,
    name='RiverWatchAISBridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RiverWatchAISBridge',
)
