# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import glob
from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

# Project absolute path ensures local imports (e.g., ticker_utils_numba) are discovered
# When PyInstaller runs a .spec file `__file__` may not be defined; use cwd instead
project_dir = os.path.abspath(os.getcwd())
pathex = [project_dir]

# Collect native dynamic libs from packages that ship DLLs to prevent missing DLL warnings
# collect_dynamic_libs returns a list of tuples suitable for the Analysis 'binaries' arg
binaries = []
for pkg in ('numba', 'llvmlite', 'numpy', 'tbb'):
    try:
        binaries += collect_dynamic_libs(pkg)
    except Exception:
        pass

# Also look for tbb DLLs installed in the current Python environment (e.g., from Intel TBB)
try:
    site_pkgs = os.path.join(sys.prefix, 'Lib', 'site-packages')
    for dll in glob.glob(os.path.join(site_pkgs, '**', 'tbb*.dll'), recursive=True):
        # append as (src, dest_dir)
        binaries.append((dll, '.'))
except Exception:
    pass

# Also search common Program Files locations for installed TBB redistributables
for root in (r"C:\Program Files", r"C:\Program Files (x86)", r"C:\Program Files\Intel", r"C:\Program Files\Intel\oneAPI"):
    try:
        for dll in glob.glob(os.path.join(root, '**', 'tbb*.dll'), recursive=True):
            binaries.append((dll, '.'))
    except Exception:
        pass

# User-provided explicit tbb DLL path (ensure this is bundled)
explicit_tbb = r"C:\Users\prc\AppData\Local\Programs\Python\Python314\Library\bin\tbb12.dll"
if os.path.exists(explicit_tbb):
    binaries.append((explicit_tbb, '.'))


a = Analysis(
    ['TCKR-v1.0.2026.0212.1214.py'],
    pathex=pathex,
    binaries=binaries,
    datas=[('TCKR.ico', '.'), ('SubwayTicker.ttf', '.'), ('notify.wav', '.')],
    hiddenimports=['PyQt5.QtMultimedia', 'PyQt5.sip', 'requests', 'psutil', 'ticker_utils_numba', 'memory_pool', 'numba', 'numba.cloudpickle.cloudpickle_fast', 'numba.cloudpickle.cloudpickle', 'llvmlite.binding'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Exclude a scipy helper that isn't present in many installs and only triggers warnings
    excludes=['scipy.special._cdflib'],
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
    name='TCKR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Disable UPX to reduce failures and speed up build; set True if you need smaller EXE
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[os.path.join(project_dir, 'TCKR.ico')],
    version=os.path.join(project_dir, "version.txt"),
)

