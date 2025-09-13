"""
Author: Paul R. Charovkine
Date: 2025.09.13
Program: TCKR.py

Description:
This program implements a customizable stock ticker application using Tkinter for Windows.
It displays real-time stock prices and logos in a scrolling ticker bar at the top of the screen.
Users can manage the list of stocks, adjust the ticker height, and update their Finnhub API key
through modern, user-friendly dialog boxes. The ticker integrates with the Windows AppBar for
persistent display and supports restarting or closing the ticker from the GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageFilter
import requests
from io import BytesIO
import ctypes
from ctypes import wintypes
import os
import sys
import json
import tkinter.font as tkFont
from screeninfo import get_monitors
import time
import threading
import math
import pystray
from PIL import Image as PILImage
import webbrowser
import argparse
import concurrent.futures
import tempfile
import subprocess
import sounddevice as sd
import soundfile as sf


def get_appdata_dir():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        appdata = os.path.expanduser("~")
    tckr_dir = os.path.join(appdata, "TCKR")
    if not os.path.exists(tckr_dir):
        os.makedirs(tckr_dir, exist_ok=True)
    return tckr_dir

APPDATA_DIR = get_appdata_dir()
SETTINGS_FILE = os.path.join(APPDATA_DIR, "TCKR.Settings.json")
STOCKS_FILE = os.path.join(APPDATA_DIR, "TCKR.Tickers.json")

def get_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                settings = json.load(f)
                if not settings.get("api_key"):
                    return None
                if "transparency" not in settings:
                    settings["transparency"] = 100
                if "show_change_pct" not in settings:
                    settings["show_change_pct"] = True
                if "speed" not in settings:
                    settings["speed"] = 2
                if "update_interval" not in settings:
                    settings["update_interval"] = 300000
                if "play_sound_on_update" not in settings:
                    settings["play_sound_on_update"] = True
                if "glass_opacity" not in settings:
                    settings["glass_opacity"] = 60
                if "glass_highlight_ratio" not in settings:
                    settings["glass_highlight_ratio"] = 0
                if "screen_index" not in settings:
                    settings["screen_index"] = 0
                if "coingecko_api_key" not in settings:
                    settings["coingecko_api_key"] = ""
                if "group_crypto_first" not in settings:
                    settings["group_crypto_first"] = False
                if "proxy" not in settings:
                    settings["proxy"] = ""
                if "cert_file" not in settings:
                    settings["cert_file"] = ""
                return settings
        except Exception:
            pass
    return {
        "transparency": 100,
        "show_change_pct": True,
        "speed": 2,
        "update_interval": 300000,
        "play_sound_on_update": True,
        "glass_opacity": 60,
        "glass_highlight_ratio": 0,
        "screen_index": 0,
        "coingecko_api_key": "",
        "group_crypto_first": False,
        "proxy": "",
        "cert_file": ""
    }

def set_settings(api_key=None, coingecko_api_key=None, height=None, transparency=None, show_change_pct=None, speed=None, update_interval=None, play_sound_on_update=None, glass_opacity=None, glass_highlight_ratio=None, screen_index=None, group_crypto_first=None, proxy=None, cert_file=None):
    settings = get_settings() or {}
    if api_key is not None:
        settings["api_key"] = api_key
    if coingecko_api_key is not None:
        settings["coingecko_api_key"] = coingecko_api_key
    if height is not None:
        settings["height"] = height
    if transparency is not None:
        settings["transparency"] = transparency
    if show_change_pct is not None:
        settings["show_change_pct"] = show_change_pct
    if speed is not None:
        settings["speed"] = speed
    if update_interval is not None:
        settings["update_interval"] = update_interval
    if play_sound_on_update is not None:
        settings["play_sound_on_update"] = play_sound_on_update
    if glass_opacity is not None:
        settings["glass_opacity"] = glass_opacity
    if glass_highlight_ratio is not None:
        settings["glass_highlight_ratio"] = glass_highlight_ratio
    if screen_index is not None:
        settings["screen_index"] = screen_index
    if group_crypto_first is not None:
        settings["group_crypto_first"] = group_crypto_first
    if proxy is not None:
        settings["proxy"] = proxy
    if cert_file is not None:
        settings["cert_file"] = cert_file
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
    except PermissionError as e:
        print(f"PermissionError: {e}")
        messagebox.showerror("Permission Error", f"Cannot write to {SETTINGS_FILE}.\nPlease close the file in other programs or check permissions.")

def should_disable_cert_check():
    proxy_setting = get_settings().get("proxy", "")
    return "check-certificate=off" in proxy_setting

def get_requests_proxies():
    proxy_url = get_settings().get("proxy", "")
    # Remove the special flag if present
    if "check-certificate=off" in proxy_url:
        proxy_url = proxy_url.replace("check-certificate=off", "").replace(";", "").replace(",", "").strip()
    if proxy_url:
        return {
            "http": proxy_url,
            "https": proxy_url
        }
    return None

def get_cert_file():
    cert_file = get_settings().get("cert_file", "")
    if should_disable_cert_check():
        return False
    if cert_file:
        return cert_file
    return True  # Use system default

def get_current_screen_geometry():
    settings = get_settings()
    monitors = get_monitors()
    screen_index = settings.get("screen_index", 0)
    if screen_index < 0 or screen_index >= len(monitors):
        screen_index = 0
    m = monitors[screen_index]
    return m.x, m.y, m.width, m.height

def prompt_for_api_key():
    prompt = tk.Tk()
    prompt.withdraw()
    dialog = tk.Toplevel(prompt)
    dialog.title("Enter Finnhub API Key")
    sx, sy, sw, sh = get_current_screen_geometry()
    dw, dh = 350, 120
    dx = sx + (sw - dw) // 2
    dy = sy + (sh - dh) // 2
    dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
    dialog.attributes("-topmost", True)
    ttk.Label(dialog, text="Finnhub API Key:").pack(pady=10)
    api_entry = ttk.Entry(dialog, show="*")
    api_entry.pack()
    api_entry.focus_set()
    result = {"api_key": None}
    def submit():
        key = api_entry.get().strip()
        if key:
            result["api_key"] = key
            set_settings(api_key=key)
            dialog.destroy()
            prompt.destroy()
        else:
            messagebox.showerror("Missing Key", "API key is required.")
    ttk.Button(dialog, text="Save", command=submit).pack(pady=10)
    api_entry.bind("<Return>", lambda e: submit())
    prompt.wait_window(dialog)
    return result["api_key"]

def fetch_logo(domain, logo_size):
    ticker = os.path.splitext(domain)[0].upper()
    images_dir = os.path.join(APPDATA_DIR, "TCKR.images")
    if not os.path.exists(images_dir):
        os.makedirs(images_dir, exist_ok=True)
    local_path = os.path.join(images_dir, f"{ticker}.png")
    if os.path.exists(local_path):
        try:
            return Image.open(local_path).convert("RGBA").resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        except Exception:
            pass

    # --- Crypto icon logic ---
    crypto_tickers = {
        "BTC", "ETH", "DOGE", "LTC", "ADA", "BNB", "XRP", "SOL", "DOT", "AVAX"
    }
    if ticker in crypto_tickers:
        # Use lowercase for the crypto icon URL
        crypto_url = f"https://raw.githubusercontent.com/krypdoh/cryptocurrency-icons/master/128/icon/{ticker.lower()}.png"
        try:
            response = requests.get(crypto_url, timeout=5, proxies=get_requests_proxies(), verify=get_cert_file())
            response.raise_for_status()
            img = Image.open(BytesIO(response.content)).convert("RGBA").resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            img.save(local_path)
            return img
        except Exception:
            # Fallback to blank if crypto icon fails
            return Image.new("RGBA", (logo_size, logo_size), (0, 0, 0, 0))

    # --- Stock icon logic (default) ---
    url = f"https://raw.githubusercontent.com/krypdoh/stock-icons/refs/heads/main/ticker_icons/{ticker}.png"
    try:
        response = requests.get(url, timeout=5, proxies=get_requests_proxies(), verify=get_cert_file())
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert("RGBA").resize((logo_size, logo_size), Image.Resampling.LANCZOS)
        img.save(local_path)
        return img
    except Exception:
        return Image.new("RGBA", (logo_size, logo_size), (0, 0, 0, 0))

crypto_price_cache = {}  # {ticker: (last_price, last_diff_price)}
fetch_failures = {}  # {ticker: {"fail_count": count, "last_good": (price, prev_close)}}

def fetch_finnhub_quote(ticker, api_key):
    url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={api_key}"
    try:
        print(f"[STOCK] Fetching: {url}")
        response = requests.get(url, timeout=10, proxies=get_requests_proxies(), verify=get_cert_file())
        print(f"[STOCK] Status: {response.status_code}")
        print(f"[STOCK] Response: {response.text}")
        response.raise_for_status()
        data = response.json()
        price = data.get("c")
        prev_close = data.get("pc")
        return ticker, (price, prev_close)
    except Exception as e:
        print(f"Error fetching {ticker} from Finnhub: {e}")
        return ticker, (None, None)

def fetch_all_stock_prices(tickers):
    global crypto_price_cache, fetch_failures
    prices = {}
    api_key = get_settings()["api_key"]
    coingecko_api_key = get_settings().get("coingecko_api_key", "").strip()
    default_cg_key = "CG-2f1b1c2e-1b1c-4e1b-8c2e-2f1b1c2e1b1c"
    cg_key_to_use = coingecko_api_key if coingecko_api_key else default_cg_key
    crypto_map = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "DOGE": "dogecoin",
        "LTC": "litecoin",
        "ADA": "cardano",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "SOL": "solana",
        "DOT": "polkadot",
        "AVAX": "avalanche-2",
        # Add more mappings as needed
    }
    crypto_tickers = []
    stock_tickers = []
    for ticker in tickers:
        symbol = ticker.split("-")[0]
        if symbol in crypto_map:
            crypto_tickers.append(ticker)
        else:
            stock_tickers.append(ticker)

    # Fetch stock prices in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_to_ticker = {
            executor.submit(fetch_finnhub_quote, ticker, api_key): ticker
            for ticker in stock_tickers
        }
        for future in concurrent.futures.as_completed(future_to_ticker):
            ticker, result = future.result()
            price, prev_close = result
            if price is not None and prev_close is not None:
                # Success: reset fail count and store last good
                fetch_failures[ticker] = {"fail_count": 0, "last_good": (price, prev_close)}
                prices[ticker] = (price, prev_close)
            else:
                # Failure: increment fail count, use last good if available
                entry = fetch_failures.get(ticker, {"fail_count": 0, "last_good": (None, None)})
                entry["fail_count"] += 1
                if entry["fail_count"] <= 3 and entry["last_good"][0] is not None:
                    prices[ticker] = entry["last_good"]
                else:
                    prices[ticker] = (None, None)
                fetch_failures[ticker] = entry

    # Fetch crypto prices from CoinGecko (with 24h change)
    if crypto_tickers:
        ids = []
        for ticker in crypto_tickers:
            symbol = ticker.split("-")[0]
            if symbol in crypto_map:
                ids.append(crypto_map[symbol])
        if ids:
            ids_str = ",".join(ids)
            url = (
                f"https://api.coingecko.com/api/v3/simple/price"
                f"?ids={ids_str}&vs_currencies=usd"
                f"&include_24hr_change=true&api_key={cg_key_to_use}"
            )
            print(f"[CRYPTO] Using CoinGecko API Key: {cg_key_to_use}")
            try:
                print(f"[CRYPTO] Fetching: {url}")
                response = requests.get(url, timeout=10, proxies=get_requests_proxies(), verify=get_cert_file())
                print(f"[CRYPTO] Status: {response.status_code}")
                print(f"[CRYPTO] Response: {response.text}")
                response.raise_for_status()
                data = response.json()
                for ticker in crypto_tickers:
                    symbol = ticker.split("-")[0]
                    cg_id = crypto_map.get(symbol)
                    if cg_id and cg_id in data:
                        price = data[cg_id].get("usd")
                        change_pct = data[cg_id].get("usd_24h_change")
                        if price is not None and change_pct is not None:
                            prev_price = price / (1 + change_pct / 100)
                            # Success: reset fail count and store last good
                            fetch_failures[ticker] = {"fail_count": 0, "last_good": (price, prev_price)}
                            prices[ticker] = (price, prev_price)
                        else:
                            # Failure: increment fail count, use last good if available
                            entry = fetch_failures.get(ticker, {"fail_count": 0, "last_good": (None, None)})
                            entry["fail_count"] += 1
                            if entry["fail_count"] <= 3 and entry["last_good"][0] is not None:
                                prices[ticker] = entry["last_good"]
                            else:
                                prices[ticker] = (None, None)
                            fetch_failures[ticker] = entry
                    else:
                        # Failure: increment fail count, use last good if available
                        entry = fetch_failures.get(ticker, {"fail_count": 0, "last_good": (None, None)})
                        entry["fail_count"] += 1
                        if entry["fail_count"] <= 3 and entry["last_good"][0] is not None:
                            prices[ticker] = entry["last_good"]
                        else:
                            prices[ticker] = (None, None)
                        fetch_failures[ticker] = entry
            except Exception as e:
                print(f"Error fetching crypto prices: {e}")
                for ticker in crypto_tickers:
                    # Failure: increment fail count, use last good if available
                    entry = fetch_failures.get(ticker, {"fail_count": 0, "last_good": (None, None)})
                    entry["fail_count"] += 1
                    if entry["fail_count"] <= 3 and entry["last_good"][0] is not None:
                        prices[ticker] = entry["last_good"]
                    else:
                        prices[ticker] = (None, None)
                    fetch_failures[ticker] = entry
    return prices

def load_stocks():
    default_stocks = [
        ["AAPL", "AAPL.png"],
        ["GOOG", "GOOG.png"],
        ["MSFT", "MSFT.png"]
    ]
    if not os.path.exists(STOCKS_FILE):
        try:
            with open(STOCKS_FILE, "w") as f:
                json.dump(default_stocks, f)
        except Exception as e:
            messagebox.showerror("Error", f"Could not create stocks file: {e}")
        return default_stocks
    try:
        with open(STOCKS_FILE, "r") as f:
            stocks = json.load(f)
            if not isinstance(stocks, list) or not stocks:
                with open(STOCKS_FILE, "w") as fw:
                    json.dump(default_stocks, fw)
                return default_stocks
            if all(isinstance(s, list) and len(s) == 2 for s in stocks):
                return stocks
    except Exception as e:
        print(f"Error loading stocks: {e}")
    try:
        with open(STOCKS_FILE, "w") as f:
            json.dump(default_stocks, f)
    except Exception as e:
        messagebox.showerror("Error", f"Could not write default stocks: {e}")
    return default_stocks

def save_stocks(stocks):
    try:
        with open(STOCKS_FILE, "w") as f:
            json.dump(stocks, f)
    except Exception as e:
        messagebox.showerror("Error", f"Could not save stocks: {e}")

def restart_program():
    python = sys.executable
    os.execl(python, python, *sys.argv)

def fetch_prices_now_from_tray(icon=None, item=None):
    def fetch_and_update():
        ticker.price_cache = fetch_all_stock_prices([ticker for ticker, _ in ticker.stocks])
        ticker.after(0, ticker.update_prices_in_place)
    threading.Thread(target=fetch_and_update, daemon=True).start()

ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003
ABE_TOP = 1

class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]

class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HANDLE),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge", wintypes.UINT),
        ("rc", RECT),
        ("lParam", wintypes.LPARAM),
    ]

def set_appbar(hwnd, height=100, x=0, y=0, width=None):
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    if width is None:
        width = user32.GetSystemMetrics(0)
    rc = RECT(x, y, x + width, y + height)
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    abd.uCallbackMessage = 0
    abd.uEdge = ABE_TOP
    abd.rc = rc
    shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
    shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
    shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
    user32.MoveWindow(hwnd, abd.rc.left, abd.rc.top, abd.rc.right - abd.rc.left, abd.rc.bottom - abd.rc.top, True)

def remove_appbar(hwnd):
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    ctypes.windll.shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))

def get_primary_monitor_width():
    monitors = get_monitors()
    if monitors:
        return monitors[0].width
    return 1920

class ScrollingTicker(tk.Canvas):
    def __init__(self, parent, stocks, height=100, bg="black", fg="white", speed=2):
        screen_width = get_primary_monitor_width()
        super().__init__(parent, bg=bg, height=height, width=screen_width, highlightthickness=0)
        self.fg = fg
        self.speed = speed
        self.stocks = stocks
        self.images = []
        self.items = []
        self.x = 0
        self.price_cache = {}
        self.ticker_height = height
        self.last_fetch_time = 0
        self.loading = True
        self._scroll_offset = 0
        self._scroll_accum = 0.0
        self.last_displayed = {}
        self.flashing = False
        self.first_update = True

        font_size = max(12, int(height * 0.32))
        available_fonts = tkFont.families()
        digital_font_name = "Subway Ticker"
        if digital_font_name in available_fonts:
            self.ticker_font = (digital_font_name, font_size, "bold")
        else:
            self.ticker_font = ("Arial", font_size, "bold")

        self.update_interval = get_settings().get("update_interval", 300000)

        self.create_ticker()  # Show loading message
        self.after(100, self.load_data_async)  # Will start scroll after data loads

        # Only bind our optimized configure handler
        self._last_size = (self.winfo_width(), self.ticker_height)
        self._last_configure_time = 0
        self._pending_configure = False
        self.bind("<Configure>", self._on_configure)
        self._pause_on_hover = False
        self._hover_timer = None
        self._mouse_inside = False
        self.bind("<Enter>", self._on_mouse_enter)
        self.bind("<Leave>", self._on_mouse_leave)

        # Cache variables
        self._led_bg_cache = None
        self._led_bg_cache_size = (0, 0)
        self._glass_overlay_cache = None
        self._glass_overlay_cache_size = (0, 0)

    def _on_configure(self, event=None):
        # Throttle expensive redraws to at most every 100ms
        now = time.time()
        if self._pending_configure:
            return
        if now - self._last_configure_time < 0.1:
            self._pending_configure = True
            self.after(100, self._on_configure)
            return
        self._pending_configure = False
        self._last_configure_time = now
        new_size = (self.winfo_width(), self.ticker_height)
        if new_size != self._last_size:
            self._last_size = new_size
            self.add_led_background()
            self.add_glassy_overlay()

    def _on_mouse_enter(self, event=None):
        self._mouse_inside = True
        if self._hover_timer is not None:
            self.after_cancel(self._hover_timer)
        self._hover_timer = self.after(500, self._pause_if_still_hovering)

    def _pause_if_still_hovering(self):
        if self._mouse_inside:
            self._pause_on_hover = True
            # Do not reschedule scroll here; let scroll() exit without rescheduling

    def _on_mouse_leave(self, event=None):
        self._mouse_inside = False
        if self._hover_timer is not None:
            self.after_cancel(self._hover_timer)
            self._hover_timer = None
        was_paused = self._pause_on_hover
        self._pause_on_hover = False
        if was_paused:
            # Reset scroll timer so it resumes smoothly
            self._last_scroll_time = time.perf_counter()
            self.after(16, self.scroll)

    def add_led_background(self, pixel_size=6, led_color=(30, 40, 60), off_color=(10, 12, 18)):
        width = self.winfo_width()
        height = self.ticker_height
        if width <= 1:
            width = get_primary_monitor_width()
        # Use cached image if size matches
        if self._led_bg_cache and self._led_bg_cache_size == (width, height):
            self.led_bg_img = self._led_bg_cache
        else:
            img = Image.new("RGB", (width, height), off_color)
            draw = ImageDraw.Draw(img)
            for y in range(0, height, pixel_size):
                ratio = y / max(1, height - 1)
                grad_color = tuple(
                    int(off_color[i] + (led_color[i] - off_color[i]) * ratio)
                    for i in range(3)
                )
                for x in range(0, width, pixel_size):
                    draw.rectangle(
                        [x, y, x + pixel_size - 2, y + pixel_size - 2],
                        fill=grad_color
                    )
            self.led_bg_img = ImageTk.PhotoImage(img)
            self._led_bg_cache = self.led_bg_img
            self._led_bg_cache_size = (width, height)
        self.delete("led_bg")
        self.create_image(0, 0, image=self.led_bg_img, anchor="nw", tags="led_bg")
        self.tag_lower("led_bg")

    def create_glow_text_image(self, text, font_tuple, glow_color, blur_radius=8, offset=(0,0)):
        font_name, font_size = font_tuple[0], font_tuple[1]
        try:
            font = ImageFont.truetype(font_name, font_size)
        except Exception:
            font = ImageFont.load_default()
        dummy_img = Image.new("RGBA", (1,1))
        draw = ImageDraw.Draw(dummy_img)
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = (bbox[2] - bbox[0]) + 24, (bbox[3] - bbox[1]) + 24
        img = Image.new("RGBA", (w, h), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        draw.text((12+offset[0],12+offset[1]), text, font=font, fill=glow_color)
        blurred = img.filter(ImageFilter.GaussianBlur(blur_radius))
        return ImageTk.PhotoImage(blurred), (w, h)

    def load_data_async(self):
        start_time = time.time()
        def fetch_and_update():
            self.price_cache = fetch_all_stock_prices([ticker for ticker, _ in self.stocks])
            elapsed = time.time() - start_time
            min_loading = 1.0
            remaining = max(0, min_loading - elapsed)
            if remaining > 0:
                time.sleep(remaining)
            self.loading = False
            self.after(0, self.create_ticker)
            self.after(0, self.scroll)  # Start scroll loop after ticker is ready
            self.after(self.update_interval, self.refresh_prices)
            self.after(0, self.update_prices_in_place)
        threading.Thread(target=fetch_and_update, daemon=True).start()

    def get_prices(self):
        return self.price_cache

    def create_ticker(self):
        try:
            # --- DEBUG PRINTS START ---
            print("create_ticker called, loading:", self.loading)
            print("stocks:", self.stocks)
            print("price_cache:", self.price_cache)
            # --- DEBUG PRINTS END ---
            self.delete("all")
            self.items.clear()
            self.images = []
            y_center = self.ticker_height // 2
            canvas_width = self.winfo_width()
            print("canvas_width:", canvas_width)  # DEBUG
            if canvas_width <= 1:
                canvas_width = get_primary_monitor_width()
            if self.loading:
                self.create_text(
                    canvas_width // 2, y_center,
                    text="TCKR: LOADING", fill="#FFD700", font=self.ticker_font, anchor="c"
                )
                self.ticker_length = canvas_width
                self.cycle_items = []
                return

            self.add_led_background()

            # --- Group Crypto First logic ---
            settings = get_settings()
            crypto_map = {
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "DOGE": "dogecoin",
                "LTC": "litecoin",
                "ADA": "cardano",
                "BNB": "binancecoin",
                "XRP": "ripple",
                "SOL": "solana",
                "DOT": "polkadot",
                "AVAX": "avalanche-2",
            }
            def is_crypto(ticker):
                symbol = ticker.split("-")[0]
                return symbol in crypto_map

            if settings.get("group_crypto_first", False):
                crypto_stocks = [s for s in self.stocks if is_crypto(s[0])]
                stock_stocks = [s for s in self.stocks if not is_crypto(s[0])]
                sorted_stocks = sorted(crypto_stocks, key=lambda s: s[0]) + sorted(stock_stocks, key=lambda s: s[0])
            else:
                sorted_stocks = sorted(self.stocks, key=lambda s: s[0])
            # --- End Group Crypto First logic ---

            prices = self.get_prices()
            logo_size = max(24, int(self.ticker_height * 0.6))
            font_size = max(12, int(self.ticker_height * 0.32))
            small_font_size = max(8, int(font_size * 0.55))
            padding = max(30, int(self.ticker_height * 1.0))
            logo_text_gap = max(5, int(self.ticker_height * 0.10))
            price_gap = max(10, int(self.ticker_height * 0.30))
            ticker_font = self.ticker_font
            small_font = (ticker_font[0], small_font_size, "bold")
            vertical_gap = 6
            show_change_pct = get_settings().get("show_change_pct", True)

            def draw_cycle(x_offset):
                x = x_offset
                cycle_ids = []
                for ticker, domain in sorted_stocks:
                    img = fetch_logo(domain, logo_size)
                    tk_img = ImageTk.PhotoImage(img)
                    self.images.append(tk_img)
                    img_id = self.create_image(x + logo_size // 2, y_center, image=tk_img)
                    price, prev_close = prices.get(ticker, (None, None))
                    if price is not None and prev_close is not None:
                        price_str = f"{price:.2f}"
                        change = price - prev_close
                        pct_change = (change / prev_close * 100) if prev_close else 0
                        if change > 0:
                            color = "#00FF40"
                            arrow = "▲"
                            sign = "+"
                        elif change < 0:
                            color = "red"
                            arrow = "▼"
                            sign = ""
                        else:
                            color = "white"
                            arrow = ""
                            sign = ""
                        change_str = f"{sign}{change:.2f}{arrow}"
                        pct_str = f"{sign}{pct_change:.2f}%"
                    else:
                        price_str = "   N/A   "
                        change_str = "      "
                        pct_str = "      "
                        color = "white"
                    text_x = x + logo_size + logo_text_gap
                    tag = f"ticker_{ticker}"

                    glow_img, (gw, gh) = self.create_glow_text_image(ticker, ticker_font, "#00B3FF", blur_radius=8)
                    self.images.append(glow_img)
                    glow_offset_x = text_x - 12
                    glow_offset_y = y_center - (gh // 2) + (self.bbox(self.create_text(0,0,text=ticker,font=ticker_font))[3] // 2)
                    glow_id = self.create_image(glow_offset_x, glow_offset_y, image=glow_img, anchor="nw")
                    text_id = self.create_text(
                        text_x, y_center, text=ticker, fill="#00B3FF", font=ticker_font, anchor="w", tags=(tag,)
                    )
                    cycle_ids.extend([img_id, glow_id, text_id])
                    def make_callback(tkr):
                        return lambda event: webbrowser.open(f"https://finance.yahoo.com/quote/{tkr}/")
                    self.tag_bind(tag, "<Button-1>", make_callback(ticker))
                    self.tag_bind(tag, "<Enter>", lambda e: self.config(cursor="hand2"))
                    self.tag_bind(tag, "<Leave>", lambda e: self.config(cursor=""))

                    text_bbox = self.bbox(text_id)
                    price_x = text_bbox[2] + price_gap;

                    # --- Use unique tags for price and shadow ---
                    price_tag = f"price_{ticker}"
                    price_shadow_tag = f"price_shadow_{ticker}"
                    price_shadow_id = self.create_text(
                        price_x+1, y_center+1, text=price_str, fill="black", font=ticker_font, anchor="w", tags=(price_shadow_tag,)
                    )
                    price_id = self.create_text(
                        price_x, y_center, text=price_str, fill=color, font=ticker_font, anchor="w", tags=(price_tag,)
                    )
                    self.tag_raise(price_id, price_shadow_id)
                    cycle_ids.extend([price_shadow_id, price_id])
                    def make_price_callback(tkr):
                        return lambda event: webbrowser.open(f"https://finance.yahoo.com/quote/{tkr}/")
                    self.tag_bind(price_tag, "<Button-1>", make_price_callback(ticker))
                    self.tag_bind(price_tag, "<Enter>", lambda e: self.config(cursor="hand2"))
                    self.tag_bind(price_tag, "<Leave>", lambda e: self.config(cursor=""))

                    price_bbox = self.bbox(price_id)

                    if show_change_pct:
                        change_x = price_bbox[2] + 6
                        change_y = y_center - small_font_size // 2 - vertical_gap // 2
                        pct_y = y_center + small_font_size // 2 + vertical_gap // 2 + 4  # Add vertical space here

                        change_tag = f"change_{ticker}"
                        change_shadow_tag = f"change_shadow_{ticker}"
                        change_shadow_id = self.create_text(
                            change_x+1, change_y+1, text=change_str, fill="black", font=small_font, anchor="w", tags=(change_shadow_tag,)
                        )
                        change_id = self.create_text(
                            change_x, change_y, text=change_str, fill=color, font=small_font, anchor="w", tags=(change_tag,)
                        )
                        self.tag_raise(change_id, change_shadow_id)

                        # Align percent directly under change (same x)
                        pct_x = change_x

                        pct_tag = f"pct_{ticker}"
                        pct_shadow_tag = f"pct_shadow_{ticker}"
                        pct_shadow_id = self.create_text(
                            pct_x+1, pct_y+1, text=pct_str, fill="black", font=small_font, anchor="w", tags=(pct_shadow_tag,)
                        )
                        pct_id = self.create_text(
                            pct_x, pct_y, text=pct_str, fill=color, font=small_font, anchor="w", tags=(pct_tag,)
                        )
                        self.tag_raise(pct_id, pct_shadow_id)
                        cycle_ids.extend([change_shadow_id, change_id, pct_shadow_id, pct_id])
                        change_bbox = self.bbox(change_id)
                        pct_bbox = self.bbox(pct_id)
                        rightmost = max(change_bbox[2], pct_bbox[2])

                        # Cursor for change and pct
                        self.tag_bind(change_tag, "<Enter>", lambda e: self.config(cursor="hand2"))
                        self.tag_bind(change_tag, "<Leave>", lambda e: self.config(cursor=""))
                        self.tag_bind(pct_tag, "<Enter>", lambda e: self.config(cursor="hand2"))
                        self.tag_bind(pct_tag, "<Leave>", lambda e: self.config(cursor=""))
                    else:
                        rightmost = price_bbox[2]
                    x = rightmost + padding if show_change_pct else price_bbox[2] + padding

                donate_text = "      Please Donate!          "
                rainbow_colors = [
                    "#FF0000", "#FF7F00", "#FFFF00", "#00FF00", "#00B3FF", "#4B0082", "#9400D3"
                ]
                colors = [rainbow_colors[i % len(rainbow_colors)] for i in range(len(donate_text))]
                donate_font = ticker_font
                donate_x = x + 20
                donate_y = y_center
                donate_tag = "donate_text"
                for i, char in enumerate(donate_text):
                    color = colors[i]
                    shadow_id = self.create_text(
                        donate_x+1, donate_y+1, text=char, fill="black", font=donate_font, anchor="w"
                    )
                    char_id = self.create_text(
                        donate_x, donate_y, text=char, fill=color, font=donate_font, anchor="w", tags=(donate_tag,)
                    )
                    self.tag_raise(char_id, shadow_id)
                    char_bbox = self.bbox(char_id)
                    donate_x = char_bbox[2] + 1
                    cycle_ids.extend([shadow_id, char_id])
                x = donate_x + 30

                # Bind click and cursor events for the donate text
                def open_paypal(event=None):
                    webbrowser.open("https://paypal.me/paypaulc")
                self.tag_bind(donate_tag, "<Button-1>", lambda e: open_paypal())
                self.tag_bind(donate_tag, "<Enter>", lambda e: self.config(cursor="hand2"))
                self.tag_bind(donate_tag, "<Leave>", lambda e: self.config(cursor=""))

                return x - x_offset, cycle_ids

            self.images.clear()
            self.cycle_items = []
            num_cycles = 2  # Temporary, will be recalculated after first cycle

            # Draw the first cycle just off the right edge
            cycle_length, cycle_ids = draw_cycle(canvas_width)
            self.ticker_length = cycle_length
            self.cycle_items.append({"ids": cycle_ids, "x": canvas_width})

            # Now calculate the correct number of cycles
            num_cycles = max(2, math.ceil(canvas_width / self.ticker_length) + 2)
            for i in range(1, num_cycles):
                start_x = canvas_width + i * self.ticker_length
                _, ids = draw_cycle(start_x)
                self.cycle_items.append({"ids": ids, "x": start_x})

            self.add_glassy_overlay()
            for item in self.find_all():
                if self.type(item) in ("text", "image"):
                    self.tag_raise(item)
        except Exception as e:
            print("Exception in create_ticker:", e)
            import traceback
            traceback.print_exc()

    def refresh_prices(self):
        def fetch_and_update():
            try:
                old_prices = self.price_cache.copy()
                self.price_cache = fetch_all_stock_prices([ticker for ticker, _ in self.stocks])
                # Only call create_ticker if the set of stocks changed (not for price updates)
                if self._should_recreate_ticker(old_prices, self.price_cache):
                    self.after(0, self.create_ticker)
                self.after(0, self.update_prices_in_place)
            except Exception as e:
                print("Exception in fetch_and_update:", e)
                import traceback
                traceback.print_exc()
        threading.Thread(target=fetch_and_update, daemon=True).start()
        self.after(self.update_interval, self.refresh_prices)

    def _should_recreate_ticker(self, old_prices, new_prices):
        # Only recreate if the set of tickers or their None/valid status changes
        if set(old_prices.keys()) != set(new_prices.keys()):
            return True
        for k in old_prices:
            if (old_prices[k][0] is None) != (new_prices[k][0] is None):
                return True
        return False

    def scroll(self):
        try:
            if self.loading or not self.cycle_items or self._pause_on_hover:
                # Do not reschedule scroll if paused
                return

            now = time.perf_counter()
            if not hasattr(self, '_last_scroll_time'):
                self._last_scroll_time = now
            elapsed = now - self._last_scroll_time
            self._last_scroll_time = now

            pixels_per_sec = max(1, float(self.speed)) * 60
            self._scroll_accum += pixels_per_sec * elapsed
            move_pixels = int(self._scroll_accum)
            self._scroll_accum -= move_pixels

            if move_pixels > 0:
                for cycle in self.cycle_items:
                    for item_id in cycle["ids"]:
                        self.move(item_id, -move_pixels, 0)
                    cycle["x"] -= move_pixels

                rightmost_x = max(cycle["x"] for cycle in self.cycle_items)
                for cycle in self.cycle_items:
                    if cycle["x"] + self.ticker_length <= 0:
                        new_x = rightmost_x + self.ticker_length
                        dx = new_x - cycle["x"]
                        for item_id in cycle["ids"]:
                            self.move(item_id, dx, 0)
                        cycle["x"] = new_x
                        rightmost_x = new_x

            self.after(16, self.scroll)
        except Exception as e:
            print(f"Error in scroll: {e}")

    def set_height(self, new_height):
        screen_width = get_primary_monitor_width()
        self.config(height=new_height, width=screen_width)
        self.ticker_height = new_height
        self.create_ticker()
        self.add_glassy_overlay()

    def set_speed(self, new_speed):
        self.speed = new_speed

    def set_update_interval(self, new_interval):
        self.update_interval = new_interval

    def flash_item(self, item_id, final_color, flash_color="#FFD700", duration=100):
        # Always set to the correct color before flashing
        self.itemconfig(item_id, fill=final_color)
        self.tag_raise(item_id)
        self.after(10, lambda: self._do_flash(item_id, final_color, flash_color, duration))

    def _do_flash(self, item_id, final_color, flash_color, duration):
        self.itemconfig(item_id, fill=flash_color)
        self.after(duration, lambda: self.itemconfig(item_id, fill=final_color))

    def update_prices_in_place(self):
        print("update_prices_in_place called")
        try:
            if hasattr(self, "flashing") and self.flashing:
                return

            prices = self.get_prices()
            show_change_pct = get_settings().get("show_change_pct", True)
            flash_items = []
            price_changed = False

            for ticker, domain in sorted(self.stocks, key=lambda s: s[0]):
                price, prev_close = prices.get(ticker, (None, None))
                if price is not None and prev_close is not None:
                    price_str = f"{price:.2f}"
                    change = price - prev_close
                    pct_change = (change / prev_close * 100) if prev_close else 0
                    if change > 0:
                        color = "#00FF40"
                        arrow = "▲"
                        sign = "+"
                    elif change < 0:
                        color = "red"
                        arrow = "▼"
                        sign = ""
                    else:
                        color = "white"
                        arrow = ""
                        sign = ""
                    change_str = f"{sign}{change:.2f}{arrow}"
                    pct_str = f"{sign}{pct_change:.2f}%"
                else:
                    price_str = "   N/A   "
                    change_str = "      "
                    pct_str = "      "
                    color = "white"

                # Compare with last displayed price
                last_price_str, last_change_str, last_pct_str = self.last_displayed.get(ticker, (None, None, None))

                # Only update if any value changed
                if (
                    last_price_str is not None
                    and price_str == last_price_str
                    and change_str == last_change_str
                    and pct_str == last_pct_str
                ):
                    continue

                price_changed = True
                self.last_displayed[ticker] = (price_str, change_str, pct_str)

                # Update price
                price_items = self.find_withtag(f"price_{ticker}")
                price_shadow_items = self.find_withtag(f"price_shadow_{ticker}")
                for price_item, price_shadow_item in zip(price_items, price_shadow_items):
                    self.itemconfig(price_item, text=price_str, fill=color)
                    self.itemconfig(price_shadow_item, text=price_str, fill="black")
                    flash_items.append((price_item, color))
                    self.tag_raise(price_item, price_shadow_item)

                # Update change and percentage
                if show_change_pct:
                    change_items = self.find_withtag(f"change_{ticker}")
                    change_shadow_items = self.find_withtag(f"change_shadow_{ticker}")
                    for change_item, change_shadow_item in zip(change_items, change_shadow_items):
                        self.itemconfig(change_item, text=change_str, fill=color)
                        self.itemconfig(change_shadow_item, text=change_str, fill="black")
                        flash_items.append((change_item, color))
                        self.tag_raise(change_item, change_shadow_item)

                    pct_items = self.find_withtag(f"pct_{ticker}")
                    pct_shadow_items = self.find_withtag(f"pct_shadow_{ticker}")
                    for pct_item, pct_shadow_item in zip(pct_items, pct_shadow_items):
                        self.itemconfig(pct_item, text=pct_str, fill=color)
                        self.itemconfig(pct_shadow_item, text=pct_str, fill="black")
                        flash_items.append((pct_item, color))
                        self.tag_raise(pct_item, pct_shadow_item)

            if self.first_update:
                self.first_update = False
                self.flashing = False
                return

            if get_settings().get("play_sound_on_update", True) and price_changed:
                # Only play sound if any price changed
                sound_files = [
                    "Windows Notify.wav",
                    "Windows Exclamation.wav",
                    "Windows Ding.wav",
                    "chimes.wav",
                    "tada.wav"
                ]
                media_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Media")
                sound_path = None
                for fname in sound_files:
                    candidate = os.path.join(media_dir, fname)
                    if os.path.exists(candidate):
                        sound_path = candidate
                        break

                def play_notify_sound():
                    try:
                        if sound_path and os.path.exists(sound_path):
                            data, fs = sf.read(sound_path, dtype='float32')
                            sd.play(data, fs)
                        else:
                            print("No valid sound file found.")
                    except Exception as e:
                        print("Sound error:", e)

                threading.Thread(target=play_notify_sound, daemon=True).start()

            # Only flash if any price changed
            if price_changed:
                self.flashing = True
                sequential_flash_delay = 120  # ms between flashes

                def flash_next(index=0):
                    if index < len(flash_items):
                        item_id, final_color = flash_items[index]
                        self.flash_item(item_id, final_color, flash_color="#FFD700", duration=500)
                        self.after(sequential_flash_delay, lambda: flash_next(index + 1))
                    else:
                        self.flashing = False  # Done flashing, allow next sequence

                flash_next()
            else:
                self.flashing = False  # No change, no flash

        except Exception as e:
            print("EXCEPTION in update_prices_in_place:", e)
            import traceback
            traceback.print_exc()

    def animate_price_flash(self, item_id, target_color):
        self.itemconfig(item_id, fill="#FFD700")
        self.after(100, lambda: self.itemconfig(item_id, fill=target_color))
        self.after(400, lambda: self.itemconfig(item_id, fill="#FFD700"))
        self.after(600, lambda: self.itemconfig(item_id, fill=target_color))

    def add_glassy_overlay(self):
        opacity = get_settings().get("glass_opacity", 60)
        highlight_ratio = get_settings().get("glass_highlight_ratio", 0.18)
        width = self.winfo_width()
        height = self.ticker_height
        if width <= 1:
            width = get_primary_monitor_width()
        # Use cached image if size matches
        if self._glass_overlay_cache and self._glass_overlay_cache_size == (width, height):
            self.glass_overlay = self._glass_overlay_cache
        else:
            base_color = (220, 235, 255)
            overlay_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            for y in range(height):
                glass_alpha = int(opacity * (1 - (y / height) ** 1.5))
                for x in range(width):
                    overlay_img.putpixel((x, y), base_color + (glass_alpha,))
            highlight_height = int(height * highlight_ratio)
            for y in range(highlight_height):
                curve = 1 - ((y / highlight_height) - 0.5) ** 2 * 4
                curve = max(0, curve)
                highlight_alpha = int(180 * curve)
                for x in range(width):
                    base = overlay_img.getpixel((x, y))
                    new_alpha = max(base[3], highlight_alpha)
                    highlight_color = (
                        int(base_color[0] + (255 - base_color[0]) * 0.5),
                        int(base_color[1] + (255 - base_color[1]) * 0.5),
                        int(base_color[2] + (255 - base_color[2]) * 0.5),
                        new_alpha
                    )
                    overlay_img.putpixel((x, y), highlight_color)
            border_alpha = 90
            for x in range(width):
                overlay_img.putpixel((x, 0), (255, 255, 255, border_alpha))
                overlay_img.putpixel((x, height - 1), (0, 0, 0, border_alpha))
            self.glass_overlay = ImageTk.PhotoImage(overlay_img)
            self._glass_overlay_cache = self.glass_overlay
            self._glass_overlay_cache_size = (width, height)
        self.delete("glass_overlay")
        self.create_image(0, 0, image=self.glass_overlay, anchor="nw", tags="glass_overlay", state="disabled")
        self.tag_lower("glass_overlay")  # Ensure overlay is always below text

def move_ticker_to_screen(screen_index=0):
    monitors = get_monitors()
    if not monitors:
        messagebox.showerror("Screen Error", "No monitors detected.")
        return
    if screen_index < 0 or screen_index >= len(monitors):
        messagebox.showerror("Screen Error", f"Screen {screen_index+1} not found.")
        return
    m = monitors[screen_index]
    root.geometry(f"{m.width}x{ticker.ticker_height}+{m.x}+{m.y}")
    root.update_idletasks()
    set_appbar(int(root.winfo_id()), height=ticker.ticker_height, x=m.x, y=m.y, width=m.width)
    root.update()
    root.focus_force()
    set_settings(screen_index=screen_index)

def show_screen_select_dialog():
    monitors = get_monitors()
    dialog = tk.Toplevel(root)
    dialog.title("Select Display Screen")
    sx, sy, sw, sh = get_current_screen_geometry()
    dw, dh = 320, 180
    dx = sx + (sw - dw) // 2
    dy = sy + (sh - dh) // 2
    dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
    dialog.attributes("-topmost", True)
    ttk.Label(dialog, text="Move ticker to which screen?", font=("Segoe UI", 11, "bold")).pack(pady=12)
    for idx, m in enumerate(monitors):
        desc = f"Screen {idx+1}: {m.width}x{m.height} @ ({m.x},{m.y})"
        def move_and_close(i=idx):
            move_ticker_to_screen(i)
            dialog.destroy()
        ttk.Button(dialog, text=desc, command=move_and_close).pack(pady=6, fill="x")
    ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack(pady=6, fill="x")

def set_ticker_transparency(alpha_percent):
    alpha = max(0, min(100, int(alpha_percent))) / 100.0
    root.attributes("-alpha", alpha)

tray_icon_instance = None
settings_dialog_instance = None
manage_stocks_dialog_instance = None

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
        # Fallback: if not found, try the script's directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(base_path, relative_path)
        if not os.path.exists(candidate):
            candidate = os.path.join(script_dir, relative_path)
        return candidate
    return os.path.join(base_path, relative_path)

def create_tray_icon():
    global tray_icon_instance
    icon_path = resource_path("TCKR.ico")
    if not os.path.exists(icon_path):
        print(f"Tray icon file not found: {icon_path}")
        from tkinter import messagebox
        messagebox.showwarning(
            "Tray Icon Missing",
            f"Tray icon file not found:\n{icon_path}\n\n"
            "Please ensure TCKR.ico is present in the application folder."
        )
        return

    image = PILImage.open(icon_path)

    def on_settings(icon, item):
        root.after(0, show_settings_dialog)

    def on_exit(icon, item):
        icon.stop()
        root.after(0, on_close)

    def on_about(icon, item):
        root.after(0, show_about_dialog)

    menu = pystray.Menu(
        pystray.MenuItem("Fetch Stock Prices", fetch_prices_now_from_tray),
        pystray.MenuItem("Settings...", on_settings),
        pystray.MenuItem("About...", on_about),
        pystray.MenuItem("Exit", on_exit)
    )
    tray_icon_instance = pystray.Icon("pcticker", image, "TCKR", menu)
    tray_icon_instance.run()

def start_tray_icon():
    t = threading.Thread(target=create_tray_icon, daemon=True)
    t.start()

def show_manage_stocks_dialog():
    global ticker, manage_stocks_dialog_instance
    if manage_stocks_dialog_instance is not None and manage_stocks_dialog_instance.winfo_exists():
        manage_stocks_dialog_instance.lift()
        manage_stocks_dialog_instance.focus_force()
        return

    stocks = load_stocks()
    dialog = tk.Toplevel(root)
    manage_stocks_dialog_instance = dialog  # Track the instance
    dialog.title("Manage Stocks")
    sx, sy, sw, sh = get_current_screen_geometry()
    dw, dh = 400, 600
    dx = sx + (sw - dw) // 2
    dy = sy + (sh - dh) // 2
    dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
    dialog.transient(root)
    dialog.lift()
    dialog.focus_force()
    dialog.attributes("-topmost", True)
    dialog.resizable(False, False)
    dialog.update_idletasks()
    icon_path = resource_path("TCKR.ico")
    if os.path.exists(icon_path):
        try:
            dialog.iconbitmap(icon_path)
        except Exception as e:
            print(f"Warning: Could not set dialog icon: {e}")
    default_font = ("Segoe UI", 10)

    ttk.Label(dialog, text="Manage Stocks", font=("Segoe UI", 14, "bold")).pack(pady=(12, 6))

    list_frame = ttk.Frame(dialog)
    list_frame.pack(fill="x", padx=20, pady=6)

    listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, width=40, height=12, font=default_font)
    for tkr, img in stocks:
        listbox.insert(tk.END, f"{tkr} | {img}")
    listbox.pack(pady=6)

    add_frame = ttk.Frame(dialog)
    add_frame.pack(fill="x", padx=20, pady=6)

    ttk.Label(add_frame, text="Ticker:", font=default_font).grid(row=0, column=0, sticky="w", pady=4)
    ticker_entry = ttk.Entry(add_frame, width=10, font=default_font)
    ticker_entry.grid(row=0, column=1, sticky="w", pady=4)

    sep = ttk.Separator(dialog, orient="horizontal")
    sep.pack(fill="x", padx=10, pady=10)

    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(fill="x", padx=20, pady=6)

    def add_stock():
        tkr = ticker_entry.get().strip().upper()
        if tkr:
            img = f"{tkr}.png"
            stocks.append([tkr, img])
            listbox.insert(tk.END, f"{tkr} | {img}")
            ticker_entry.delete(0, tk.END)
            save_stocks(stocks)
        else:
            messagebox.showerror("Input Error", "Ticker is required.")

    def remove_selected():
        selected = list(listbox.curselection())
        if not selected:
            return
        for idx in reversed(selected):
            del stocks[idx]
            listbox.delete(idx)
        save_stocks(stocks)

    def edit_selected():
        selected = listbox.curselection()
        if len(selected) != 1:
            messagebox.showerror("Edit Error", "Please select a single stock to edit.")
            return
        idx = selected[0]
        old_tkr, _ = stocks[idx]

        edit_dialog = tk.Toplevel(dialog)
        edit_dialog.title("Edit Stock")
        sx, sy, sw, sh = get_current_screen_geometry()
        dw, dh = 300, 100
        dx = sx + (sw - dw) // 2
        dy = sy + (sh - dh) // 2
        edit_dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
        edit_dialog.attributes("-topmost", True)
        style = ttk.Style(edit_dialog)
        style.theme_use('vista')

        ttk.Label(edit_dialog, text="Ticker:", font=default_font).grid(row=0, column=0, padx=5, pady=5)
        ticker_entry2 = ttk.Entry(edit_dialog, font=default_font)
        ticker_entry2.grid(row=0, column=1, padx=5, pady=5)
        ticker_entry2.insert(0, old_tkr)

        def save_edit():
            new_tkr = ticker_entry2.get().strip().upper()
            if new_tkr:
                new_img = f"{new_tkr}.png"
                stocks[idx] = [new_tkr, new_img]
                listbox.delete(idx)
                listbox.insert(idx, f"{new_tkr} | {new_img}")
                save_stocks(stocks)
                edit_dialog.destroy()
            else:
                messagebox.showerror("Input Error", "Ticker is required.")

        ttk.Button(edit_dialog, text="Save", command=save_edit).grid(row=1, column=0, columnspan=2, pady=10)

    def save_and_close():
        save_stocks(stocks)
        dialog.destroy()
        ticker.stocks = load_stocks()
        ticker.create_ticker()

    ttk.Button(btn_frame, text="Add", command=add_stock).pack(pady=4, fill="x")
    ttk.Button(btn_frame, text="Remove Selected", command=remove_selected).pack(pady=4, fill="x")
    ttk.Button(btn_frame, text="Edit Selected", command=edit_selected).pack(pady=4, fill="x")
    ttk.Button(btn_frame, text="Save & Close", command=save_and_close).pack(pady=4, fill="x")
    ttk.Button(btn_frame, text="Restart Ticker", command=lambda: (dialog.destroy(), restart_program())).pack(pady=4, fill="x")
    ttk.Button(btn_frame, text="Close Ticker", command=lambda: (dialog.destroy(), on_close())).pack(pady=4, fill="x")

    def on_close_dialog():
        global manage_stocks_dialog_instance
        manage_stocks_dialog_instance = None
        dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", on_close_dialog)

def show_settings_dialog():
    global settings_dialog_instance
    if settings_dialog_instance is not None and settings_dialog_instance.winfo_exists():
        settings_dialog_instance.lift()
        settings_dialog_instance.focus_force()
        return

    dialog = tk.Toplevel(root)
    settings_dialog_instance = dialog  # <-- Track the instance here
    dialog.title("TCKR Settings")
    sx, sy, sw, sh = get_current_screen_geometry()
    dw, dh = 500, 820
    dx = sx + (sw - dw) // 2
    dy = sy + (sh - dh) // 2
    dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
    dialog.transient(root)
    dialog.lift()
    dialog.focus_force()
    dialog.attributes("-topmost", True)
    dialog.resizable(False, False)
    dialog.update_idletasks()  # Ensure window is created before setting icon
    icon_path = resource_path("TCKR.ico")
    if os.path.exists(icon_path):
        try:
            dialog.iconbitmap(icon_path)
        except Exception as e:
            print(f"Warning: Could not set dialog icon: {e}")
    default_font = ("Segoe UI", 10)

    ttk.Label(dialog, text="TCKR Settings", font=("Segoe UI", 14, "bold")).pack(pady=(12, 6))

    # Add a canvas with a vertical scrollbar for the settings frame
    canvas = tk.Canvas(dialog, borderwidth=0, height=dh-100)
    vsb = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    # Add padding to the frame for balanced white space
    frame = ttk.Frame(canvas, padding=(24, 8, 24, 8))  # (left, top, right, bottom)
    canvas.create_window((0, 0), window=frame, anchor="nw")
    frame.bind("<Configure>", lambda event, c=canvas: c.configure(scrollregion=c.bbox("all")))

    row = 0

    # API Keys at the top
    ttk.Label(frame, text="Finnhub API Key:", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    api_entry = ttk.Entry(frame, show="*", width=24, font=default_font)
    api_entry.grid(row=row, column=1, sticky="ew", pady=4)
    api_entry.insert(0, get_settings()["api_key"])
    row += 1

    ttk.Label(frame, text="CoinGecko API Key:", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    coingecko_api_entry = ttk.Entry(frame, show="*", width=24, font=default_font)
    coingecko_api_entry.grid(row=row, column=1, sticky="ew", pady=4)
    coingecko_api_entry.insert(0, get_settings().get("coingecko_api_key", ""))
    row += 1

    ttk.Separator(frame, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
    row += 1

    # Sliders group
    ttk.Label(frame, text="Height (pixels):", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    height_entry = ttk.Entry(frame, width=8, font=default_font)
    height_entry.grid(row=row, column=1, sticky="ew", pady=4)
    height_entry.insert(0, str(ticker.ticker_height))
    row += 1

    # Move Update Interval here
    ttk.Label(frame, text="Update Interval (seconds):", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    update_interval_var = tk.IntVar(value=get_settings().get("update_interval", 300000) // 1000)
    update_interval_entry = ttk.Entry(frame, width=8, font=default_font, textvariable=update_interval_var)
    update_interval_entry.grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="Transparency:", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    transparency_var = tk.IntVar(value=get_settings().get("transparency", 100))
    transparency_scale = ttk.Scale(frame, from_=0, to=100, orient="horizontal", variable=transparency_var, length=180)
    transparency_scale.grid(row=row, column=1, sticky="ew", pady=4)
    transparency_value_label = ttk.Label(frame, text=str(transparency_var.get()), font=default_font)
    transparency_value_label.grid(row=row, column=2, sticky="w", padx=6)
    transparency_scale.config(command=lambda v: transparency_value_label.config(text=str(int(float(v)))))


    row += 1

    ttk.Label(frame, text="Scroll Speed:", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    speed_var = tk.IntVar(value=get_settings().get("speed", 2))
    speed_scale = ttk.Scale(frame, from_=1, to=20, orient="horizontal", variable=speed_var, length=180)
    speed_scale.grid(row=row, column=1, sticky="ew", pady=4)
    speed_value_label = ttk.Label(frame, text=str(speed_var.get()), font=default_font)
    speed_value_label.grid(row=row, column=2, sticky="w", padx=6)
    speed_scale.config(command=lambda v: speed_value_label.config(text=str(int(float(v)))))


    row += 1

    ttk.Label(frame, text="Glassy Opacity (0-255):", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    glass_opacity_var = tk.IntVar(value=get_settings().get("glass_opacity", 60))
    glass_opacity_scale = ttk.Scale(frame, from_=0, to=255, orient="horizontal", variable=glass_opacity_var, length=180)
    glass_opacity_scale.grid(row=row, column=1, sticky="ew", pady=4)
    glass_opacity_value_label = ttk.Label(frame, text=str(glass_opacity_var.get()), font=default_font)
    glass_opacity_value_label.grid(row=row, column=2, sticky="w", padx=6)
    glass_opacity_scale.config(command=lambda v: glass_opacity_value_label.config(text=str(int(float(v)))))


    row += 1

    ttk.Label(frame, text="Highlight Thickness (%):", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    glass_highlight_var = tk.DoubleVar(value=round(get_settings().get("glass_highlight_ratio", 0) * 100, 2))
    glass_highlight_scale = ttk.Scale(frame, from_=0, to=30, orient="horizontal", variable=glass_highlight_var, length=180)
    glass_highlight_scale.grid(row=row, column=1, sticky="ew", pady=4)
    glass_highlight_value_label = ttk.Label(frame, text=str(glass_highlight_var.get()), font=default_font)
    glass_highlight_value_label.grid(row=row, column=2, sticky="w", padx=6)
    glass_highlight_scale.config(command=lambda v: glass_highlight_value_label.config(text=f"{float(v):.2f}"))


    row += 1

    ttk.Separator(frame, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
    row += 1

    # Checkboxes group
    show_change_pct_var = tk.BooleanVar(value=get_settings().get("show_change_pct", True))
    ttk.Label(frame, text="Show Price Change & Percentage", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    show_change_pct_check = ttk.Checkbutton(frame, variable=show_change_pct_var)
    show_change_pct_check.grid(row=row, column=1, sticky="w", pady=4)
    row += 1

    play_sound_var = tk.BooleanVar(value=get_settings().get("play_sound_on_update", True))
    ttk.Label(frame, text="Play Sound on Price Update", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    play_sound_check = ttk.Checkbutton(frame, variable=play_sound_var)
    play_sound_check.grid(row=row, column=1, sticky="w", pady=4)
    row += 1

    group_crypto_first_var = tk.BooleanVar(value=get_settings().get("group_crypto_first", False))
    ttk.Label(frame, text="Group Crypto First", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    group_crypto_first_check = ttk.Checkbutton(frame, variable=group_crypto_first_var)
    group_crypto_first_check.grid(row=row, column=1, sticky="w", pady=4)
    row += 1

    ttk.Separator(frame, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
    row += 1

    # Other options
    ttk.Label(frame, text="Display Screen:", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    monitors = get_monitors()
    screen_index_var = tk.IntVar(value=get_settings().get("screen_index", 0))
    screen_combo = ttk.Combobox(frame, state="readonly", font=default_font, width=18)
    screen_combo['values'] = [f"Screen {i+1}: {m.width}x{m.height}" for i, m in enumerate(monitors)]
    screen_combo.current(screen_index_var.get())
    screen_combo.grid(row=row, column=1, sticky="ew", pady=4)
    row += 1

    ttk.Label(frame, text="Proxy Server URL:", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    proxy_entry = ttk.Entry(frame, width=24, font=default_font)
    proxy_entry.grid(row=row, column=1, sticky="ew", pady=4)
    proxy_entry.insert(0, get_settings().get("proxy", ""))
    row += 1

    ttk.Label(frame, text="Certificate File:", font=default_font).grid(row=row, column=0, sticky="w", pady=4)
    cert_file_entry = ttk.Entry(frame, width=24, font=default_font)
    cert_file_entry.grid(row=row, column=1, sticky="ew", pady=4)
    cert_file_entry.insert(0, get_settings().get("cert_file", ""))
    row += 1

    sep = ttk.Separator(frame, orient="horizontal")
    sep.grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)
    row += 1

    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=row, column=0, columnspan=3, pady=6, sticky="ew")

    def apply_settings():
        try:
            new_height = int(height_entry.get())
            new_height = max(50, min(1000, new_height))
            screen_width = get_primary_monitor_width()
            if new_height != ticker.ticker_height:
                set_settings(height=new_height)
                dialog.destroy()
                return restart_program()
            else:
                set_settings(height=new_height)
                root.geometry(f"{screen_width}x{new_height}+0+0")
                set_appbar(int(root.winfo_id()), height=new_height, width=screen_width)
                ticker.set_height(new_height)
        except Exception:
            pass
        new_api = api_entry.get().strip()
        new_cg_api = coingecko_api_entry.get().strip()
        if new_api and new_api != get_settings()["api_key"]:
            set_settings(api_key=new_api)
            ticker.create_ticker()
        set_settings(coingecko_api_key=new_cg_api)
        new_transparency = transparency_var.get()
        new_show_change_pct = show_change_pct_var.get()
        new_speed = speed_var.get()
        new_play_sound = play_sound_var.get()
        try:
            new_update_interval = int(update_interval_var.get()) * 1000
            if new_update_interval < 10000:
                new_update_interval = 10000
        except Exception:
            new_update_interval = 300000
        new_glass_opacity = glass_opacity_var.get()
        new_glass_highlight_ratio = glass_highlight_var.get() / 100.0
        new_screen_index = screen_combo.current()
        new_group_crypto_first = group_crypto_first_var.get()
        new_proxy = proxy_entry.get().strip()
        new_cert_file = cert_file_entry.get().strip()
        set_settings(
            transparency=new_transparency,
            show_change_pct=new_show_change_pct,
            speed=new_speed,
            update_interval=new_update_interval,
            play_sound_on_update=new_play_sound,
            glass_opacity=new_glass_opacity,
            glass_highlight_ratio=new_glass_highlight_ratio,
            screen_index=new_screen_index,
            group_crypto_first=new_group_crypto_first,
            proxy=new_proxy,
            cert_file=new_cert_file
        )
        set_ticker_transparency(new_transparency)
        ticker.set_speed(new_speed)
        ticker.set_update_interval(new_update_interval)
        ticker.create_ticker()
        move_ticker_to_screen(new_screen_index)
        dialog.destroy()

    ttk.Button(btn_frame, text="Manage Stocks", command=show_manage_stocks_dialog).pack(pady=4, fill="x")
    ttk.Button(btn_frame, text="Move Ticker to Screen...", command=show_screen_select_dialog).pack(pady=4, fill="x")
    ttk.Button(btn_frame, text="Apply", command=apply_settings).pack(pady=4, fill="x")
    ttk.Button(btn_frame, text="Restart Ticker", command=restart_program).pack(pady=4, fill="x")
    ttk.Button(btn_frame, text="Close Ticker", command=on_close).pack(pady=4, fill="x")
    # winsound.PlaySound("notify.wav", winsound.SND_FILENAME | winsound.SND_ASYNC)

def show_about_dialog():
    about_lines = [
        "TCKR",
        "Version 0.63.0",
        "",
        "A simple and powerful scrolling LED stock ticker application.",
        "",
        "Developed by Paul R. Charovkine",
        "© 2025 Paul R. Charovkine. All rights reserved.",
        "Licensed under the AGPL-3.0 license.",
        "",
        "Visit our website: https://github.com/krypdoh/TCKR",
        "",
        "Financial data thanks to",
        "https://finnhub.io",
        "https://coingecko.com"
    ]
    dialog = tk.Toplevel(root)
    dialog.title("About TCKR")
    sx, sy, sw, sh = get_current_screen_geometry()
    dw, dh = 440, 420
    dx = sx + (sw - dw) // 2
    dy = sy + (sh - dh) // 2
    dialog.geometry(f"{dw}x{dh}+{dx}+{dy}")
    dialog.transient(root)
    dialog.lift()
    dialog.focus_force()
    dialog.attributes("-topmost", True)
    dialog.resizable(False, False)
    icon_path = resource_path("TCKR.ico")
    if os.path.exists(icon_path):
        try:
            dialog.iconbitmap(icon_path)
        except Exception:
            pass
    frame = ttk.Frame(dialog, padding=18)
    frame.pack(fill="both", expand=True)

    # Use a Text widget for clickable links
    text = tk.Text(frame, wrap="word", font=("Segoe UI", 12), height=16, borderwidth=0, highlightthickness=0)
    text.pack(fill="both", expand=True)
    text.config(state="normal", cursor="arrow")

    # Insert lines and tag links
    link_map = {
        "https://github.com/krypdoh/TCKR": lambda e: webbrowser.open("https://github.com/krypdoh/TCKR"),
        "https://finnhub.io": lambda e: webbrowser.open("https://finnhub.io"),
        "https://coingecko.com": lambda e: webbrowser.open("https://coingecko.com"),
    }
    for idx, line in enumerate(about_lines):
        if "https://github.com/krypdoh/TCKR" in line:
            start = text.index("end-1c")
            text.insert("end", "Visit our website: ")
            link = "https://github.com/krypdoh/TCKR"
            text.insert("end", link, "github")
            text.insert("end", "\n")
        elif "https://finnhub.io" in line:
            start = text.index("end-1c")
            text.insert("end", line, "finnhub")
            text.insert("end", "\n")
        elif "https://coingecko.com" in line:
            start = text.index("end-1c")
            text.insert("end", line, "coingecko")
            text.insert("end", "\n")
        else:
            text.insert("end", line + "\n")

    # Tag config and bindings for links
    text.tag_config("github", foreground="#0066cc", underline=True)
    text.tag_bind("github", "<Button-1>", link_map["https://github.com/krypdoh/TCKR"])
    text.tag_config("finnhub", foreground="#0066cc", underline=True)
    text.tag_bind("finnhub", "<Button-1>", link_map["https://finnhub.io"])
    text.tag_config("coingecko", foreground="#0066cc", underline=True)
    text.tag_bind("coingecko", "<Button-1>", link_map["https://coingecko.com"])

    text.config(state="disabled")

    ttk.Button(frame, text="OK", command=dialog.destroy).pack(pady=(10, 0))

def on_close():
    global tray_icon_instance
    try:
        if tray_icon_instance is not None:
            tray_icon_instance.stop()
    except Exception:
        pass
    remove_appbar(int(root.winfo_id()))
    root.destroy()

def parse_command_line_args():
    parser = argparse.ArgumentParser(
        description=(
            "TCKR Stock/Crypto Ticker - Command Line Options\n"
            "\n"
            "Options:\n"
            "  --api APIKEY,                    Finnhub API key\n"
            "  --crypto-api APIKEY,             CoinGecko API key\n"
            "  --tickers LIST, -t LIST          Comma-separated tickers (e.g. BTC,ETH,MSFT,T)\n"
            "  --speed INT, -s INT              Ticker scroll speed\n"
            "  --height INT, -ht INT            Ticker height in pixels\n"
            "  --update-interval INT, -u INT    Update interval in seconds\n"
            "  --crypto-first enable|disable    Group crypto tickers first (enable/disable)\n"
            "  --change enable|disable          Show price change and percentage (enable/disable)\n"
            "  --proxy URL                      Proxy server URL (e.g. http://127.0.0.1:8080)\n"
            "  --help ,-h                       Show this help message and exit\n"
        ),
        epilog=(
            "Example:\n"
            "  tckr.exe -t BTC,ETH,MSFT,T -s 3 -ht 80 -u 120 --proxy http://127.0.0.1:8080"
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--api", dest="api", type=str, help="Finnhub API key")
    parser.add_argument("--crypto-api", dest="crypto_api", type=str, help="CoinGecko API key")
    parser.add_argument("--tickers", "-t", dest="tickers", type=str, help="Comma-separated list of tickers (e.g. BTC,ETH,MSFT,T)")
    parser.add_argument("--speed", "-s", dest="speed", type=int, help="Ticker scroll speed (integer)")
    parser.add_argument("--height", "-ht", dest="height", type=int, help="Ticker height in pixels (integer)")
    parser.add_argument("--update-interval", "-u", dest="update_interval", type=int, help="Update interval in seconds (integer)")
    parser.add_argument("--crypto-first", dest="crypto_first", choices=["enable", "disable"], help="Display crypto tickers first (enable/disable)")
    parser.add_argument("--change", dest="change", choices=["enable", "disable"], help="Show price change and percentage (enable/disable)")
    parser.add_argument("--proxy", dest="proxy", type=str, help="Proxy server URL (e.g. http://127.0.0.1:8080)")
    args, _ = parser.parse_known_args()
    return args

def apply_command_line_args(args):
    updated = False
    if args.api:
        set_settings(api_key=args.api)
        updated = True
    if args.crypto_api:
        set_settings(coingecko_api_key=args.crypto_api)
        updated = True
    if args.speed is not None:
        set_settings(speed=args.speed)
        updated = True
    if args.height is not None:
        set_settings(height=args.height)
        updated = True
    if args.update_interval is not None:
        set_settings(update_interval=args.update_interval * 1000)
        updated = True
    if args.crypto_first is not None:
        set_settings(group_crypto_first=(args.crypto_first == "enable"))
        updated = True
    if args.change is not None:
        set_settings(show_change_pct=(args.change == "enable"))
        updated = True
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        stocks = [[t, f"{t}.png"] for t in tickers]
        save_stocks(stocks)
        updated = True
    if hasattr(args, "proxy") and args.proxy is not None:
        set_settings(proxy=args.proxy)
        updated = True
    return updated

def download_and_install_subway_ticker_font():
    import winreg
    font_url = "https://github.com/krypdoh/TCKR/raw/main/res/SubwayTicker.ttf"
    font_name = "SubwayTicker.ttf"
    font_display_name = "Subway Ticker (TrueType)"
    temp_dir = tempfile.gettempdir()
    font_path = os.path.join(temp_dir, font_name)
    fonts_dir = os.path.join(os.environ["WINDIR"], "Fonts")
    dest_path = os.path.join(fonts_dir, font_name)

    try:
        # Download font
        response = requests.get(font_url, timeout=10)
        response.raise_for_status()
        with open(font_path, "wb") as f:
            f.write(response.content)
    except Exception as e:
        messagebox.showerror("Download Error", f"Could not download font:\n{e}")
        return False

    # Install font (Windows)
    try:
        # Copy font file
        if not os.path.exists(dest_path):
            # Requires admin rights!
            subprocess.run([
                "powershell", "-Command",
                f'Copy-Item -Path "{font_path}" -Destination "{fonts_dir}" -Force'
            ], check=True, shell=True)
        # Add registry entry
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts", 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, font_display_name, 0, winreg.REG_SZ, font_name)
        messagebox.showinfo(
            "Font Installed",
            "Subway Ticker font installed successfully.\n\n"
            "You may need to log off or reboot your computer for the font to become available."
        )
        return True
    except Exception as e:
        messagebox.showerror("Install Error", f"Could not install font:\n{e}\nTry running as administrator.")
        return False

def is_font_installed():
    import winreg
    fonts_dir = os.path.join(os.environ["WINDIR"], "Fonts")
    font_file = "SubwayTicker.ttf"
    font_display_name = "Subway Ticker (TrueType)"
    font_path = os.path.join(fonts_dir, font_file)
    # Check file
    if not os.path.exists(font_path):
        return False
    # Check registry
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts") as key:
            value, _ = winreg.QueryValueEx(key, font_display_name)
            if value.lower() != font_file.lower():
                return False
    except Exception:
        return False
    return True

if __name__ == "__main__":
    # Parse command line arguments FIRST, before any other logic
    args = parse_command_line_args()
    # argparse will automatically exit if -h/--help is used

    # Only apply CLI args and continue if not exiting
    apply_command_line_args(args)

    settings = get_settings()
    if not settings or not settings.get("api_key"):
        api_key = prompt_for_api_key()
        if not api_key:
            exit(0)
        settings = get_settings()
    initial_height = settings.get("height", 60)
    initial_speed = settings.get("speed", 1.0)
    initial_update_interval = settings.get("update_interval", 300000)

    root = tk.Tk()
    root.overrideredirect(True)
    root.configure(bg="black")
    root.attributes("-topmost", True)
    set_ticker_transparency(settings.get("transparency", 100))

    # --- Subway Ticker font check and prompt ---
    import tkinter.font as tkFont
    if "Subway Ticker" not in tkFont.families():
        root.withdraw()
        result = messagebox.askyesno(
            "Font Not Installed",
            "The Subway Ticker font is not installed on your system.\n\n"
            "Would you like to download and install it now?"
        )
        if result:
            success = download_and_install_subway_ticker_font()
            if success:
                root.destroy()
                sys.exit(0)
            else:
                root.deiconify()
        else:
            messagebox.showinfo(
                "Font Required",
                "Please install SubwayTicker.ttf to use the custom ticker font.\n\n"
                "To install:\n"
                "1. Locate SubwayTicker.ttf in your app folder or download it.\n"
                "2. Double-click the file and click 'Install'.\n"
                "3. Restart this application."

            )
            root.deiconify()   
    # --- End font check ---

    stocks = load_stocks()
    ticker = ScrollingTicker(root, stocks, height=initial_height, speed=initial_speed)
    ticker.set_update_interval(initial_update_interval)
    ticker.pack(fill="both", expand=True)
    root.update()

    monitors = get_monitors()
    screen_index = settings.get("screen_index", 0)
    if screen_index < 0 or screen_index >= len(monitors):
        screen_index = 0
    m = monitors[screen_index]
    root.geometry(f"{m.width}x{initial_height}+{m.x}+{m.y}")
    set_appbar(int(root.winfo_id()), height=initial_height, x=m.x, y=m.y, width=m.width)
    root.focus_force()

    def change_height(delta):
        new_height = max(50, min(200, ticker.ticker_height + delta))
        set_settings(height=new_height)
        screen_width = get_primary_monitor_width()
        root.geometry(f"{screen_width}x{new_height}+0+0")
        set_appbar(int(root.winfo_id()), height=new_height, width=screen_width)
        ticker.set_height(new_height)

    root.bind("<Up>", lambda e: change_height(10))
    root.bind("<Down>", lambda e: change_height(-10))
    root.bind("<Button-3>", lambda e: show_settings_dialog())
    root.protocol("WM_DELETE_WINDOW", on_close)

    if not stocks:
        messagebox.showerror("Stocks Error", f"No stocks found in {STOCKS_FILE}.")
        exit(1)

    start_tray_icon()
    root.mainloop()
