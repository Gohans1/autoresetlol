# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_dynamic_libs

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=collect_dynamic_libs('PIL'),
    datas=[
        ('assets/avatar.ico', 'assets'),
        ('assets/avatar.png', 'assets'),
    ],
    # PIL._imaging is a C extension; the Pillow-12 hook misses it on some
    # Python versions, so pin it explicitly.
    hiddenimports=['PIL._imaging', 'PIL._tkinter_finder'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AntiFateEngine_v2.0',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/avatar.ico',
)
