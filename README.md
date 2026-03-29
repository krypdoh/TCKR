
# TCKR — Real-Time Stock Ticker for Windows

TCKR is a sophisticated, real-time stock ticker application for Windows. It creates a persistent, scrolling bar at the top of your screen to track stock prices and market indices, with a modern LED-inspired look and advanced performance optimizations.

---

## 🚀 Quick Start

1. **Requirements:**
    - Python 3.8–3.14 (64-bit recommended)
    - Windows 10/11
    - [PyQt5](https://pypi.org/project/PyQt5/), [requests](https://pypi.org/project/requests/), [Numba](https://pypi.org/project/numba/) (optional, for performance)
    - See `requirements.txt` for all dependencies

2. **Minimum Files Needed:**
    - `TCKR-v1.1.0.py` (main app)
    - `modern_gui_styles.py` (styling)
    - `ticker_utils_numba.py` (performance, optional but recommended)
    - `TCKR.ico` (tray icon, optional)
    - See [file_requirements.md](file_requirements.md) and [CHECKLIST.md](CHECKLIST.md) for full details

3. **Run:**
    ```sh
    python TCKR-v1.1.0.py
    ```
    - On first run, user settings and stock lists are created in `%APPDATA%\TCKR\`.

---

## 🗂️ File Reference

See [file_requirements.md](file_requirements.md) for a complete, categorized list.

### Required
| File | Purpose |
|---|---|
| `TCKR-v1.1.0.py` | Main application |
| `modern_gui_styles.py` | Dark theme/styling |

### Optional (Recommended/Enhanced)
| File | What you lose without it |
|---|---|
| `ticker_utils_numba.py` | Numba-accelerated math (slower fallback if missing) |
| `ticker_utils_cython.pyx` | Fastest math (optional, needs build) |
| `setup_cython.py` | Build script for Cython extension |
| `memory_pool.py` | QPixmap memory pooling (minor perf) |
| `TCKR.ico` | Tray icon |
| `notify.wav` | Price update sound |
| `neon_check.png` | Market "Open" icon |
| `neon_cross.png` | Market "Closed" icon |

### Auto-generated at Runtime
All stored in `%APPDATA%\TCKR\`:
| File | Created by |
|---|---|
| `TCKR.Settings.json` | First run |
| `TCKR.Tickers.json` | First run |
| `TCKR.images\*.png` | Downloaded as needed |

---

## ✨ Features

- **Real-Time Tracking:** Live stock prices and indices (S&P 500, NASDAQ, Dow Jones, etc.)
- **Windows AppBar Integration:** "Docks" at the top of your screen, reserving space
- **Multi-Monitor Support:** Choose display in settings
- **Retro LED Aesthetic:** Scanlines, pixel grid, and neon effects
- **Advanced Visual Effects:** Bloom, motion blur, glass glare, text glow
- **High Performance:** Hardware-accelerated PyQt5 rendering, 60 FPS
- **Smart Update Intervals:** Market-aware, reduces API calls off-hours ([see timing details](TIMING_OVERVIEW.md))
- **User Customization:** Tray menu, adjustable speed, transparency, font, and more
- **Modern GUI:** Compact, dark-themed dialogs ([see MODERN_GUI_GUIDE.md](MODERN_GUI_GUIDE.md))
- **Performance Optimizations:** Connection pooling, Numba JIT, memory pooling, progressive loading

---

## 📈 Performance & Optimization

TCKR is optimized for smooth, stutter-free scrolling and efficient resource usage.

- **Rendering:** Continuous, VSync-paced 60 FPS (see changelog for details)
- **Startup:** Progressive loading for up to 40–60% faster perceived startup
- **Memory:** Icon and settings caching, LRU eviction, optional pixmap pooling
- **Network:** Persistent HTTP sessions, reduced API calls off-hours
- **Measured Results:**
  - Startup: Up to 40–60% faster (with progressive loading)
  - Memory: Lower peak usage on icon-heavy/long sessions
  - Rendering: Stable 60 FPS, no stutter/flash
  - See [PERFORMANCE_OPTIMIZATIONS.md](PERFORMANCE_OPTIMIZATIONS.md) for full details

---

## 📝 Changelog & Version History

See [changelog.txt](changelog.txt) for a detailed, dated history of all changes, bugfixes, and performance improvements.

Recent highlights:
- Major performance overhaul (Jan 2026):
  - Continuous rendering, stable 60 FPS
  - Deferred price updates, optimized bloom, memory pooling
- GUI modernization: Compact, dark-themed dialogs
- Smart update intervals and error backoff

---

## 📚 Technical Guides

- [file_requirements.md](file_requirements.md): Full file/dependency breakdown
- [CHECKLIST.md](CHECKLIST.md): Build & run checklist
- [PERFORMANCE_OPTIMIZATIONS.md](PERFORMANCE_OPTIMIZATIONS.md): User-facing performance summary
- [TIMING_OVERVIEW.md](TIMING_OVERVIEW.md): How price fetching and update intervals work
- [MODERN_GUI_GUIDE.md](MODERN_GUI_GUIDE.md): How to apply the modern UI theme

---

**In short:** TCKR is a highly polished, dockable desktop utility for traders and enthusiasts who want to keep an eye on the market—without switching away from their active work windows. For full details, see the guides and changelog above.