"""
Build script for ticker_utils_cython.pyx

Usage:
    python setup_cython.py build_ext --inplace

Requirements:
    pip install cython numpy
    Visual C++ Build Tools 2022 ("Desktop development with C++")
"""

from setuptools import setup, Extension
import numpy as np

try:
    from Cython.Build import cythonize
except ImportError:
    raise SystemExit("Cython is required. Install with: pip install cython")

compiler_directives = {
    "language_level": "3",
    "boundscheck": False,
    "wraparound": False,
    "cdivision": True,
    "nonecheck": False,
    "embedsignature": False,
}

import sys
if sys.platform == "win32":
    extra_compile_args = ["/O2", "/fp:fast"]
    extra_link_args = []
else:
    extra_compile_args = ["-O3", "-ffast-math"]
    extra_link_args = ["-O3"]

ext = Extension(
    name="ticker_utils_cython",
    sources=["ticker_utils_cython.pyx"],
    include_dirs=[np.get_include()],
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
)

setup(
    name="ticker_utils_cython",
    ext_modules=cythonize(
        [ext],
        compiler_directives=compiler_directives,
        annotate=False,
    ),
)
