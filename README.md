# TCKR - Stock & Crypto Ticker for Windows

**Author:** Paul R. Charovkine  
**License:** GNU AGPLv3

---

## Description

TCKR is a customizable, always-on-top ticker application for Windows that displays real-time* stock prices with visual alerts for significant price movements.  
It features a modern LED-style UI with glow effects for stocks with ≥5% changes, multi-monitor support, and a system tray icon for quick access.  
The ticker fetches stock prices from Finnhub, supports user configuration, and allows management of displayed tickers.  
Users can adjust appearance, scroll speed, transparency, display screen, update intervals, and more via a settings dialog or command-line arguments.

** Prices may be delayed depending on your Finnhub account. For educational and entertainment purposes only.
---

## Key Features

- Real-time stock and crypto price display (Finnhub & CoinGecko APIs)
- **Visual alerts**: Glowing effect for stocks with ≥5% price changes (lasts 5 minutes)
- Customizable appearance: height, transparency, glass effect, scroll speed
- Multi-monitor and system tray support
- Manage tickers (add, remove, edit) via GUI
- Command-line options for automation and scripting
- Clickable tickers open Yahoo Finance; donation link included
- Persistent settings and ticker list stored in user AppData
- Windows AppBar integration for proper screen space reservation

---

## Requirements

Currently Used:

✅ PyQt5 - Core GUI framework (imported at line 23-24)

✅ requests - HTTP requests for API calls (line 19)

✅ numpy - Used conditionally when USE_OPT=True for performance optimizations (lines 3594, 3690, 4097)

✅ pandas & pandas-market-calendars - Market hours detection (lines 461-462, function at line 456)

✅ numba - Optional JIT compilation via ticker_utils_numba.py module (loaded at line 609)

Also Used (not in requirements.txt):

Standard library: sys, os, json, time, datetime, webbrowser, ctypes, concurrent.futures, argparse, shutil, signal, atexit

Custom modules: modern_gui_styles.py, ticker_utils_numba.py (optional), memory_pool.py (optional)


## Installation & Usage

1. **Clone or Download the Repository**

2. **Install Dependencies**

    ```sh
    pip install -r requirements.txt
    ```

3. **Run the Application**

    ```sh
    python TCKR/TCKR.py
    ```

You will need to enter in your [Finnhub API key](https://finnhub.io/) in Settings if you have stock tickers in Manage Stocks.

---

## Command-Line Options

You can customize TCKR at launch with these options:
```sh
-a, --api                   Finnhub API key
-̶c̶, -̶-̶c̶r̶y̶p̶t̶o̶-̶a̶p̶i̶            C̶o̶i̶n̶G̶e̶c̶k̶o̶ A̶P̶I̶ k̶e̶y̶
-t, --tickers               Comma-separated tickers (e.g. AAPL,MSFT,T)
-s, --speed                 Ticker scroll speed
-ht, --height               Ticker height in pixels
-u, --update-interval       Update interval in seconds
-b, --backup-settings       Restore settings from backup and save as current
```

**Example:**

```sh
TCKR.py -t BTC,ETH,MSFT,T -s 3 -ht 80 -u 120
```
---

## Settings & Customization

- Right-click the ticker or use the system tray icon to access settings
- **Manage tickers**: Add or remove stocks/crypto symbols
- **Visual customization**: Adjust ticker height, transparency, scroll speed
- **Display options**: Choose which monitor to display on (multi-monitor support)
- **Update interval**: Configure how often prices are refreshed (default: 5 minutes)
- **Network settings**: Configure proxy and SSL certificate options if needed
- **Glow alerts**: Automatic visual highlighting for stocks with ≥5% price changes (5-minute duration)
- Settings and ticker lists are automatically saved in your user %AppData%/TCKR folder

---

## Screenshots

![TCKR Screenshot Windows 11.](https://github.com/krypdoh/TCKR/blob/main/docs/TCKR-screenshot4.png)

![TCKR Screenshot Windows 11.](https://github.com/krypdoh/TCKR/blob/main/docs/TCKR-screenshot3.png)

![TCKR Screenshot Windows 11.](https://github.com/krypdoh/TCKR/blob/main/docs/TCKR-screenshot1.png)

---

## License

This project is licensed under the GNU AGPLv3 License.

---

## Donations

If you find TCKR useful, consider [donating via PayPal](https://paypal.me/paypaulc).

---
