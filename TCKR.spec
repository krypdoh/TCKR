# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import glob
import importlib.util
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_all

block_cipher = None

# Use cwd for pathex so PyInstaller finds local modules
project_dir = os.path.abspath(os.getcwd())
pathex = [project_dir]

# Collect native dynamic libs for common packages
binaries = []

def _add_binary_unique(path, dest='.'):
    """Add a binary once (by normalized absolute path)."""
    norm = os.path.normcase(os.path.abspath(path))
    if norm in _seen_binary_paths:
        return
    _seen_binary_paths.add(norm)
    binaries.append((path, dest))


def _find_tbb_dll():
    """Pick one TBB DLL from the active Python environment only."""
    preferred = [
        os.path.join(sys.prefix, 'Library', 'bin', 'tbb12.dll'),
        os.path.join(sys.prefix, 'DLLs', 'tbb12.dll'),
    ]
    for candidate in preferred:
        if os.path.exists(candidate):
            return candidate

    env_roots = [
        os.path.join(sys.prefix, 'Lib', 'site-packages'),
        sys.prefix,
    ]
    patterns = ('tbb12.dll', 'tbb*.dll')
    for root in env_roots:
        if not os.path.isdir(root):
            continue
        for pattern in patterns:
            matches = glob.glob(os.path.join(root, '**', pattern), recursive=True)
            if matches:
                return matches[0]
    return None


_seen_binary_paths = set()
for pkg in ('numba', 'llvmlite', 'numpy'):
    try:
        for dll_path, dll_dest in collect_dynamic_libs(pkg):
            _add_binary_unique(dll_path, dll_dest)
    except Exception:
        pass

tbb_dll = _find_tbb_dll()
if tbb_dll:
    _add_binary_unique(tbb_dll, '.')

hiddenimports = [
    'PyQt5.QtMultimedia',
    'PyQt5.sip',
    'requests',
    'psutil',
    'ticker_utils_numba',
    'memory_pool',
    'numba',
    'numba.cloudpickle.cloudpickle_fast',
    'numba.cloudpickle.cloudpickle',
    'llvmlite.binding',
]

if importlib.util.find_spec('sip'):
    hiddenimports.append('sip')

datas = [
    ('TCKR.ico', '.'),
    ('SubwayTicker.ttf', '.'),
    ('notify.wav', '.'),
    ('neon_check.png', '.'),
    ('neon_cross.png', '.'),
]

# Collect full charset_normalizer bundle so Requests can resolve charset backend.
for dep in ('charset_normalizer',):
    if importlib.util.find_spec(dep):
        dep_datas, dep_bins, dep_hidden = collect_all(dep)
        datas += dep_datas
        for dll_path, dll_dest in dep_bins:
            _add_binary_unique(dll_path, dll_dest)
        hiddenimports += dep_hidden

a = Analysis(
    ['TCKR-v1.0.2026.0309.1050.py'],
    pathex=pathex,
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_requests_charset.py'],
    excludes=['scipy.special._cdflib', 'numba.np.ufunc.tbbpool'],
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
    version=os.path.join(project_dir, 'version.txt'),
)

