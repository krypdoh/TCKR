# TCKR File Requirements

## Required — program will not start without these

| File | Purpose |
|---|---|
| `TCKR-v1.1.0.py` | Main application |
| `modern_gui_styles.py` | Dark theme/styling — imported unconditionally at startup (`from modern_gui_styles import *`) |

---

## Optional — included for enhanced functionality, gracefully skipped if absent

| File | What you lose without it |
|---|---|
| `TCKR.ico` | Tray icon (falls back to generic system icon) |
| `SubwayTicker.ttf` | LED-style font (falls back to Arial) |
| `notify.wav` | Price update sound (silently skipped) |
| `neon_check.png` | Market "Open" icon in ticker (just omitted) |
| `neon_cross.png` | Market "Closed" icon in ticker (just omitted if absent) |
| `ticker_utils_numba.py` | Numba-accelerated math (falls back to pure Python — slower but correct) |
| `ticker_utils_cython.pyx` | Cython-compiled math (fastest, optional, requires build; falls back to numba or pure Python) |
| `setup_cython.py` | Build script for ticker_utils_cython (needed only if building Cython extension) |
| `memory_pool.py` | QPixmap memory pooling (falls back to normal allocation — minor perf cost) |

---

## Auto-generated at runtime — never need to ship

All stored in `%APPDATA%\TCKR\`:

| File / Folder | Created by |
|---|---|
| `TCKR.Settings.json` | First run (populated with defaults) |
| `TCKR.Tickers.json` | First run (default tickers: ^GSPC, ^IXIC, ^DJI) |
| `TCKR.Settings.json.backup` | Auto-backup on every settings save |
| `TCKR.Tickers.json.backup` | Auto-backup on every tickers save |
| `TCKR.images\*.png` | Downloaded on demand per ticker from GitHub stock-icons repo |

---

## User-configured (optional, paths set inside the app)

| File | Where configured |
|---|---|
| Custom second ticker stocks `.json` | Settings → Dual Ticker → Second Ticker Stocks |
| SSL certificate `.pem` / `.crt` / `.cer` | Settings → Network → Certificate File |

---

## Minimum viable distribution

To ship a working build, only these files are strictly needed:

```
TCKR-v1.1.0.py              ← required (main app)
modern_gui_styles.py         ← required
ticker_utils_numba.py        ← recommended (performance)
ticker_utils_cython.pyx      ← optional (fastest, needs build)
setup_cython.py              ← optional (for Cython build)
memory_pool.py               ← optional (minor performance)
TCKR.ico                     ← recommended
notify.wav                   ← optional
neon_check.png               ← optional
neon_cross.png               ← optional
```
