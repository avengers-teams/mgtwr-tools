# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


rasterio_hiddenimports = collect_submodules('rasterio')
rasterio_datas = collect_data_files('rasterio')
rasterio_binaries = collect_dynamic_libs('rasterio')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=rasterio_binaries,
    datas=[('assets', 'assets'), ('version', '.')] + rasterio_datas,
    hiddenimports=rasterio_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['IPython', 'jupyter', 'notebook'],
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
    name='main',
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
    icon=['assets\\icons\\favicon.ico'],
)
