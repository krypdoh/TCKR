# TCKR - Stock & Crypto Ticker for Windows

**Author:** Paul R. Charovkine  
**License:** MIT

---

## Description

TCKR is a customizable, always-on-top ticker application for Windows that displays real-time stock and cryptocurrency prices.  
It features a modern, glassy UI with LED effects, multi-monitor support, and a system tray icon for quick access.  
The ticker fetches stock prices from Finnhub and crypto prices from CoinGecko, supports user configuration, and allows management of displayed tickers.  
Users can adjust appearance, scroll speed, transparency, and more via a settings dialog or command-line arguments.

---

## Key Features

- Real-time stock and crypto price display (Finnhub & CoinGecko APIs)
- Customizable appearance: height, transparency, glass effect, scroll speed
- Multi-monitor and system tray support
- Manage tickers (add, remove, edit) via GUI
- Command-line options for automation and scripting
- Clickable tickers open Yahoo Finance; donation link included
- Persistent settings and ticker list stored in user AppData

---

## Requirements

- Python 3.8+
- Modules:
  - `pillow`
  - `requests`
  - `screeninfo`
  - `pystray`
  - `tkinter` (standard with Python on Windows)

Install dependencies with:
pip install -r requirements.txt

---

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

On first launch, you will be prompted for your [Finnhub API key](https://finnhub.io/).  
(Optional: Enter a CoinGecko API key for crypto support via Settings or CLI if needed otherwise use the built-in key)

---

## Command-Line Options

You can customize TCKR at launch with these options:
```sh
--api APIKEY                  Finnhub API key 
--crypto-api APIKEY           CoinGecko API key 
--tickers, -t LIST            Comma-separated tickers (e.g. BTC,ETH,MSFT,T) 
--speed, -s INT               Ticker scroll speed 
--height, -ht INT             Ticker height in pixels 
--update-interval, -u INT     Update interval in seconds 
--crypto-first enable|disable Group crypto tickers first 
--change enable|disable       Show price change and percentage -h, 
--help                        Show help
```

**Example:**

```sh
python TCKR/TCKR.py -t BTC,ETH,MSFT,T -s 3 -ht 80 -u 120
```
---

## Settings & Customization

- Right-click the ticker to open the settings dialog.
- Manage tickers, adjust appearance, move to another screen, and more.
- Settings and ticker lists are saved in your user AppData folder.

---

## Screenshots

*(Add screenshots here if available)*

---

## License

This project is licensed under the MIT License.

---

## Donations

If you find TCKR useful, consider [donating via PayPal](https://paypal.me/paypaulc).

---
