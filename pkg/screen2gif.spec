# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import copy_metadata

# Bundle package metadata so importlib.metadata queries succeed at runtime
pkg_metadata = copy_metadata('imageio') + copy_metadata('imageio_ffmpeg')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('gif', 'gif'), ('video', 'video'), ('logs', 'logs')] + pkg_metadata,
    hiddenimports=['imageio', 'imageio_ffmpeg'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='screen2gif',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
)
