# TCKR — Real-Time Stock Ticker for Windows

![](https://github.com/krypdoh/TCKR/blob/main/docs/TCKR-screenshot0.png)

<img src="https://i.imgur.com/ORjiXB2.gif">

**Author:** Paul R. Charovkine  
**License:** GNU AGPLv3

---

## Description

TCKR is a customizable, high-performance real-time stock ticker for Windows that displays scrolling prices, logos, and market data as a persistent AppBar. Built with PyQt5 and featuring rich LED-style visual effects, it streams live prices via Finnhub WebSocket with REST API fallback, supports dual API keys with load balancing, and offers an optional second ticker bar with its own stock list and scroll speed.

*Prices may be delayed depending on your Finnhub account. For educational and entertainment purposes only.*

---

## Key Features

### Core Ticker
- **Real-time price streaming** via Finnhub WebSocket + REST API fallback
- **Dual API key support** with automatic load balancing
- **API key validation** — built-in TEST buttons verify keys with inline status feedback
- **Dual ticker bars** — optional second ticker with independent stock list and scroll speed
- **Persistent AppBar** integration — docks to screen top, reserves desktop space
- **Multi-monitor support** — choose which display to dock the ticker on
- **Crypto support** via CoinGecko integration

### Visual & Display
- **Smooth scrolling** with configurable scroll speed and ticker height
- **Historical mini-sparklines** — toggleable 1D/5D trend charts next to each symbol
  - Async fetch from Yahoo Finance with smart caching and TTL
  - Configurable placement: left or right of price/change
- **Price indicators** — multiple styles: right-angle triangles, thick arrows, thin arrows
  - Rotate dynamically based on price change magnitude
- **LED bloom/glow effect** with adjustable intensity (non-linear scaling)
- **Motion blur / ghosting** with adjustable intensity
- **LED icon matrix overlay** for retro CRT-style look
- **Glass cover with glare** for depth effect
- **Subtle text glow** for enhanced readability
- **Live visual effects preview** in Settings — true ticker-style sample showing all active effects, indicator style, sparkline position, and effect toggles
- **Stale data handling** — retains last valid price and progressively fades price, change text, and indicator instead of jumping to gold; gold reserved for initial N/A states only

### Settings & UX
- **Polished two-column grid layout** across API Keys, Appearance, and Visual Effects sections
- **Numeric-only input fields** with unit labels (sec, px, px/frame, %) on the right
- **Live apply** — most settings take effect immediately without restart
- **Modeless dialogs** — Settings, Manage Stocks, and About windows don't block the ticker
- **System tray integration** with right-click menu for quick access
- **Configurable transparency** (0–100%)
- **Sound on update** toggle

### Performance
- **Incremental pixmap rebuilds** — only changed symbols are re-rendered
- **Batched WebSocket visual refresh** with configurable interval
- **Sparkline fetch deduplication** and in-flight tracking
- **Icon caching with LRU eviction** to limit memory growth
- **Settings caching** to reduce repeated disk I/O during rendering
- **Progressive loading** for faster perceived startup
- Optional enhancements: pixmap memory pooling and JIT acceleration (Numba) when available

### Network
- **Proxy support** (HTTP/HTTPS)
- **Custom certificate** support (.pem)
- **Automatic session management** with retry/timeout handling
- **Data source failover** — graceful handling of API unavailability

---

## Requirements

**Python packages:**

| Package | Purpose |
|---|---|
| PyQt5 | Core GUI framework |
| requests | HTTP requests for API calls |
| websocket-client | Finnhub WebSocket streaming |
| numpy | Performance optimizations (optional) |
| pandas, pandas-market-calendars | Market hours detection |
| numba | Optional JIT compilation |
| pip-system-certs | System certificate trust |

**Standard library:** sys, os, json, time, datetime, webbrowser, ctypes, concurrent.futures, argparse, shutil, signal, atexit  
**Custom modules:** modern_gui_styles.py, ticker_utils_numba.py (optional), memory_pool.py (optional)

---

## Installation & Usage

1. **Clone or Download the Repository**

2. **Install Dependencies**

    ```powershell
    pip install -r requirements.txt
    ```

3. **Run the Application**

    ```powershell
    python TCKR.py
    ```

On first launch, enter your [Finnhub API key](https://finnhub.io/) in the Settings dialog. Use the **TEST** button to verify connectivity before saving.

---

## Building with PyInstaller

```powershell
python -m PyInstaller --noconfirm --clean --onefile --windowed --icon=TCKR.ico --name TCKR `
    --add-data "TCKR.ico;." `
    --add-data "SubwayTicker.ttf;." `
    --add-data "notify.wav;." `
    --hidden-import=PyQt5.QtMultimedia `
    --hidden-import=PyQt5.sip `
    --hidden-import=requests `
    --hidden-import=numpy `
    --hidden-import=psutil `
    --hidden-import=ticker_utils_numba `
    --hidden-import=memory_pool `
    --hidden-import=numba `
    --hidden-import="numba.cloudpickle.cloudpickle_fast" `
    --hidden-import="numba.cloudpickle.cloudpickle" `
    --hidden-import="numba.np.ufunc" `
    --hidden-import="llvmlite.binding" `
    TCKR.py
```

Then launch: `.\dist\TCKR.exe`

---

## Command-Line Options

```sh
-a, --api                   Finnhub API key
-b, --backup-settings       Restore settings from backup
-ht, --height               Ticker height in pixels
-n, --no-splash             Disable splash screen on startup
-s, --speed                 Ticker scroll speed
-t, --tickers               Comma-separated tickers (e.g. AAPL,MSFT,T)
-u, --update-interval       Update interval in seconds
```

**Example:**

```sh
TCKR.py -t BTC,ETH,MSFT,T -s 3 -ht 80 -u 120
```

---

## Settings Reference

All settings are managed via the Settings dialog and stored in `tckr_settings.json`:

| Setting | Description | Default |
|---|---|---|
| Primary Key | Finnhub API key for price data | — |
| Secondary Key | Optional second key for load balancing | — |
| Update Interval | REST API poll frequency | 300 sec |
| WS Visual Refresh | WebSocket display refresh rate (0 = smooth) | 0 sec |
| Display | Target monitor for ticker bar | Display 1 |
| Scroll Speed | Ticker scroll rate | 2 px/frame |
| Height | Ticker bar height | 60 px |
| Transparency | Window transparency | 100% |
| Price Indicator | Triangle / Arrow (thick/thin) style | Triangles |
| Sparklines | Enable 1D/5D historical trend charts | Off |
| Sparkline Range | 1D or 5D history window | 1D |
| Sparkline Position | Left or Right of price/change | Left |
| Second Ticker | Enable second independent ticker bar | Off |
| Bloom Effect | LED glow behind text/icons | On (60%) |
| Ghosting | Motion blur trailing effect | On (50%) |
| LED Matrix | Retro LED dot pattern overlay | On |
| Glass Cover | Glare/depth overlay | On |
| Text Glow | Subtle glow on text rendering | On |
| Sound | Play notification on price update | On |

---

## Data Sources

| Provider | Purpose |
|---|---|
| [Finnhub.io](https://finnhub.io) | Real-time stock quotes, WebSocket streaming |
| [Yahoo Finance](https://finance.yahoo.com) | Historical sparkline data (1D/5D) |
| [CoinGecko](https://coingecko.com) | Cryptocurrency prices |

---

## Screenshots

![TCKR Screenshot Windows 11.](https://github.com/krypdoh/TCKR/blob/main/docs/TCKR-screenshot4.png)

![TCKR Screenshot Windows 11.](https://github.com/krypdoh/TCKR/blob/main/docs/TCKR-screenshot3.png)

![TCKR Screenshot Windows 11.](https://github.com/krypdoh/TCKR/blob/main/docs/TCKR-screenshot1.png)

---

## License

This project is licensed under the [GNU Affero General Public License v3.0](https://www.gnu.org/licenses/agpl-3.0.html).

---

## Donations

If you find TCKR useful, consider [donating via PayPal](https://paypal.me/paypaulc).

---

*TCKR v1.0.2026.0212 — February 12, 2026*
