"""
Author: Paul R. Charovkine
Program: TCKR.py
Date: 2025.10.15
Version: 0.99.11
License: GNU AGPLv3

Description:
This program implements a customizable stock ticker application using Tkinter for Windows.
It displays real-time stock prices and logos in a scrolling ticker bar at the top of the screen.
Users can manage the list of stocks, adjust the ticker height, and update their Finnhub API key
through modern, user-friendly dialog boxes. The ticker integrates with the Windows AppBar for
persistent display and supports restarting or closing the ticker from the GUI.
"""

import sys
import os
import json
import requests
import time
import datetime
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtMultimedia import QSoundEffect
import webbrowser
import ctypes
from ctypes import wintypes
import concurrent.futures
import argparse
import shutil
import signal
import atexit

APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "TCKR")
SETTINGS_FILE = os.path.join(APPDATA_DIR, "TCKR.Settings.json")
STOCKS_FILE = os.path.join(APPDATA_DIR, "TCKR.Tickers.json")

# Global variable to track the main ticker window for emergency cleanup
_global_ticker_window = None

ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003
ABE_TOP = 1

# AppBar notification messages
ABN_STATECHANGE = 0x00000000
ABN_POSCHANGED = 0x00000001
ABN_FULLSCREENAPP = 0x00000002
ABN_WINDOWARRANGE = 0x00000003

class APPBARDATA(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('hWnd', wintypes.HWND),
        ('uCallbackMessage', wintypes.UINT),
        ('uEdge', wintypes.UINT),
        ('rc', wintypes.RECT),
        ('lParam', wintypes.LPARAM),
    ]

def set_appbar(hwnd, height, rect):
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32

    # Ensure DPI awareness
    try:
        user32.SetProcessDPIAware()
    except:
        pass

    # CRITICAL: Get the ACTUAL physical window height FIRST
    # On high-DPI screens, Qt's logical pixels differ from Windows physical pixels
    # We need to use the physical height for AppBar registration
    actual_window_rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(actual_window_rect))
    actual_window_height = actual_window_rect.bottom - actual_window_rect.top
    print(f"[APPBAR] Logical height requested: {height}px, Actual window height: {actual_window_height}px")
    
    # Use the actual physical height for AppBar registration
    appbar_height = actual_window_height

    msg_id = user32.RegisterWindowMessageW("TCKR_APPBAR_MESSAGE")
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    abd.uCallbackMessage = msg_id
    abd.uEdge = ABE_TOP
    
    # CRITICAL: Use the full screen coordinates for the AppBar
    # rect.right() gives us the right edge coordinate (left + width)
    abd.rc.left = rect.left()
    abd.rc.top = rect.top()
    abd.rc.right = rect.right()  # Use rect.right() which is left + width
    abd.rc.bottom = rect.top() + appbar_height  # Use ACTUAL physical height

    # Register as appbar
    result = shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
    print(f"[APPBAR] ABM_NEW result: {result}")
    print(f"[APPBAR] Registration: left={abd.rc.left}, top={abd.rc.top}, right={abd.rc.right}, bottom={abd.rc.bottom}, width={abd.rc.right - abd.rc.left}")
    
    # Query position - this tells us where Windows wants to place us
    shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
    print(f"[APPBAR] QUERYPOS returned: top={abd.rc.top}, bottom={abd.rc.bottom}")
    
    # CRITICAL: Set the proposed rectangle coordinates with PHYSICAL height
    # For top edge, we want the full width of the screen
    abd.rc.left = rect.left()
    abd.rc.top = rect.top()  # Always at the very top
    abd.rc.right = rect.right()  # Full width
    abd.rc.bottom = rect.top() + appbar_height  # Reserve using ACTUAL physical height
    
    # Set the position - this reserves the space
    shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
    print(f"[APPBAR] SETPOS with: left={abd.rc.left}, top={abd.rc.top}, right={abd.rc.right}, bottom={abd.rc.bottom}, height={abd.rc.bottom - abd.rc.top}")
    
    # After SETPOS, check what Windows actually gave us
    shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
    actual_reserved_height = abd.rc.bottom - abd.rc.top
    print(f"[APPBAR] After SETPOS, QUERYPOS shows: top={abd.rc.top}, bottom={abd.rc.bottom}, reserved={actual_reserved_height}")
    
    if actual_reserved_height < appbar_height:
        print(f"[APPBAR WARNING] Windows only reserved {actual_reserved_height}px instead of {appbar_height}px")
        # Try one more time with a brief pause to let Windows process the request
        abd.rc.top = rect.top()
        abd.rc.bottom = rect.top() + appbar_height
        abd.rc.left = rect.left()
        abd.rc.right = rect.right()
        shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        time.sleep(0.05)  # Reduced delay
        shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        if abd.rc.bottom - abd.rc.top >= appbar_height:
            print(f"[APPBAR] Reservation successful on retry")
        else:
            print(f"[APPBAR] Space reservation limited by Windows - using available space")
    
    # Use the actual physical window height for work area reservation
    work_area_top_offset = actual_window_height
    
    # Broadcast WM_SETTINGCHANGE to force all applications to recalculate work area
    # This is critical - without this, other apps may not respect the AppBar reservation
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    
    # CRITICAL FIX: Verify and enforce work area adjustment
    # Get monitor info to calculate work area
    monitor_info = wintypes.RECT()
    monitor_info.left = rect.left()
    monitor_info.top = rect.top()
    monitor_info.right = rect.right()
    monitor_info.bottom = rect.bottom()
    
    # Check current work area
    work_area_before = wintypes.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area_before), 0)  # SPI_GETWORKAREA = 48
    print(f"[APPBAR] Work area BEFORE: top={work_area_before.top}, bottom={work_area_before.bottom}")
    
    # After setting AppBar position, Windows should have adjusted work area automatically
    # Let's verify
    work_area_check = wintypes.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area_check), 0)
    print(f"[APPBAR] Work area AFTER SETPOS: top={work_area_check.top}, expected={rect.top() + work_area_top_offset}")
    
    # CRITICAL: Manually set work area to ensure other apps respect our space
    # The AppBar API should do this automatically, but it doesn't always work reliably
    # We only do this during initial setup, not in response to ABN_POSCHANGED (which would cause a loop)
    # Use the actual physical window height (work_area_top_offset) not the logical height
    if work_area_check.top < (rect.top() + work_area_top_offset):
        print(f"[APPBAR] Work area not adjusted by AppBar API - manually setting it")
        new_work_area = wintypes.RECT()
        new_work_area.left = rect.left()
        new_work_area.top = rect.top() + work_area_top_offset  # Use ACTUAL window height
        new_work_area.right = rect.right()
        new_work_area.bottom = rect.bottom()
        
        # Set the work area without triggering file system updates
        SPI_SETWORKAREA = 47
        SPIF_SENDCHANGE = 0x0002  # Broadcast change but don't update INI files
        result = user32.SystemParametersInfoW(SPI_SETWORKAREA, 0, 
                                             ctypes.byref(new_work_area), 
                                             SPIF_SENDCHANGE)
        print(f"[APPBAR] SystemParametersInfo(SPI_SETWORKAREA) result: {result}")
        print(f"[APPBAR] Set work area top to: {new_work_area.top} (screen top {rect.top()} + actual window height {work_area_top_offset})")
        
        # Small delay to let Windows process the change
        time.sleep(0.1)
        
        # Verify it worked
        work_area_verify = wintypes.RECT()
        user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area_verify), 0)
        print(f"[APPBAR] Work area after manual adjustment: top={work_area_verify.top}")
    else:
        print(f"[APPBAR] Work area already correctly set at top={work_area_check.top}")
    
    # Broadcast WM_SETTINGCHANGE with work area change to notify other apps
    # This is separate from the SystemParametersInfo call above
    user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 
                                47, 0,  # SPI_SETWORKAREA = 47
                                SMTO_ABORTIFHUNG, 2000, None)
    
    print(f"[APPBAR] Broadcasted WM_SETTINGCHANGE to all windows")
    
    # CRITICAL: Force window position AFTER broadcasts using SetWindowPos
    # The broadcasts may cause Windows to reposition windows, so we need to 
    # force our position again after the work area has been recalculated
    time.sleep(0.05)  # Brief pause to let broadcasts process
    
    # Use SetWindowPos with TOPMOST and NOACTIVATE to ensure we're at the absolute top
    # but don't steal focus from other windows
    HWND_TOPMOST = -1
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    # Use actual_window_height (physical pixels) instead of height (logical pixels)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, rect.left(), rect.top(), 
                       rect.width(), actual_window_height, SWP_SHOWWINDOW | SWP_NOACTIVATE)
    
    print(f"[APPBAR] Final SetWindowPos to x={rect.left()}, y={rect.top()}, width={rect.width()}, height={actual_window_height}")
    
    return abd.rc.top  # Return the actual top position Windows gave us

def force_window_to_top(hwnd, rect, height):
    """Force window to absolute top of screen, ignoring other docked apps"""
    user32 = ctypes.windll.user32
    
    # Constants for SetWindowPos
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    
    # First, move to absolute top position and make it topmost
    user32.SetWindowPos(hwnd, HWND_TOPMOST, rect.left(), rect.top(), 
                       rect.width(), height, SWP_SHOWWINDOW)
    
    # Get the actual window position to verify
    window_rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(window_rect))
    
    # If not at the very top, force it there multiple times
    max_attempts = 5
    for attempt in range(max_attempts):
        if window_rect.top <= rect.top():
            break
        
        # Force move to top with TOPMOST flag
        user32.SetWindowPos(hwnd, HWND_TOPMOST, rect.left(), rect.top(), 
                           rect.width(), height, SWP_NOACTIVATE)
        
        # Check position again
        user32.GetWindowRect(hwnd, ctypes.byref(window_rect))
        
        if attempt < max_attempts - 1:
            time.sleep(0.1)  # Brief pause between attempts
    
    return window_rect.top

def get_work_area(rect):
    """Get the work area of the screen (area not occupied by taskbars, etc.)"""
    if sys.platform != "win32":
        return rect
    
    user32 = ctypes.windll.user32
    
    # Get work area for the monitor containing this rectangle
    monitor_info = wintypes.RECT()
    monitor_info.left = rect.left()
    monitor_info.top = rect.top()
    monitor_info.right = rect.right()
    monitor_info.bottom = rect.bottom()
    
    # SystemParametersInfo to get work area
    work_area = wintypes.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0)  # SPI_GETWORKAREA = 48
    
    return work_area

def remove_appbar(hwnd):
    """Remove the AppBar registration and restore the work area"""
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    
    print(f"[APPBAR] Removing AppBar registration for window handle {hwnd}")
    
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    result = shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
    print(f"[APPBAR] ABM_REMOVE result: {result}")
    
    # CRITICAL: Force Windows to recalculate work area after AppBar removal
    if sys.platform == "win32":
        from ctypes import wintypes
        
        # Method 1: Tell Windows to recalculate work area automatically
        # This should handle remaining AppBars (like taskbar) correctly
        SPI_SETWORKAREA = 47
        SPIF_SENDCHANGE = 0x0002
        SPIF_UPDATEINIFILE = 0x0001
        
        # Pass NULL to let Windows recalculate the work area based on remaining AppBars
        result1 = user32.SystemParametersInfoW(SPI_SETWORKAREA, 0, None, 
                                              SPIF_SENDCHANGE | SPIF_UPDATEINIFILE)
        print(f"[APPBAR] SystemParametersInfo auto-recalculate result: {result1}")
        
        # Method 2: Force a complete desktop refresh
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        
        # Broadcast work area change
        user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 
                                  SPI_SETWORKAREA, 0,
                                  SMTO_ABORTIFHUNG, 3000, None)
        
        # Also broadcast display settings change to force a complete refresh
        user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 
                                  0, ctypes.c_wchar_p("intl"),
                                  SMTO_ABORTIFHUNG, 3000, None)
        
        # Give Windows time to process the changes
        time.sleep(0.1)
        
        # Verify the work area was restored
        work_area_after = wintypes.RECT()
        user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area_after), 0)  # SPI_GETWORKAREA = 48
        print(f"[APPBAR] Work area after removal: top={work_area_after.top}, left={work_area_after.left}, right={work_area_after.right}, bottom={work_area_after.bottom}")
        
        print(f"[APPBAR] AppBar removal and work area restoration completed")

def global_cleanup_handler():
    """Global cleanup function for unexpected application termination"""
    global _global_ticker_window
    if _global_ticker_window and sys.platform == "win32":
        try:
            print("[EMERGENCY] Global cleanup handler activated - removing AppBar")
            remove_appbar(int(_global_ticker_window.winId()))
        except Exception as e:
            print(f"[EMERGENCY] Global cleanup failed: {e}")

def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown"""
    print(f"[SIGNAL] Received signal {signum} - performing emergency cleanup")
    global_cleanup_handler()
    sys.exit(0)

def is_market_open():
    """
    Check if the US stock market is currently open.
    Returns True if market is open, False if closed.
    
    US Stock Market Hours (Eastern Time):
    - Monday to Friday: 9:30 AM to 4:00 PM ET
    - Closed on weekends and federal holidays
    
    Uses pandas_market_calendars for accurate market hours including holidays.
    Falls back to simpler implementations if library is not available.
    """
    try:
        # Method 1: Use pandas_market_calendars for most accurate market hours
        import pandas_market_calendars as mcal
        import pandas as pd
        
        # Get NYSE calendar (standard US stock market hours)
        nyse = mcal.get_calendar('NYSE')
        
        # Get current time (pandas_market_calendars handles timezones internally)
        now = pd.Timestamp.now(tz='America/New_York')
        
        # Get today's schedule
        schedule = nyse.schedule(start_date=now.date(), end_date=now.date())
        
        # If no schedule for today, market is closed (weekend or holiday)
        if schedule.empty:
            return False
        
        # Get market open and close times for today
        market_open_time = schedule.iloc[0]['market_open']
        market_close_time = schedule.iloc[0]['market_close']
        
        # Check if current time is within market hours
        return market_open_time <= now <= market_close_time
    
    except (ImportError, Exception):
        # Method 2: Fall back to pytz-based implementation
        try:
            import pytz
            
            # Get current time in Eastern Time
            eastern = pytz.timezone('US/Eastern')
            now = datetime.datetime.now(eastern)
            
            # Check if it's a weekend
            if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
                return False
            
            # Check if it's within market hours (9:30 AM to 4:00 PM ET)
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            
            return market_open <= now <= market_close
        
        except (ImportError, Exception):
            # Method 3: Fall back to simplified UTC check if pytz also not available
            # This assumes Eastern Time is UTC-5 (standard) or UTC-4 (daylight)
            utc_now = datetime.datetime.utcnow()
            
            # Approximate Eastern Time (this is not perfect due to DST)
            # Using UTC-5 as approximation
            eastern_approx = utc_now - datetime.timedelta(hours=5)
            
            # Check if it's a weekend
            if eastern_approx.weekday() >= 5:
                return False
            
            # Check if it's within approximate market hours
            if 9 <= eastern_approx.hour < 16:
                if eastern_approx.hour == 9 and eastern_approx.minute < 30:
                    return False
                return True
            
            return False

def get_market_status_info():
    """
    Get market status information with appropriate colors.
    Returns tuple: (market_text, market_color, status_text, status_color)
    """
    if is_market_open():
        return ("Market:", QtGui.QColor("#00B3FF"), "Open", QtGui.QColor("#00FF40"))
    else:
        return ("Market:", QtGui.QColor("#00B3FF"), "Closed", QtGui.QColor("#FF5555"))

def diagnose_appbar_state(hwnd, expected_height):
    """Diagnose the current AppBar state and work area to help troubleshoot reservation issues"""
    if sys.platform != "win32":
        return
    
    user32 = ctypes.windll.user32
    
    # Get window position
    window_rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(window_rect))
    actual_height = window_rect.bottom - window_rect.top
    
    # Get work area
    work_area = wintypes.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0)  # SPI_GETWORKAREA = 48
    
    print(f"[APPBAR DIAGNOSTICS]")
    print(f"  Window position: top={window_rect.top}, bottom={window_rect.bottom}, height={actual_height}")
    print(f"  Expected height: {expected_height}")
    print(f"  Work area: top={work_area.top}, left={work_area.left}, right={work_area.right}, bottom={work_area.bottom}")
    print(f"  Space reserved at top: {work_area.top} pixels")
    
    if work_area.top < expected_height:
        print(f"  ⚠️ WARNING: Work area top ({work_area.top}) is less than expected height ({expected_height})")
        print(f"     This means Windows did not reserve the full space for the AppBar")
        print(f"     Other windows will overlap the ticker bar")
    elif work_area.top > expected_height:
        print(f"  ℹ️ Work area reserved MORE space than requested ({work_area.top} vs {expected_height})")
    else:
        print(f"  ✓ Work area correctly reserved {expected_height} pixels at top")
    
    return work_area.top

def cleanup_orphaned_appbars():
    """Cleanup any orphaned appbar registrations from previous TCKR instances"""
    if sys.platform != "win32":
        return
    
    # Skip cleanup entirely - it was causing more problems than it solved
    # by interfering with window detection and appbar registration
    print("[STARTUP] Skipping appbar cleanup to avoid interference")

def get_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "transparency": 100,
        "show_change_pct": True,
        "speed": 2,
        "update_interval": 300,  # Default: 300 seconds (5 minutes)
        "play_sound_on_update": True,
        "led_flicker_effect": False,  # LED flickering disabled by default (removed from render)
        "led_bloom_effect": True,  # Enable glow/bloom around bright colors
        "led_ghosting_effect": True,  # Enable motion blur/trailing effect
        "led_icon_matrix": True,  # Apply LED matrix overlay to icons
        "led_glass_glare": True,  # Enable glass cover with reflections/glare
        "glass_opacity": 60,
        "glass_highlight_ratio": 0,
        "screen_index": 0,
        "coingecko_api_key": "",
        "finnhub_api_key": "",
        "finnhub_api_key_2": "",  # Optional second API key for load balancing
        "group_crypto_first": False,
        "proxy": "",
        "cert_file": "",
        "ticker_height": 60,
        "global_text_glow": True  # Subtle glow on all text (less intense than 5% price change glow)
    }

def save_settings(settings):
    os.makedirs(APPDATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

def load_stocks():
    if os.path.exists(STOCKS_FILE):
        try:
            with open(STOCKS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return [["AAPL", "AAPL.png"], ["GOOG", "GOOG.png"], ["MSFT", "MSFT.png"]]

def save_stocks(stocks):
    os.makedirs(APPDATA_DIR, exist_ok=True)
    with open(STOCKS_FILE, "w") as f:
        json.dump(stocks, f)

class FinnhubApiKeyDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter Finnhub API Key")
        layout = QtWidgets.QVBoxLayout(self)

        label = QtWidgets.QLabel(
            'A Finnhub API key is required.<br>'
            'Get a free API key at: '
            '<a href="https://finnhub.io/register">https://finnhub.io/register</a>'
        )
        label.setOpenExternalLinks(True)
        label.setTextFormat(QtCore.Qt.RichText)
        layout.addWidget(label)

        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setPlaceholderText("Enter your Finnhub API key here")
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addWidget(self.api_key_edit)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_api_key(self):
        return self.api_key_edit.text().strip()

def ensure_finnhub_api_key(parent=None):
    settings = get_settings()
    api_key = settings.get("finnhub_api_key", "").strip()
    if api_key:
        return api_key
    dlg = FinnhubApiKeyDialog(parent)
    if dlg.exec_() == QtWidgets.QDialog.Accepted:
        api_key = dlg.get_api_key()
        if api_key:
            settings["finnhub_api_key"] = api_key
            save_settings(settings)
            return api_key
    return None

def fetch_finnhub_quote(ticker, api_key):
    url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={api_key}"
    settings = get_settings()
    proxies = None
    verify = True
    if settings.get("use_proxy") and settings.get("proxy"):
        proxies = {
            "http": settings["proxy"],
            "https": settings["proxy"]
        }
    if settings.get("use_cert") and settings.get("cert_file"):
        verify = settings["cert_file"]
    try:
        # print(f"[API CALL] GET {url}")  # Commented for less verbose output
        response = requests.get(url, timeout=10, proxies=proxies, verify=verify)
        # print(f"[API RESPONSE] Status: {response.status_code}")  # Commented for less verbose output
        response.raise_for_status()
        data = response.json()
        # print(f"[API DATA] {ticker}: {data}")  # Commented for less verbose output
        price = data.get("c")
        prev_close = data.get("pc")
        return ticker, (price, prev_close)
    except Exception as e:
        print(f"[API ERROR] {ticker}: {e}")
        return ticker, (None, None)

def fetch_all_stock_prices(tickers, api_key, api_key_2=None):
    """
    Fetch stock prices using one or two API keys.
    If api_key_2 is provided, alternates between keys every 30 calls.
    """
    prices = {}
    batch_size = 10
    call_count = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i+batch_size]
            
            # Determine which API key to use for this batch
            # Switch to second key after 30 calls (3 batches of 10)
            if api_key_2 and call_count >= 30:
                current_key = api_key_2
                # print(f"[API KEY] Using API Key 2 for batch {i//batch_size + 1}")  # Commented for less verbose output
            else:
                current_key = api_key
                # if api_key_2:  # Commented for less verbose output
                #     print(f"[API KEY] Using API Key 1 for batch {i//batch_size + 1}")
            
            futures = [executor.submit(fetch_finnhub_quote, ticker, current_key) for ticker in batch]
            for future in concurrent.futures.as_completed(futures):
                tkr, (price, prev_close) = future.result()
                prices[tkr] = (price, prev_close)
                call_count += 1
                
                # Reset counter after 60 calls to alternate back to first key
                if call_count >= 60:
                    call_count = 0
                    
            if i + batch_size < len(tickers):
                time.sleep(3.5)  # Wait 3.5 seconds between batches
    return prices

def fetch_all_stock_prices_with_429(tickers, api_key, api_key_2=None):
    """
    Fetch stock prices with 429 detection using one or two API keys.
    If api_key_2 is provided, alternates between keys every 30 calls.
    """
    prices = {}
    batch_size = 10
    had_429 = False
    call_count = 0
    
    def fetch_with_status(ticker, api_key):
        url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={api_key}"
        settings = get_settings()
        proxies = None
        verify = True
        if settings.get("use_proxy") and settings.get("proxy"):
            proxies = {
                "http": settings["proxy"],
                "https": settings["proxy"]
            }
        if settings.get("use_cert") and settings.get("cert_file"):
            verify = settings["cert_file"]
        try:
            # print(f"[API CALL] GET {url}")  # Commented for less verbose output
            response = requests.get(url, timeout=10, proxies=proxies, verify=verify)
            # print(f"[API RESPONSE] Status: {response.status_code}")  # Commented for less verbose output
            response.raise_for_status()
            data = response.json()
            # print(f"[API DATA] {ticker}: {data}")  # Commented for less verbose output
            price = data.get("c")
            prev_close = data.get("pc")
            return ticker, (price, prev_close), response.status_code
        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, 'status_code', None)
            print(f"[API ERROR] {ticker}: {e}")
            return ticker, (None, None), status_code
        except Exception as e:
            print(f"[API ERROR] {ticker}: {e}")
            return ticker, (None, None), None

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i+batch_size]
            
            # Determine which API key to use for this batch
            # Switch to second key after 30 calls (3 batches of 10)
            if api_key_2 and call_count >= 30:
                current_key = api_key_2
                # print(f"[API KEY] Using API Key 2 for batch {i//batch_size + 1}")  # Commented for less verbose output
            else:
                current_key = api_key
                # if api_key_2:  # Commented for less verbose output
                #     print(f"[API KEY] Using API Key 1 for batch {i//batch_size + 1}")
            
            futures = [executor.submit(fetch_with_status, ticker, current_key) for ticker in batch]
            for future in concurrent.futures.as_completed(futures):
                tkr, (price, prev_close), status_code = future.result()
                prices[tkr] = (price, prev_close)
                if status_code == 429:
                    had_429 = True
                call_count += 1
                
                # Reset counter after 60 calls to alternate back to first key
                if call_count >= 60:
                    call_count = 0
                    
            if i + batch_size < len(tickers):
                time.sleep(3.5)
    return prices, had_429

def get_ticker_icon(ticker, size=32):
    images_dir = os.path.join(APPDATA_DIR, "TCKR.images")
    os.makedirs(images_dir, exist_ok=True)
    ticker = ticker.upper()
    local_path = os.path.join(images_dir, f"{ticker}.png")
    pixmap = None
    if os.path.exists(local_path):
        try:
            pixmap = QtGui.QPixmap(local_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        except Exception:
            pass
    if pixmap is None or pixmap.isNull():
        url = f"https://raw.githubusercontent.com/krypdoh/stock-icons/refs/heads/main/ticker_icons/{ticker}.png"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(resp.content)
                pixmap = pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        except Exception:
            pass
    if pixmap is None or pixmap.isNull():
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.transparent)

    # Subtle pixelation effect (reduced for better clarity)
    pixel_size = max(16, int(size // 1.5))  # Less aggressive pixelation, convert to int
    small_pixmap = pixmap.scaled(pixel_size, pixel_size, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
    pixmap = small_pixmap.scaled(size, size, QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)

    # Lighter scanline effect for better icon visibility
    scanline_pixmap = QtGui.QPixmap(pixmap.size())
    scanline_pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(scanline_pixmap)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
    painter.drawPixmap(0, 0, pixmap)
    scanline_color = QtGui.QColor(0, 0, 0, 25)  # Lighter opacity for clarity
    for y in range(0, pixmap.height(), 4):      # Every 4 pixels (less frequent)
        painter.fillRect(0, y, pixmap.width(), 1, scanline_color)  # Thinner lines
    
    # LED Matrix Overlay (if enabled in settings) - subtle version
    if get_settings().get("led_icon_matrix", True):
        # Add subtle LED pixel grid pattern
        led_grid_color = QtGui.QColor(0, 0, 0, 30)  # Lighter for better visibility
        # Vertical lines (less frequent)
        for x in range(0, pixmap.width(), 6):
            painter.fillRect(x, 0, 1, pixmap.height(), led_grid_color)
        # Horizontal lines (less frequent)
        for y in range(0, pixmap.height(), 6):
            painter.fillRect(0, y, pixmap.width(), 1, led_grid_color)
    
    painter.end()
    return scanline_pixmap

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.settings = get_settings()
        # Store original settings to detect what changed
        self.original_settings = self.settings.copy()
        layout = QtWidgets.QFormLayout(self)

        self.finnhub_api_key_edit = QtWidgets.QLineEdit(self.settings.get("finnhub_api_key", ""))
        self.finnhub_api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addRow("Finnhub API Key:", self.finnhub_api_key_edit)

        self.finnhub_api_key_2_edit = QtWidgets.QLineEdit(self.settings.get("finnhub_api_key_2", ""))
        self.finnhub_api_key_2_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.finnhub_api_key_2_edit.setPlaceholderText("Optional - for load balancing")
        layout.addRow("Finnhub API Key 2:", self.finnhub_api_key_2_edit)

        self.transparency_spin = QtWidgets.QSpinBox()
        self.transparency_spin.setRange(0, 100)
        self.transparency_spin.setValue(self.settings.get("transparency", 100))
        self.scroll_speed_spin = QtWidgets.QSpinBox()
        self.scroll_speed_spin.setRange(1, 50)
        self.scroll_speed_spin.setValue(self.settings.get("speed", 2))
        self.ticker_height_spin = QtWidgets.QSpinBox()
        self.ticker_height_spin.setRange(24, 200)
        self.ticker_height_spin.setValue(self.settings.get("ticker_height", 60))

        self.update_interval_spin = QtWidgets.QSpinBox()
        self.update_interval_spin.setRange(10, 3600)
        self.update_interval_spin.setValue(self.settings.get("update_interval", 300))
        layout.addRow("Update Interval (seconds):", self.update_interval_spin)

        self.led_flicker_checkbox = QtWidgets.QCheckBox("Enable LED Flicker Effect")
        self.led_flicker_checkbox.setChecked(self.settings.get("led_flicker_effect", True))
        
        self.led_bloom_checkbox = QtWidgets.QCheckBox("Enable LED Bloom/Glow Effect")
        self.led_bloom_checkbox.setChecked(self.settings.get("led_bloom_effect", True))
        
        self.led_ghosting_checkbox = QtWidgets.QCheckBox("Enable Motion Blur/Ghosting")
        self.led_ghosting_checkbox.setChecked(self.settings.get("led_ghosting_effect", True))
        
        self.led_icon_matrix_checkbox = QtWidgets.QCheckBox("Enable LED Icon Matrix Overlay")
        self.led_icon_matrix_checkbox.setChecked(self.settings.get("led_icon_matrix", True))
        
        self.led_glass_glare_checkbox = QtWidgets.QCheckBox("Enable Glass Cover with Glare/Reflections")
        self.led_glass_glare_checkbox.setChecked(self.settings.get("led_glass_glare", True))

        self.global_text_glow_checkbox = QtWidgets.QCheckBox("Enable Subtle Text Glow (All Text)")
        self.global_text_glow_checkbox.setChecked(self.settings.get("global_text_glow", True))

        self.play_sound_checkbox = QtWidgets.QCheckBox("Play Sound After Update")
        self.play_sound_checkbox.setChecked(self.settings.get("play_sound_on_update", True))

        self.display_combo = QtWidgets.QComboBox()
        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        for i, screen in enumerate(screens):
            geom = screen.geometry()
            self.display_combo.addItem(
                f"Display {i+1} ({geom.width()}x{geom.height()})", i
            )
        self.display_combo.setCurrentIndex(self.settings.get("screen_index", 0))

        layout.addRow("Scroll Speed (px/frame):", self.scroll_speed_spin)
        layout.addRow("Ticker Height (px):", self.ticker_height_spin)
        layout.addRow("Transparency (%):", self.transparency_spin)
        layout.addRow("Choose Display:", self.display_combo)
        layout.addRow(self.led_flicker_checkbox)
        layout.addRow(self.led_bloom_checkbox)
        layout.addRow(self.led_ghosting_checkbox)
        layout.addRow(self.led_icon_matrix_checkbox)
        layout.addRow(self.led_glass_glare_checkbox)
        layout.addRow(self.global_text_glow_checkbox)
        layout.addRow(self.play_sound_checkbox)

        net_group = QtWidgets.QGroupBox("Network Settings")
        net_layout = QtWidgets.QFormLayout(net_group)

        self.use_cert_checkbox = QtWidgets.QCheckBox("Use Certificate")
        self.use_cert_checkbox.setChecked(bool(self.settings.get("use_cert", False)))
        self.cert_file_edit = QtWidgets.QLineEdit(self.settings.get("cert_file", ""))
        self.cert_file_edit.setEnabled(self.use_cert_checkbox.isChecked())
        self.cert_file_btn = QtWidgets.QPushButton("Browse...")
        self.cert_file_btn.setEnabled(self.use_cert_checkbox.isChecked())
        self.cert_file_btn.clicked.connect(self.browse_cert_file)
        self.use_cert_checkbox.toggled.connect(self.cert_file_edit.setEnabled)
        self.use_cert_checkbox.toggled.connect(self.cert_file_btn.setEnabled)

        cert_layout = QtWidgets.QHBoxLayout()
        cert_layout.addWidget(self.cert_file_edit)
        cert_layout.addWidget(self.cert_file_btn)
        net_layout.addRow(self.use_cert_checkbox, cert_layout)

        self.use_proxy_checkbox = QtWidgets.QCheckBox("Use Proxy")
        self.use_proxy_checkbox.setChecked(bool(self.settings.get("use_proxy", False)))
        self.proxy_edit = QtWidgets.QLineEdit(self.settings.get("proxy", ""))
        self.proxy_edit.setEnabled(self.use_proxy_checkbox.isChecked())
        self.use_proxy_checkbox.toggled.connect(self.proxy_edit.setEnabled)
        net_layout.addRow(self.use_proxy_checkbox, self.proxy_edit)

        layout.addRow(net_group)

        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def browse_cert_file(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Certificate File", "", "Certificate Files (*.pem *.crt *.cer);;All Files (*)")
        if fname:
            self.cert_file_edit.setText(fname)

    def accept(self):
        s = get_settings()
        s["transparency"] = self.transparency_spin.value()
        s["speed"] = self.scroll_speed_spin.value()
        s["ticker_height"] = self.ticker_height_spin.value()
        s["update_interval"] = self.update_interval_spin.value()
        s["screen_index"] = self.display_combo.currentIndex()
        s["use_cert"] = self.use_cert_checkbox.isChecked()
        s["cert_file"] = self.cert_file_edit.text().strip()
        s["use_proxy"] = self.use_proxy_checkbox.isChecked()
        s["proxy"] = self.proxy_edit.text().strip()
        s["led_flicker_effect"] = self.led_flicker_checkbox.isChecked()
        s["led_bloom_effect"] = self.led_bloom_checkbox.isChecked()
        s["led_ghosting_effect"] = self.led_ghosting_checkbox.isChecked()
        s["led_icon_matrix"] = self.led_icon_matrix_checkbox.isChecked()
        s["led_glass_glare"] = self.led_glass_glare_checkbox.isChecked()
        s["global_text_glow"] = self.global_text_glow_checkbox.isChecked()
        s["play_sound_on_update"] = self.play_sound_checkbox.isChecked()
        s["finnhub_api_key"] = self.finnhub_api_key_edit.text().strip()
        s["finnhub_api_key_2"] = self.finnhub_api_key_2_edit.text().strip()
        save_settings(s)
        
        # Check what settings actually changed
        major_changes = (
            self.original_settings.get("ticker_height") != s["ticker_height"] or
            self.original_settings.get("screen_index") != s["screen_index"] or
            self.original_settings.get("use_cert") != s["use_cert"] or
            self.original_settings.get("cert_file") != s["cert_file"] or
            self.original_settings.get("use_proxy") != s["use_proxy"] or
            self.original_settings.get("proxy") != s["proxy"] or
            self.original_settings.get("finnhub_api_key") != s["finnhub_api_key"] or
            self.original_settings.get("finnhub_api_key_2") != s["finnhub_api_key_2"]
        )
        
        app = QtWidgets.QApplication.instance()
        for widget in app.topLevelWidgets():
            if isinstance(widget, TickerWindow):
                if major_changes:
                    # Signal that ticker needs to be restarted
                    self.needs_restart = True
                else:
                    # Apply simple changes without restart
                    if self.original_settings.get("update_interval") != s["update_interval"]:
                        widget.apply_update_interval()
                    if self.original_settings.get("speed") != s["speed"]:
                        widget.apply_speed()
                    if self.original_settings.get("transparency") != s["transparency"]:
                        widget.apply_transparency()
                    if self.original_settings.get("play_sound_on_update") != s["play_sound_on_update"]:
                        pass  # Sound setting doesn't need immediate action
                    if self.original_settings.get("global_text_glow") != s["global_text_glow"]:
                        # Rebuild ticker text with new glow setting
                        widget.build_ticker_text(reset_scroll=False)
        
        # Set flag to indicate if restart is needed
        if not hasattr(self, 'needs_restart'):
            self.needs_restart = False
        
        super().accept()

class PriceFetchWorker(QtCore.QThread):
    prices_fetched = QtCore.pyqtSignal(dict)
    def __init__(self, tickers, api_key, api_key_2=None):
        super().__init__()
        self.tickers = tickers
        self.api_key = api_key
        self.api_key_2 = api_key_2
    def run(self):
        prices = fetch_all_stock_prices(self.tickers, self.api_key, self.api_key_2)
        self.prices_fetched.emit(prices)

class TickerGLWidget(QtWidgets.QOpenGLWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.ticker_window = parent
        self.setMouseTracking(True)
    def paintEvent(self, event):
        self.ticker_window.paint_ticker(self)
    def mousePressEvent(self, event):
        self.ticker_window.ticker_mousePressEvent(event)
    def enterEvent(self, event):
        self.ticker_window.enterEvent(event)
    def leaveEvent(self, event):
        self.ticker_window.leaveEvent(event)
        self.unsetCursor()
    def mouseMoveEvent(self, event):
        pos = event.pos()
        for _, _, rect in self.ticker_window.ticker_click_areas:
            if rect.contains(pos):
                self.setCursor(QtCore.Qt.PointingHandCursor)
                break
        else:
            self.unsetCursor()

class TrayIcon(QtWidgets.QSystemTrayIcon):
    def __init__(self, parent, ticker_window):
        icon_path = os.path.join(os.path.dirname(__file__), "TCKR.ico")
        icon = QtGui.QIcon(icon_path) if os.path.exists(icon_path) else parent.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon)
        super().__init__(icon, parent)
        self.ticker_window = ticker_window

        menu = QtWidgets.QMenu()
        self.settings_action = menu.addAction("Settings...")
        self.stocks_action = menu.addAction("Manage Stocks...")
        menu.addSeparator()
        self.about_action = menu.addAction("About...")
        menu.addSeparator()
        self.exit_action = menu.addAction("Exit")

        self.setContextMenu(menu)
        self.settings_action.triggered.connect(self.show_settings)
        self.stocks_action.triggered.connect(self.show_manage_stocks)
        self.about_action.triggered.connect(self.show_about)
        self.exit_action.triggered.connect(self.safe_exit)
        self.activated.connect(self.on_activated)

    def show_settings(self):
        dlg = SettingsDialog()
        if dlg.exec_():
            # Only restart ticker if major changes were made
            if getattr(dlg, 'needs_restart', False):
                old_window = self.ticker_window
                parent = old_window.parent()
                
                # Properly cleanup the old window's appbar reservation
                if sys.platform == "win32":
                    old_window.hide()  # Hide first
                    remove_appbar(int(old_window.winId()))
                    # Give Windows time to process the appbar removal
                    QtCore.QTimer.singleShot(300, lambda: self._create_new_window_after_cleanup(old_window))
                else:
                    old_window.close()
                    self._create_new_window_immediately()
            # If no major changes, the settings were already applied directly to the existing window

    def _create_new_window_after_cleanup(self, old_window):
        """Create new window after ensuring old appbar is properly cleaned up"""
        old_window.close()
        self._create_new_window_immediately()

    def _create_new_window_immediately(self):
        """Create and configure the new ticker window"""
        new_window = TickerWindow()
        new_window.set_transparency(get_settings().get("transparency", 100))
        new_window.scroll_speed = get_settings().get("speed", 2)
        new_window.ticker_height = get_settings().get("ticker_height", 60)
        new_window.setFixedHeight(new_window.ticker_height)
        new_window.update_font_and_label()
        new_window.build_ticker_pixmaps()
        new_window.gl_widget.setGeometry(0, 0, new_window.width(), new_window.ticker_height)
        new_window.gl_widget.update()
        new_window.update_timer.setInterval(get_settings().get("update_interval", 300) * 1000)
        
        # Ensure new window is positioned at the top after creation
        if sys.platform == "win32":
            QtCore.QTimer.singleShot(200, new_window.ensure_top_position)
        
        self.ticker_window = new_window
        self.ticker_window.tray_icon = self

    def show_manage_stocks(self):
        dlg = ManageStocksDialog(self.ticker_window)
        if dlg.exec_():
            self.ticker_window.update_prices()

    def show_about(self):
        about_html = (
            "<b>TCKR</b><br>"
            "Version 0.99<br><br>"
            "A simple and powerful scrolling LED stock ticker application.<br><br>"
            "© 2025 Paul R. Charovkine. All rights reserved.<br>"
            "Licensed under the AGPL-3.0 license.<br><br>"
            'Visit our website: <a href="https://github.com/krypdoh/TCKR">https://github.com/krypdoh/TCKR</a><br><br>'
            "Financial data thanks to<br>"
            '<a href="https://finnhub.io">https://finnhub.io</a><br>'
            '<a href="https://coingecko.com">https://coingecko.com</a>'
        )
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("About TCKR")
        msg.setTextFormat(QtCore.Qt.RichText)
        msg.setText(about_html)
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        msg.exec_()

    def safe_exit(self):
        """Safely exit the application with proper AppBar cleanup"""
        print("[EXIT] Safe exit initiated - cleaning up AppBar registration")
        
        # Ensure the ticker window closes properly, which triggers AppBar cleanup
        if hasattr(self, 'ticker_window') and self.ticker_window:
            # Close the ticker window, which will call closeEvent and clean up AppBar
            self.ticker_window.close()
            
            # Give Windows a moment to process the AppBar removal
            # Use a timer to delay the actual quit to ensure cleanup completes
            QtCore.QTimer.singleShot(100, self.delayed_quit)
        else:
            # No ticker window, just quit directly
            QtWidgets.qApp.quit()
    
    def delayed_quit(self):
        """Complete the application exit after AppBar cleanup"""
        print("[EXIT] AppBar cleanup completed, exiting application")
        QtWidgets.qApp.quit()

    def on_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            self.ticker_window.showNormal()
            self.ticker_window.raise_()
            self.ticker_window.activateWindow()

class TickerWindow(QtWidgets.QWidget):
    FLASH_DURATION_MS = 400
    _instance_counter = 0  # Class variable to track instance numbers
    
    def __init__(self):
        super().__init__()
        
        # Assign unique instance ID and set window title for identification
        TickerWindow._instance_counter += 1
        self.instance_id = TickerWindow._instance_counter
        self.setWindowTitle(f"TCKR-{self.instance_id}")
        print(f"[INIT] Creating ticker instance #{self.instance_id}")
        
        # Track when we last set the work area to ignore feedback notifications
        self._last_work_area_set_time = 0
        
        self.setContentsMargins(0, 0, 0, 0)
        self.ticker_height = get_settings().get("ticker_height", 60)
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint  # Keep on top to prevent overlap
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedHeight(self.ticker_height)
        self.icon_cache = {}
        self.update_font_and_label()
        self.stocks = [s[0] for s in load_stocks()]
        self.prices = {}
        self.prev_prices = {}
        self.price_flash_times = {}
        self.pulse_effects = {}
        self.glow_baseline_prices = {}  # Track the price that triggered each glow
        self.glow_history = {}  # Track prev_close values that already triggered glows
        self.ticker_text = ""
        self.offset = 0
        self.scroll_speed = max(1, get_settings().get("speed", 1))
        self.update_interval = get_settings().get("update_interval", 300) * 1000  # seconds to ms
        self.timer_interval = 16  # Back to 16ms (60 FPS) now that stuttering is fixed
        self.ticker_pixmaps = []
        self.ticker_pixmap_widths = []
        self.gl_widget = TickerGLWidget(self)
        self.gl_widget.setGeometry(0, 0, self.width(), self.ticker_height)
        self.gl_widget.show()
        self.timer = QtCore.QTimer(self)
        self.timer.setTimerType(QtCore.Qt.PreciseTimer)
        self.timer.timeout.connect(self.gl_widget.update)
        self.timer.start(self.timer_interval)
        self.update_timer = QtCore.QTimer(self)
        self.update_timer.timeout.connect(self.update_prices_inplace)
        self.update_timer.start(self.update_interval)
        
        # Market status update timer - check every minute for market open/close changes
        self.market_status_timer = QtCore.QTimer(self)
        self.market_status_timer.timeout.connect(self.update_market_status)
        self.market_status_timer.start(60000)  # Check every 60 seconds
        
        # DISABLED: Glow cleanup timer was causing scroll stuttering every second
        # Glow effects will now persist until next price update (every 5 minutes)
        # This eliminates the periodic pixmap rebuilds that caused stuttering
        # self.glow_cleanup_timer = QtCore.QTimer(self)
        # self.glow_cleanup_timer.timeout.connect(self.cleanup_expired_glow_effects)
        # self.glow_cleanup_timer.start(1000)
        
        # Show "TCKR: Loading" until first API batch completes
        self.loading = True
        
        self.sound_effect = QSoundEffect()
        self.sound_effect.setVolume(0.5)
        self.set_sound_file()
        
        # Monitor screen changes and reposition if necessary
        if sys.platform == "win32":
            app = QtWidgets.QApplication.instance()
            app.screenAdded.connect(self.on_screen_changed)
            app.screenRemoved.connect(self.on_screen_changed)
            app.primaryScreenChanged.connect(self.on_screen_changed)
        
        # Show window immediately with loading screen
        if sys.platform == "win32":
            # Position window at top of screen before showing
            screen_index = get_settings().get("screen_index", 0)
            app = QtWidgets.QApplication.instance()
            screens = app.screens()
            print(f"[INIT] Total screens available: {len(screens)}, requested screen_index: {screen_index}")
            if 0 <= screen_index < len(screens):
                screen = screens[screen_index]
                print(f"[INIT] Using screen at index {screen_index}")
            else:
                screen = app.primaryScreen()
                print(f"[INIT] Screen index out of range, using primary screen")
            
            rect = screen.geometry()
            print(f"[INIT] Screen geometry: left={rect.left()}, top={rect.top()}, width={rect.width()}, height={rect.height()}")
            
            # Also check available geometry (excludes taskbars, etc.)
            avail_rect = screen.availableGeometry()
            print(f"[INIT] Available geometry: left={avail_rect.left()}, top={avail_rect.top()}, width={avail_rect.width()}, height={avail_rect.height()}")
            
            print(f"[INIT] Setting window geometry to: x={rect.left()}, y={rect.top()}, width={rect.width()}, height={self.ticker_height}")
            
            # Use setGeometry to set position and size together - more reliable than separate move/resize
            self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
            
            # Verify geometry after setGeometry
            geom = self.geometry()
            print(f"[INIT] Window geometry after setGeometry(): x={geom.x()}, y={geom.y()}, width={geom.width()}, height={geom.height()}")
            
            # CRITICAL: Check for other tickers BEFORE showing this window
            # This prevents the brief moment where both tickers are at y=0 causing Windows to reposition things
            print(f"[INIT] Checking for other tickers before showing window...")
            
            # Small delay to let any existing tickers fully initialize
            import time
            time.sleep(0.1)
            
            self.check_for_other_tickers_early()
            
            # If we detected we're secondary, position ourselves correctly BEFORE showing
            if hasattr(self, 'is_secondary_ticker') and self.is_secondary_ticker and hasattr(self, 'target_position_y'):
                print(f"[INIT] Detected as secondary ticker - positioning at y={self.target_position_y} before show")
                self.setGeometry(rect.left(), self.target_position_y, rect.width(), self.ticker_height)
            
            # Show immediately with loading screen
            self.show()
            
            # Set extended window style to ensure proper behavior as an AppBar/toolbar
            # This helps prevent other windows from displacing us
            if sys.platform == "win32":
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                GWL_EXSTYLE = -20
                WS_EX_TOOLWINDOW = 0x00000080  # Exclude from taskbar
                WS_EX_TOPMOST = 0x00000008     # Always on top
                WS_EX_NOACTIVATE = 0x08000000  # Don't activate when clicked
                
                # Get current extended style
                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                
                # Add our desired styles
                new_ex_style = ex_style | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
                
                # Set the new extended style
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
                print(f"[INIT] Set extended window style: 0x{new_ex_style:08X}")
            
            # Force position again after show - sometimes Qt repositions on show()
            self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
            
            # Verify position after show
            pos = self.pos()
            geom = self.geometry()
            print(f"[INIT] Window position after show(): x={pos.x()}, y={pos.y()}")
            print(f"[INIT] Window geometry after show(): x={geom.x()}, y={geom.y()}, width={geom.width()}, height={geom.height()}")
            
            print("[TCKR] Initialized - Starting price updates")  # Single startup message
            
            # Setup AppBar after showing - this allows coordinate_with_other_tickers to find existing windows
            QtCore.QTimer.singleShot(100, self.setup_appbar_and_position)
            
            # Set up periodic position check to ensure we stay at top
            # Increased from 5s to 60s to minimize scroll stuttering from Windows API calls
            # Temporarily disabled to test if it's causing stuttering
            # self.position_check_timer = QtCore.QTimer(self)
            # self.position_check_timer.timeout.connect(self.check_and_fix_position)
            # self.position_check_timer.start(60000)  # Check every 60 seconds (reduced frequency to minimize stuttering)
        else:
            # On non-Windows platforms, show immediately
            self.show()
        
        # Start fetching real prices in the background AFTER showing the ticker
        QtCore.QTimer.singleShot(500, self.update_prices_full)
        self.failed_fetch_counts = {}
        


    def ensure_top_position(self):
        """Ensure the ticker is positioned at the very top of the selected screen"""
        screen_index = get_settings().get("screen_index", 0)
        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        if 0 <= screen_index < len(screens):
            screen = screens[screen_index]
        else:
            screen = app.primaryScreen()
        rect = screen.geometry()
        
        # Force position to the very top of the screen
        self.move(rect.left(), rect.top())
        self.resize(rect.width(), self.ticker_height)
        
        # Use aggressive positioning on Windows if other apps are docked
        if sys.platform == "win32":
            final_top = force_window_to_top(int(self.winId()), rect, self.ticker_height)
            print(f"[ENSURE TOP] Target: {rect.top()}, Final: {final_top}")
            
            # If still not at top, try multiple times
            if final_top > rect.top():
                for i in range(3):
                    QtCore.QTimer.singleShot(50 * (i + 1), lambda: self.move(rect.left(), rect.top()))

    def on_screen_changed(self, screen=None):
        """Handle screen configuration changes (monitors added/removed/changed)"""
        print(f"[SCREEN CHANGE] Screen configuration changed, repositioning ticker")
        
        # Remove current appbar registration first
        if sys.platform == "win32":
            remove_appbar(int(self.winId()))
        
        # Wait for system to stabilize, then reposition
        QtCore.QTimer.singleShot(1500, self.setup_appbar_and_position)

    def check_for_other_tickers_early(self):
        """Check for other ticker windows before showing - sets flags for positioning"""
        if sys.platform != "win32":
            return
            
        try:
            user32 = ctypes.windll.user32
            ticker_windows = []
            
            # Get our window handle and title
            my_hwnd = int(self.winId())
            my_title = self.windowTitle()
            
            def enum_callback(hwnd, lParam):
                try:
                    # Skip our own window
                    if hwnd == my_hwnd:
                        return True
                    
                    # Get window title
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        
                        # Skip if it's our own window by title
                        if title == my_title:
                            return True
                        
                        # Check if it's a ticker window
                        # Be VERY strict - only match our exact window title pattern
                        # Don't match File Explorer, Firefox tabs, etc. that might contain "TCKR" in the path
                        is_ticker = (
                            title == "TCKR" or 
                            (title.startswith("TCKR-") and title[5:].isdigit())  # TCKR-1, TCKR-2, etc.
                        )
                        
                        if is_ticker:
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            window_height = rect.bottom - rect.top
                            
                            # CRITICAL: Filter out hidden/minimized windows
                            # Windows uses negative values (like -32000) for hidden windows
                            # Only consider windows that are actually visible on screen
                            if rect.top >= 0 and rect.top < 500 and 30 <= window_height <= 150:
                                # Also check if window is visible
                                if user32.IsWindowVisible(hwnd):
                                    ticker_windows.append({
                                    'hwnd': hwnd,
                                    'title': title,
                                    'top': rect.top,
                                    'height': window_height
                                })
                                print(f"[INIT] Found existing ticker: '{title}' at y={rect.top}, height={window_height}")
                except:
                    pass
                return True
            
            # Enumerate all windows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
            
            if ticker_windows:
                # Found other tickers - we're secondary
                print(f"[INIT] Found {len(ticker_windows)} existing ticker(s) - will be secondary")
                ticker_windows.sort(key=lambda x: x['top'])
                last_ticker = ticker_windows[-1]
                
                self.is_secondary_ticker = True
                self.target_position_y = last_ticker['top'] + last_ticker['height']
                print(f"[INIT] Will position at y={self.target_position_y}")
            else:
                # No other tickers - we're primary
                print(f"[INIT] No existing tickers found - will be primary")
                self.is_secondary_ticker = False
                
        except Exception as e:
            print(f"[INIT] Error checking for other tickers: {e}")
            self.is_secondary_ticker = False

    def coordinate_with_other_tickers(self):
        """Check for other ticker windows and coordinate positioning to prevent gaps
        Returns True if other tickers were found (indicating we should NOT register as appbar)
        """
        if sys.platform != "win32":
            return False
            
        try:
            user32 = ctypes.windll.user32
            ticker_windows = []
            
            def enum_callback(hwnd, lParam):
                try:
                    # Skip our own window - check BEFORE getting title
                    my_hwnd = int(self.winId())
                    if hwnd == my_hwnd:
                        return True  # Skip ourselves
                    
                    # Get window title to identify ticker windows
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title = buff.value
                        
                        # Be VERY specific about what constitutes a ticker window
                        # Must be EXACTLY "TCKR" or "TCKR-<number>" format
                        # This prevents matching File Explorer, Firefox tabs, etc. that might have "TCKR" in the path
                        is_ticker = (
                            title == "TCKR" or 
                            (title.startswith("TCKR-") and len(title) > 5 and title[5:].isdigit())
                        )
                        
                        if is_ticker:
                            # Double-check it's not our own window by title
                            my_title = self.windowTitle()
                            if title == my_title:
                                print(f"[COORDINATE] Skipping own window: '{title}' (hwnd={hwnd})")
                                return True
                            
                            # Get window position
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            
                            # Additional validation: ticker windows should be at the top of screen
                            # and have a height close to our ticker height (within reasonable range)
                            window_height = rect.bottom - rect.top
                            
                            # CRITICAL: Filter out hidden/minimized windows
                            # Windows uses negative values (like -32000) for hidden windows
                            # Only consider windows that are actually visible on screen
                            if rect.top >= 0 and rect.top < 500 and 30 <= window_height <= 150:
                                # Also check if window is visible
                                if user32.IsWindowVisible(hwnd):
                                    ticker_windows.append({
                                        'hwnd': hwnd,
                                        'title': title,
                                        'top': rect.top,
                                        'height': window_height
                                    })
                                    print(f"[COORDINATE] Found valid ticker: '{title}' at y={rect.top}, height={window_height}")
                                else:
                                    print(f"[COORDINATE] Rejected '{title}' - window not visible")
                            else:
                                print(f"[COORDINATE] Rejected '{title}' - wrong position/size: y={rect.top}, height={window_height}")
                except:
                    pass
                return True
            
            # Enumerate all windows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
            
            print(f"[COORDINATE] Enumeration complete. Found {len(ticker_windows)} valid ticker windows")
            
            if ticker_windows:
                print(f"[COORDINATE] Found {len(ticker_windows)} other ticker window(s)")
                # If there are other tickers, we should position ourselves right after the last one
                # Sort by top position
                ticker_windows.sort(key=lambda x: x['top'])
                last_ticker = ticker_windows[-1]
                
                # Get screen geometry for positioning
                screen_index = get_settings().get("screen_index", 0)
                app = QtWidgets.QApplication.instance()
                screens = app.screens()
                if 0 <= screen_index < len(screens):
                    screen = screens[screen_index]
                else:
                    screen = app.primaryScreen()
                screen_rect = screen.geometry()
                
                # Calculate where we should be positioned
                # Position right after the last ticker (adding heights together from screen top)
                new_top = last_ticker['top'] + last_ticker['height']
                print(f"[COORDINATE] Last ticker at y={last_ticker['top']}, height={last_ticker['height']}")
                print(f"[COORDINATE] Positioning this ticker at y={new_top}")
                
                # IMPORTANT: Store the target position for use in setup_appbar_and_position
                self.target_position_y = new_top
                
                # Move to the calculated position immediately
                self.move(screen_rect.left(), new_top)
                
                # Store that we're a secondary ticker
                self.is_secondary_ticker = True
                return True  # Found other tickers
            
            # No other tickers found - we're the primary
            self.is_secondary_ticker = False
            return False
            
        except Exception as e:
            print(f"[COORDINATE] Error coordinating with other tickers: {e}")
            self.is_secondary_ticker = False
            return False

    def check_and_fix_position(self):
        """Periodically check if ticker is still at the top and fix if needed"""
        if sys.platform != "win32":
            return
            
        screen_index = get_settings().get("screen_index", 0)
        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        if 0 <= screen_index < len(screens):
            screen = screens[screen_index]
        else:
            screen = app.primaryScreen()
        rect = screen.geometry()
        
        # Check if window is still at the expected position
        current_pos = self.pos()
        expected_top = rect.top()
        
        # If window has drifted from the top, fix it
        if current_pos.y() > expected_top + 5:  # Allow 5px tolerance
            print(f"[POSITION FIX] Window drifted to {current_pos.y()}, fixing to {expected_top}")
            self.move(rect.left(), expected_top)
            
            # If it keeps drifting, use aggressive positioning
            QtCore.QTimer.singleShot(100, lambda: force_window_to_top(int(self.winId()), rect, self.ticker_height))

    def apply_update_interval(self):
        interval_sec = get_settings().get("update_interval", 300)
        if self.update_timer.isActive():
            self.update_timer.stop()
        self.update_timer.setInterval(interval_sec * 1000)
        self.update_timer.start()
    
    def apply_speed(self):
        """Apply new scroll speed setting without restarting ticker"""
        self.scroll_speed = max(1, get_settings().get("speed", 1))
    
    def apply_transparency(self):
        """Apply new transparency setting without restarting ticker"""
        self.set_transparency(get_settings().get("transparency", 100))

    def setup_appbar_and_position(self):
        """Setup appbar and position window at top of selected screen"""
        print(f"[SETUP] setup_appbar_and_position called for instance #{self.instance_id}")
        
        # Check current position before any changes
        current_pos = self.pos()
        print(f"[SETUP] Current window position at start: x={current_pos.x()}, y={current_pos.y()}")
        
        screen_index = get_settings().get("screen_index", 0)
        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        if 0 <= screen_index < len(screens):
            screen = screens[screen_index]
        else:
            screen = app.primaryScreen()
        rect = screen.geometry()
        
        print(f"[SETUP] Target screen: left={rect.left()}, top={rect.top()}, width={rect.width()}, height={rect.height()}")

        # Check if there are other ticker windows FIRST
        print(f"[SETUP] Checking for other ticker windows...")
        has_other_tickers = self.coordinate_with_other_tickers()
        
        # If we're a secondary ticker, skip ALL appbar operations
        if hasattr(self, 'is_secondary_ticker') and self.is_secondary_ticker:
            print(f"[APPBAR] Instance #{self.instance_id} is SECONDARY - no appbar operations")
            
            # Just ensure correct positioning (below other tickers)
            if hasattr(self, 'target_position_y'):
                self.setGeometry(rect.left(), self.target_position_y, rect.width(), self.ticker_height)
                print(f"[APPBAR] Secondary ticker positioned at y={self.target_position_y}")
            return  # Exit early - no appbar operations for secondary tickers

        # Only reach here if we're the PRIMARY ticker
        print(f"[APPBAR] Instance #{self.instance_id} is PRIMARY - setting up appbar")
        
        # Check if space is already reserved at the top (from a previous ticker)
        user32 = ctypes.windll.user32
        work_area = wintypes.RECT()
        user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0)  # SPI_GETWORKAREA
        existing_reservation = work_area.top - rect.top()
        
        if existing_reservation > 0:
            print(f"[APPBAR] Space already reserved at top ({existing_reservation}px)")
            
            # CRITICAL: Get our actual physical window height for slot calculation
            # We need to use physical pixels, not logical pixels
            hwnd = int(self.winId())
            actual_window_rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(actual_window_rect))
            actual_window_height = actual_window_rect.bottom - actual_window_rect.top
            print(f"[APPBAR] Our window: logical height={self.ticker_height}px, physical height={actual_window_height}px")
            
            # Calculate which slot we should be in using PHYSICAL height
            num_existing_slots = existing_reservation // actual_window_height
            print(f"[APPBAR] Existing slots: {num_existing_slots} (using physical height {actual_window_height}px)")
            
            # We should be in the next slot
            our_slot = num_existing_slots
            target_y_physical = rect.top() + (our_slot * actual_window_height)
            
            # Convert physical pixels back to logical pixels for Qt
            # The ratio is: actual_window_height (physical) / self.ticker_height (logical)
            scale_factor = actual_window_height / self.ticker_height if self.ticker_height > 0 else 2.0
            target_y_logical = target_y_physical / scale_factor
            
            print(f"[APPBAR] We are ticker #{our_slot + 1}, positioning at y={target_y_physical}px (physical) = {target_y_logical}px (logical)")
            
            # Position ourselves at the correct slot using LOGICAL pixels for Qt
            self.setGeometry(rect.left(), int(target_y_logical), rect.width(), self.ticker_height)
            
            # Mark as secondary (no AppBar registration to avoid conflicts)
            self.is_secondary_ticker = True
            self.target_position_y = int(target_y_logical)
            
            print(f"[APPBAR] Secondary ticker positioned at y={target_y_logical} (no AppBar registration)")
            print(f"[APPBAR] NOTE: This ticker will not reserve screen space - only primary ticker reserves space")
            
            # Keep our position stable
            def check_position():
                pos = self.pos()
                if pos.y() != int(target_y_logical):
                    print(f"[APPBAR] Position drifted to y={pos.y()}, fixing to y={int(target_y_logical)}")
                    self.setGeometry(rect.left(), int(target_y_logical), rect.width(), self.ticker_height)
            
            QtCore.QTimer.singleShot(200, check_position)
            QtCore.QTimer.singleShot(500, check_position)
            QtCore.QTimer.singleShot(1000, check_position)
            return  # Exit - we've handled this case
        
        print(f"[APPBAR] No existing reservation found - will register new AppBar")
        
        # Remove any previous appbar registration for THIS window only
        remove_appbar(int(self.winId()))

        def after_removal():
            """Called after appbar removal to ensure cleanup is complete"""
            def setup_new_appbar():
                """Setup the new appbar and position window - PRIMARY TICKER ONLY"""
                
                # Position window at the very top of the selected screen
                print(f"[SETUP] PRIMARY ticker - moving to top: x={rect.left()}, y={rect.top()}")
                self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
                
                # Verify position after move
                pos = self.pos()
                print(f"[SETUP] Position after move: x={pos.x()}, y={pos.y()}")
                
                # Use logical height for appbar reservation to prevent over-reserving space
                # The DPI-scaled physical height was causing too much space reservation
                # leading to gaps between multiple ticker instances
                
                print(f"[APPBAR] Registering PRIMARY ticker as appbar: height={self.ticker_height}, screen={rect}")
                actual_top = set_appbar(int(self.winId()), self.ticker_height, rect)
                
                # Mark the time we set the work area to ignore feedback notifications
                import time as time_module
                self._last_work_area_set_time = time_module.time()
                print(f"[APPBAR] Work area set time recorded: {self._last_work_area_set_time}")
                
                print(f"[APPBAR] set_appbar returned actual_top={actual_top}")
                
                # Check position after appbar registration
                pos = self.pos()
                print(f"[APPBAR] Position after set_appbar: x={pos.x()}, y={pos.y()}")
                
                # CRITICAL FIX: After appbar registration, Windows may have moved our window
                # Force it back to the absolute top (inside the reserved space, not below it)
                print(f"[APPBAR] Forcing position back to absolute top: y={rect.top()}")
                self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
                
                # Verify the position was set
                pos = self.pos()
                print(f"[APPBAR] Position after force-positioning: x={pos.x()}, y={pos.y()}")
                
                # If still not at top, keep trying
                if pos.y() != rect.top():
                    print(f"[APPBAR] WARNING: Window not at top (y={pos.y()}), forcing again...")
                    for attempt in range(5):
                        self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
                        QtCore.QCoreApplication.processEvents()  # Let Qt process the move
                        pos = self.pos()
                        print(f"[APPBAR] Attempt {attempt+1}: Position is now y={pos.y()}")
                        if pos.y() == rect.top():
                            break
                        time.sleep(0.05)
                
                # Window stays visible throughout
                
                # Force window to absolute top using Windows API too
                print(f"[APPBAR] Calling force_window_to_top...")
                final_top = force_window_to_top(int(self.winId()), rect, self.ticker_height)
                
                print(f"[POSITIONING] Screen top: {rect.top()}, AppBar assigned: {actual_top}, Final position: {final_top}")
                
                # Check position after force_window_to_top
                pos = self.pos()
                print(f"[POSITIONING] Position after force_window_to_top: x={pos.x()}, y={pos.y()}")
                
                # LAST RESORT: If STILL not at top, use direct Windows API
                if pos.y() != rect.top():
                    print(f"[POSITIONING] STILL not at top! Using aggressive Windows API positioning...")
                    user32 = ctypes.windll.user32
                    HWND_TOPMOST = -1
                    SWP_SHOWWINDOW = 0x0040
                    
                    for attempt in range(10):
                        user32.SetWindowPos(int(self.winId()), HWND_TOPMOST, 
                                          rect.left(), rect.top(), 
                                          rect.width(), self.ticker_height, 
                                          SWP_SHOWWINDOW)
                        time.sleep(0.05)
                        
                        # Check if it worked
                        window_rect = wintypes.RECT()
                        user32.GetWindowRect(int(self.winId()), ctypes.byref(window_rect))
                        print(f"[POSITIONING] Aggressive attempt {attempt+1}: Window at y={window_rect.top}")
                        if window_rect.top == rect.top():
                            print(f"[POSITIONING] SUCCESS at attempt {attempt+1}")
                            break
                
                # Diagnose AppBar state to verify space reservation - use logical height
                reserved_space = diagnose_appbar_state(int(self.winId()), self.ticker_height)
                
                # CRITICAL FIX: After AppBar registration and broadcasts, Windows may reposition
                # our window to be BELOW the reserved space instead of IN it
                # Schedule aggressive repositioning after everything settles
                def final_position_fix():
                    print(f"[FINAL FIX] Checking final position...")
                    pos = self.pos()
                    print(f"[FINAL FIX] Current position: y={pos.y()}, expected: y={rect.top()}")
                    
                    if pos.y() != rect.top():
                        print(f"[FINAL FIX] Window at wrong position! Forcing to y={rect.top()}")
                        
                        # Use both Qt and Windows API to force position
                        self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
                        
                        user32 = ctypes.windll.user32
                        HWND_TOPMOST = -1
                        SWP_SHOWWINDOW = 0x0040
                        user32.SetWindowPos(int(self.winId()), HWND_TOPMOST, 
                                          rect.left(), rect.top(), 
                                          rect.width(), self.ticker_height, 
                                          SWP_SHOWWINDOW)
                        
                        # Verify it worked
                        QtCore.QCoreApplication.processEvents()
                        pos = self.pos()
                        print(f"[FINAL FIX] Position after fix: y={pos.y()}")
                        
                        # If still wrong, keep trying
                        if pos.y() != rect.top():
                            print(f"[FINAL FIX] Still wrong, scheduling another attempt...")
                            QtCore.QTimer.singleShot(100, final_position_fix)
                    else:
                        print(f"[FINAL FIX] Position correct at y={rect.top()} ✓")
                
                # Check position after delays to let Windows settle
                QtCore.QTimer.singleShot(200, final_position_fix)
                QtCore.QTimer.singleShot(500, final_position_fix)
                QtCore.QTimer.singleShot(1000, final_position_fix)
                
                # If AppBar didn't reserve proper space, try manual work area adjustment
                if reserved_space < self.ticker_height:
                    print(f"[APPBAR] WARNING: Only {reserved_space}px reserved, expected {self.ticker_height}px")
                    print(f"[APPBAR] Attempting manual work area adjustment...")
                    
                    # Get current screen geometry
                    user32 = ctypes.windll.user32
                    work_area = wintypes.RECT()
                    work_area.left = rect.left()
                    work_area.top = rect.top() + self.ticker_height  # Reserve space for ticker
                    work_area.right = rect.right()
                    work_area.bottom = rect.bottom()
                    
                    # Try to set work area manually
                    SPI_SETWORKAREA = 47
                    SPIF_SENDCHANGE = 0x0002
                    result = user32.SystemParametersInfoW(SPI_SETWORKAREA, 0, 
                                                         ctypes.byref(work_area), 
                                                         SPIF_SENDCHANGE)
                    print(f"[APPBAR] Manual work area adjustment result: {result}")
                    
                    # Re-diagnose after manual adjustment
                    time.sleep(0.2)
                    diagnose_appbar_state(int(self.winId()), self.ticker_height)
                
                # DISABLED: Retry mechanism was causing problems when multiple tickers launched
                # The verify_and_fix callbacks would re-register appbar and cause position issues
                # def verify_and_fix():
                #     actual_pos = self.pos()
                #     if actual_pos.y() > rect.top():
                #         print(f"[POSITIONING] Window drifted to {actual_pos.y()}, forcing back to {rect.top()}")
                #         self.move(rect.left(), rect.top())
                #         # Re-register appbar to ensure space is reserved - use logical height
                #         set_appbar(int(self.winId()), self.ticker_height, rect)
                #         # Re-diagnose after fix
                #         diagnose_appbar_state(int(self.winId()), self.ticker_height)
                
                # Multiple verification passes to ensure proper positioning
                # QtCore.QTimer.singleShot(100, verify_and_fix)
                # QtCore.QTimer.singleShot(500, verify_and_fix)
                # QtCore.QTimer.singleShot(1000, verify_and_fix)
                
            QtCore.QTimer.singleShot(250, setup_new_appbar)
        QtCore.QTimer.singleShot(300, after_removal)

    def set_sound_file(self):
        sound_path = os.path.join(os.path.dirname(__file__), "notify.wav")
        if os.path.exists(sound_path):
            self.sound_effect.setSource(QtCore.QUrl.fromLocalFile(sound_path))
        else:
            self.sound_effect.setSource(QtCore.QUrl())

    def play_update_sound(self):
        print(f"[PLAY SOUND] Notify.wav")
        if get_settings().get("play_sound_on_update", True):
            if self.sound_effect.source().isEmpty():
                QtWidgets.QApplication.beep()
            else:
                self.sound_effect.play()

    def resizeEvent(self, event):
        self.gl_widget.setGeometry(0, 0, self.width(), self.ticker_height)
        super().resizeEvent(event)
    def move_to_selected_screen(self):
        """Move ticker to selected screen with proper appbar cleanup and setup"""
        screen_index = get_settings().get("screen_index", 0)
        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        if 0 <= screen_index < len(screens):
            screen = screens[screen_index]
        else:
            screen = app.primaryScreen()
        rect = screen.geometry()
        
        # If on Windows, properly handle appbar when moving between screens
        if sys.platform == "win32":
            # Remove current appbar registration
            remove_appbar(int(self.winId()))
            
            def after_cleanup():
                # Position at top of new screen
                self.move(rect.left(), rect.top())
                self.resize(rect.width(), self.ticker_height)
                
                # Re-register appbar on new screen
                actual_top = set_appbar(int(self.winId()), self.ticker_height, rect)
                
                # Force to absolute top position
                final_top = force_window_to_top(int(self.winId()), rect, self.ticker_height)
                
                print(f"[SCREEN MOVE] Target: {rect.top()}, AppBar: {actual_top}, Final: {final_top}")
                
                # Additional positioning if needed
                if final_top > rect.top():
                    QtCore.QTimer.singleShot(50, lambda: self.move(rect.left(), rect.top()))
            
            # Give Windows time to process appbar removal before setting up new one
            QtCore.QTimer.singleShot(200, after_cleanup)
        else:
            # Non-Windows platforms - simple move and resize
            self.move(rect.left(), rect.top())
            self.resize(rect.width(), self.ticker_height)
    def update_font_and_label(self, width=None):
        # Use 70% of ticker height for font, leaving padding above and below
        font_size = max(8, int(self.ticker_height * 0.7))
        font_path = resource_path("SubwayTicker.ttf")
        if os.path.exists(font_path):
            font_id = QtGui.QFontDatabase.addApplicationFont(font_path)
            families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
            if families:
                self.ticker_font = QtGui.QFont(families[0], font_size)
            else:
                self.ticker_font = QtGui.QFont("Arial", font_size)
        else:
            self.ticker_font = QtGui.QFont("Arial", font_size)
    def update_prices_full(self):
        # Keep loading screen visible while fetching first batch
        api_key = ensure_finnhub_api_key(self)
        if not api_key:
            self.loading = False
            self.gl_widget.update()
            return
        # Get second API key if configured
        api_key_2 = get_settings().get("finnhub_api_key_2", "").strip() or None
        self.worker = PriceFetchWorker(sorted([s[0] for s in load_stocks()]), api_key, api_key_2)
        self.worker.prices_fetched.connect(self.on_prices_fetched)
        self.worker.start()
    def on_prices_fetched(self, prices):
        self.stocks = sorted([s[0] for s in load_stocks()])
        self.prices = prices
        self.loading = False  # Hide loading screen, show ticker with real data
        self.build_ticker_text(reset_scroll=True)

    def cleanup_expired_glow_effects(self):
        """Clean up expired glow effects and trigger pixmap rebuild if needed"""
        if not hasattr(self, 'pulse_effects') or not self.pulse_effects:
            return
        
        current_time = time.time()
        expired_effects = []
        
        # Check for expired glow effects
        for symbol, start_time in list(self.pulse_effects.items()):
            glow_duration = 300.0  # 300 second glow duration (5 minutes)
            if current_time - start_time > glow_duration:
                expired_effects.append(symbol)
        
        # Remove expired effects and rebuild pixmaps if any were removed
        if expired_effects:
            for symbol in expired_effects:
                del self.pulse_effects[symbol]
                # Clean up baseline price tracking
                if hasattr(self, 'glow_baseline_prices') and symbol in self.glow_baseline_prices:
                    del self.glow_baseline_prices[symbol]
            print(f"[GLOW] Expired and removed effects for: {expired_effects}")
            
            # Mark these symbols as recently expired to prevent immediate re-triggering
            if not hasattr(self, 'recently_expired_effects'):
                self.recently_expired_effects = {}
            current_time = time.time()
            for symbol in expired_effects:
                self.recently_expired_effects[symbol] = current_time
            print(f"[GLOW] Marked as recently_expired: {list(self.recently_expired_effects.keys())}")
            
            # Rebuild pixmaps to remove glow effect from expired items
            self.build_ticker_pixmaps()  # Call build_ticker_pixmaps directly to avoid re-triggering
            
        # Debug: Show current active pulse effects (reduced verbosity)
        if self.pulse_effects and len(self.pulse_effects) > 0:
            current_time = time.time()
            # Only show debug every 10 seconds to reduce spam
            if not hasattr(self, 'last_debug_time') or current_time - self.last_debug_time > 10:
                self.last_debug_time = current_time
                active_effects = []
                for symbol, start_time in self.pulse_effects.items():
                    elapsed = current_time - start_time
                    active_effects.append(f"{symbol}({elapsed:.0f}s)")
                print(f"[GLOW] Active effects: {active_effects}")

    def draw_text_with_global_glow(self, painter, x, y, text, text_color, glow_color=None):
        """
        Draw text with optional global glow effect.
        If glow_color is None and global_text_glow is enabled, uses a subtle white glow.
        """
        settings = get_settings()
        
        # Apply global glow if enabled (subtle white glow for all text)
        if settings.get("global_text_glow", True) and glow_color is None:
            # Much less intense than 5% glow (alpha 15 vs 50)
            glow_color = QtGui.QColor(255, 255, 255, 15)
        
        # Draw glow halo if we have a glow color
        if glow_color:
            painter.setPen(glow_color)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:  # Don't draw at center position
                        painter.drawText(x + dx, y + dy, text)
        
        # Draw main text
        painter.setPen(text_color)
        painter.drawText(x, y, text)

    def get_glow_effect(self, symbol, change_percent):
        """Get glow effect for significant price changes"""
        if abs(change_percent) < 5:  # Only glow for changes >= 5%
            return None
        
        current_time = time.time()
        
        # Check if glow effect exists and is still active
        if symbol in self.pulse_effects:
            glow_start = self.pulse_effects[symbol]
            glow_duration = 300.0  # 300 second glow duration (5 minutes)
            elapsed = current_time - glow_start
            
            if elapsed > glow_duration:
                # Glow finished - don't delete here, let cleanup_expired_glow_effects handle it
                return None
            
            # Use constant alpha (no fade) to ensure zero scroll stuttering
            # Glow will remain at this intensity for full 120 seconds, then disappear
            glow_alpha = 50
            
            # Return glow color based on change direction
            if change_percent > 0:
                # Green glow for positive changes
                return QtGui.QColor(0, 255, 0, glow_alpha)
            else:
                # Red glow for negative changes  
                return QtGui.QColor(255, 0, 0, glow_alpha)
        
        # No active glow effect
        return None

    def test_glow_for_significant_changes(self):
        """Test method to trigger glow effects for stocks with significant changes"""
        # print("[GLOW DEBUG] Checking for stocks with significant price changes...")  # Commented for less verbose output
        for tkr in self.stocks:
            price, prev_close = self.prices.get(tkr, (None, None))
            if price is not None and prev_close is not None and prev_close != 0:
                change_percent = abs((price - prev_close) / prev_close) * 100
                # print(f"[GLOW DEBUG] {tkr}: price={price}, prev_close={prev_close}, change_percent={change_percent:.2f}%")  # Commented for less verbose output
                if change_percent >= 5.0:
                    # print(f"[GLOW DEBUG] Manually triggering glow effect for {tkr} with {change_percent:.2f}% change")  # Commented for less verbose output
                    self.pulse_effects[tkr] = time.time()
        
        if self.pulse_effects:
            self.build_ticker_text(reset_scroll=False)
        # else:
            # print("[GLOW DEBUG] No stocks found with >= 5% change to glow")  # Commented for less verbose output

    def update_prices_inplace(self):
        now = time.time()
        # print(f"[BACKOFF DEBUG] update_prices_inplace called at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}")  # Commented for less verbose output
        # print(f"[BACKOFF DEBUG] Current backoff_until: {getattr(TickerWindow, 'backoff_until', 0)}")  # Commented for less verbose output
        if hasattr(TickerWindow, 'backoff_until') and now < TickerWindow.backoff_until:
            # print(f"[BACKOFF DEBUG] Skipping fetch, backoff active until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(TickerWindow.backoff_until))}")  # Commented for less verbose output
            return

        api_key = ensure_finnhub_api_key(self)
        if not api_key:
            # print("[BACKOFF DEBUG] No API key, aborting fetch.")  # Commented for less verbose output
            return

        # Get second API key if configured
        api_key_2 = get_settings().get("finnhub_api_key_2", "").strip() or None

        # Run fetch in a worker thread to avoid blocking the UI
        def fetch_and_handle():
            tickers = self.stocks
            prices, had_429 = fetch_all_stock_prices_with_429(tickers, api_key, api_key_2)
            QtCore.QMetaObject.invokeMethod(
                self,
                "_handle_prices_inplace",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(dict, prices),
                QtCore.Q_ARG(bool, had_429),
                QtCore.Q_ARG(float, now)
            )

        # Use QThreadPool for non-blocking fetch
        class FetchRunnable(QtCore.QRunnable):
            def run(self):
                fetch_and_handle()

        QtCore.QThreadPool.globalInstance().start(FetchRunnable())

    @QtCore.pyqtSlot(dict, bool, float)
    def _handle_prices_inplace(self, prices, had_429, now):
        if had_429:
            TickerWindow.consecutive_429_cycles = getattr(TickerWindow, 'consecutive_429_cycles', 0) + 1
            # print(f"[BACKOFF DEBUG] 429 error detected. Consecutive cycles: {TickerWindow.consecutive_429_cycles}")  # Commented for less verbose output
            if TickerWindow.consecutive_429_cycles >= 2:
                TickerWindow.backoff_until = now + 300  # 5 minutes
                print(f"[BACKOFF] Two consecutive 429 errors. Backing off for 5 minutes until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(TickerWindow.backoff_until))}")
                TickerWindow.consecutive_429_cycles = 0
        else:
            # if getattr(TickerWindow, 'consecutive_429_cycles', 0) > 0 or getattr(TickerWindow, 'backoff_until', 0) > 0:
                # print("[BACKOFF DEBUG] No 429 error, resetting backoff process.")  # Commented for less verbose output
            TickerWindow.consecutive_429_cycles = 0
            TickerWindow.backoff_until = 0

        self.on_prices_inplace_fetched(prices)
    def on_prices_inplace_fetched(self, new_prices):
        now = int(time.time() * 1000)
        price_changed = False
        for tkr, (price, prev_close) in new_prices.items():
            old_price = self.prices.get(tkr, (None, None))[0]
            old_prev_close = self.prices.get(tkr, (None, None))[1]
            
            # If prev_close changed (new trading day), clear glow history for this stock
            if old_prev_close is not None and prev_close is not None and old_prev_close != prev_close:
                if tkr in self.glow_history:
                    # print(f"[GLOW] Clearing glow history for {tkr} - prev_close changed from {old_prev_close} to {prev_close} (new trading day)")  # Commented for less verbose output
                    del self.glow_history[tkr]
            
            if price is None:
                self.failed_fetch_counts[tkr] = self.failed_fetch_counts.get(tkr, 0) + 1
                if self.failed_fetch_counts[tkr] < 3 and old_price is not None:
                    price = old_price
                    prev_close = self.prices.get(tkr, (None, None))[1]
                else:
                    price = None
                    prev_close = None
            else:
                self.failed_fetch_counts[tkr] = 0
            # print(f"[DEBUG] {tkr}: old_price={old_price}, new_price={price}")  # Commented for less verbose output
            if price is not None and (old_price is None or price != old_price):
                # print(f"[DEBUG] {tkr} price changed!")  # Commented for less verbose output
                self.price_flash_times[tkr] = now
                # Start pulse effect for significant price changes
                if old_price is not None and prev_close and prev_close != 0:
                    # Only trigger glow if stock is not already glowing
                    if tkr not in self.pulse_effects:
                        # No current glow - check against prev_close
                        change_percent = abs((price - prev_close) / prev_close) * 100
                        # Check if we already showed glow for this prev_close value
                        already_glowed_for_this = (tkr in self.glow_history and 
                                                   self.glow_history[tkr] == prev_close)
                        if change_percent >= 5.0 and not already_glowed_for_this:
                            self.pulse_effects[tkr] = time.time()
                            self.glow_baseline_prices[tkr] = price
                            self.glow_history[tkr] = prev_close  # Remember this prev_close
                            # print(f"[GLOW] Started glow for {tkr} with {change_percent:.2f}% change from prev_close={prev_close}")  # Commented for less verbose output
                        # elif already_glowed_for_this:
                            # pass  # Already showed glow for this prev_close, don't repeat
                    # If already glowing, don't reset - let it run for full 120 seconds
                # elif old_price is not None:
                    # print(f"[GLOW DEBUG] {tkr}: old_price={old_price}, price={price}, prev_close={prev_close} - not triggering glow")  # Commented for less verbose output
                price_changed = True
            elif tkr in self.price_flash_times and price == old_price:
                del self.price_flash_times[tkr]
            new_prices[tkr] = (price, prev_close)
        self.prev_prices = self.prices.copy()
        self.prices = new_prices
        
        # Also check for existing significant changes (not just new price changes)
        # This runs at startup to catch stocks that already have big changes
        for tkr, (price, prev_close) in new_prices.items():
            if price is not None and prev_close is not None and prev_close != 0:
                change_percent = abs((price - prev_close) / prev_close) * 100
                # Only glow if: 1) not currently glowing, 2) meets threshold, 3) haven't glowed for this prev_close before, 4) not recently expired
                already_glowed_for_this = (tkr in self.glow_history and 
                                          self.glow_history[tkr] == prev_close)
                recently_expired = (hasattr(self, 'recently_expired_effects') and 
                                  tkr in self.recently_expired_effects)
                
                # Debug output for glow decision
                # if change_percent >= 5.0:
                #     print(f"[GLOW CHECK] {tkr}: change={change_percent:.2f}%, in_pulse={tkr in self.pulse_effects}, already_glowed={already_glowed_for_this}, recently_expired={recently_expired}")
                
                if change_percent >= 5.0 and tkr not in self.pulse_effects and not already_glowed_for_this and not recently_expired:
                    # print(f"[GLOW] Found significant change for {tkr}: {change_percent:.2f}%")
                    self.pulse_effects[tkr] = time.time()
                    self.glow_baseline_prices[tkr] = price  # Set baseline for initial glow
                    self.glow_history[tkr] = prev_close  # Remember this prev_close
        
        self.build_ticker_pixmaps()
        self.gl_widget.update()
        # print(f"[PRICE UPDATE] {self.prices}")
        if price_changed:
            # print(f"[PRICE CHANGE DETECTED]")
            self.play_update_sound()
    def set_transparency(self, percent):
        self.setWindowOpacity(percent / 100.0)
    def update_prices(self):
        api_key = ensure_finnhub_api_key(self)
        if not api_key:
            return
        # Get second API key if configured
        api_key_2 = get_settings().get("finnhub_api_key_2", "").strip() or None
        self.stocks = sorted([s[0] for s in load_stocks()])
        self.prices = fetch_all_stock_prices(self.stocks, api_key, api_key_2)
        self.build_ticker_text(reset_scroll=True)
    
    def update_market_status(self):
        """Update market status in the ticker display"""
        # Only rebuild ticker pixmaps to update market status
        # This is more efficient than rebuilding the entire ticker text
        self.build_ticker_pixmaps()
    
    def build_ticker_text(self, reset_scroll=False):
        items = []
        
        # Check for significant price changes to trigger glow effects
        if hasattr(self, 'pulse_effects'):
            current_time = time.time()
            
            # Clean up old recently expired effects (after 5 seconds)
            if hasattr(self, 'recently_expired_effects'):
                expired_to_remove = []
                for symbol, expire_time in self.recently_expired_effects.items():
                    if current_time - expire_time > 5.0:  # 5 second cooldown
                        expired_to_remove.append(symbol)
                for symbol in expired_to_remove:
                    del self.recently_expired_effects[symbol]
            
            for tkr in self.stocks:
                price, prev_close = self.prices.get(tkr, (None, None))
                if price is not None and prev_close is not None and prev_close != 0:
                    change_percent = abs((price - prev_close) / prev_close) * 100
                    
                    # Check if this effect was recently expired (prevent immediate re-triggering)
                    recently_expired = (hasattr(self, 'recently_expired_effects') and 
                                      tkr in self.recently_expired_effects)
                    
                    if (change_percent >= 5.0 and 
                        tkr not in self.pulse_effects and 
                        not recently_expired):
                        # print(f"[GLOW] Triggering glow for {tkr} with {change_percent:.2f}% change")
                        self.pulse_effects[tkr] = current_time
        
        for tkr in self.stocks:
            price, prev = self.prices.get(tkr, (None, None))
            if price is not None:
                items.append(f"{tkr}: {price:.2f}")
            else:
                items.append(f"{tkr}: N/A")
        self.ticker_text = "   ".join(items) + "   "
        metrics = QtGui.QFontMetrics(self.ticker_font)
        self.window_width = self.width()
        
        # Only reset scroll position when explicitly requested (initial load, stock list changes)
        if reset_scroll:
            self.offset = self.window_width
            
        self.build_ticker_pixmaps()
    def build_ticker_pixmaps(self):
        self.ticker_pixmaps = []
        self.ticker_pixmap_widths = []
        self.ticker_area_templates = []
        
        # Don't clear ghost_frames here - we're making deep copies so they remain valid
        
        metrics = QtGui.QFontMetrics(self.ticker_font)
        icon_size = int(self.ticker_height * 0.85)  # Icon a little larger than font size, leaves 15% padding
        small_font = QtGui.QFont(self.ticker_font)
        small_font.setPointSize(max(8, int(self.ticker_font.pointSize() * 0.5)))
        small_metrics = QtGui.QFontMetrics(small_font)
        
        # Create market status pixmap first
        market_text, market_color, status_text, status_color = get_market_status_info()
        market_full_text = f"{market_text} {status_text}"
        market_text_width = metrics.horizontalAdvance(market_text + " ")
        status_text_width = metrics.horizontalAdvance(status_text)
        sep = "      "
        sep_width = metrics.horizontalAdvance(sep)
        market_total_width = market_text_width + status_text_width + sep_width + 20
        
        market_pixmap = QtGui.QPixmap(market_total_width, self.ticker_height)
        market_pixmap.fill(QtCore.Qt.transparent)
        market_painter = QtGui.QPainter(market_pixmap)
        market_painter.setFont(self.ticker_font)
        
        # Center text vertically
        text_y = (self.ticker_height + metrics.ascent() - metrics.descent()) // 2
        x = 10  # Small left padding
        
        # Draw "Market:" in blue with glow
        self.draw_text_with_global_glow(market_painter, x, text_y, market_text, market_color)
        x += market_text_width
        
        # Draw "Open" or "Closed" with appropriate color and glow
        self.draw_text_with_global_glow(market_painter, x, text_y, status_text, status_color)
        
        market_painter.end()
        
        # Add market status pixmap to the beginning
        self.ticker_pixmaps.append(market_pixmap)
        self.ticker_pixmap_widths.append(market_total_width)
        self.ticker_area_templates.append([])  # No click areas for market status
        
        # Now build stock ticker pixmaps
        for tkr in self.stocks:
            price, prev = self.prices.get(tkr, (None, None))
            icon = get_ticker_icon(tkr, icon_size)
            tkr_width = metrics.horizontalAdvance(tkr + " ")
            price_text = f"{price:.2f}" if price is not None else "N/A"
            price_width = metrics.horizontalAdvance(price_text)
            change_text = ""
            pct_text = ""
            if price is not None and prev is not None:
                change = price - prev
                pct = (change / prev * 100) if prev else 0
                if change > 0:
                    change_text = f"+{abs(change):.2f}▲"
                    pct_text = f"+{abs(pct):.2f}%"
                elif change < 0:
                    change_text = f"-{abs(change):.2f}▼"
                    pct_text = f"-{abs(pct):.2f}%"
                else:  # change == 0
                    change_text = f"{change:.2f}→"
                    pct_text = f"{pct:.2f}%"
            change_width = max(small_metrics.horizontalAdvance(change_text), small_metrics.horizontalAdvance(pct_text)) if (change_text or pct_text) else 0
            sep = "      "
            sep_width = metrics.horizontalAdvance(sep)
            total_width = icon_size + 8 + tkr_width + price_width + (10 + change_width if change_width else 0) + sep_width + 20
            pixmap = QtGui.QPixmap(total_width, self.ticker_height)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            x = 0
            # Center icon vertically
            icon_y = (self.ticker_height - icon_size) // 2
            painter.drawPixmap(x, icon_y, icon)
            x += icon_size + 8
            # Center text vertically
            tkr_y = (self.ticker_height + metrics.ascent() - metrics.descent()) // 2
            symbol_rect = QtCore.QRect(x, 0, tkr_width, self.ticker_height)
            painter.setFont(self.ticker_font)
            self.draw_text_with_global_glow(painter, x, tkr_y, tkr, QtGui.QColor("#00B3FF"))
            x += tkr_width
            price_y = tkr_y
            if price is not None and prev is not None:
                if price > prev:
                    price_color = QtGui.QColor("#00FF40")
                elif price < prev:
                    price_color = QtGui.QColor("#FF5555")
                else:
                    price_color = QtGui.QColor("#FFFFFF")  # White for unchanged price
            else:
                price_color = QtGui.QColor("#FFD700")
            
            # Calculate change percentage for glow effect
            change_percent = 0
            if price is not None and prev is not None and prev != 0:
                change_percent = ((price - prev) / prev) * 100
            
            # Check for glow effect on big price changes
            glow_color = self.get_glow_effect(tkr, change_percent)
            
            price_rect = QtCore.QRect(x, 0, price_width, self.ticker_height)
            
            # Draw price text with appropriate glow
            painter.setFont(self.ticker_font)
            if glow_color:
                # Draw 5% glow effect (more intense, colored) - replaces global glow
                painter.setPen(glow_color)
                for dx in [-2, -1, 0, 1, 2]:
                    for dy in [-2, -1, 0, 1, 2]:
                        if dx != 0 or dy != 0:
                            painter.drawText(x + dx, price_y + dy, price_text)
                # Draw main price text without global glow (5% glow is sufficient)
                painter.setPen(price_color)
                painter.drawText(x, price_y, price_text)
            else:
                # No 5% glow, use global glow if enabled
                self.draw_text_with_global_glow(painter, x, price_y, price_text, price_color)
            x += price_width
            if change_text or pct_text:
                painter.setFont(small_font)
                stacked_height = small_metrics.height() * 2 + 2
                stacked_top = (self.ticker_height - stacked_height) // 2 + small_metrics.ascent()
                # Determine color: green for positive, red for negative, white for zero
                if change_text.startswith("+"):
                    color = QtGui.QColor("#00FF40")  # Green
                elif change_text.startswith("-"):
                    color = QtGui.QColor("#FF5555")  # Red
                else:
                    color = QtGui.QColor("#FFFFFF")  # White for zero change
                
                painter.setFont(small_font)
                
                # Apply glow effect to change text if 5% glow is active
                if glow_color:
                    painter.setPen(glow_color)
                    for dx in [-2, -1, 0, 1, 2]:
                        for dy in [-2, -1, 0, 1, 2]:
                            if dx != 0 or dy != 0:
                                painter.drawText(x + 10 + dx, stacked_top + dy, change_text)
                                painter.drawText(x + 10 + dx, stacked_top + small_metrics.height() + 2 + dy, pct_text)
                    # Draw main text without global glow (5% glow is sufficient)
                    painter.setPen(color)
                    painter.drawText(x + 10, stacked_top, change_text)
                    painter.drawText(x + 10, stacked_top + small_metrics.height() + 2, pct_text)
                else:
                    # No 5% glow, use global glow if enabled
                    self.draw_text_with_global_glow(painter, x + 10, stacked_top, change_text, color)
                    self.draw_text_with_global_glow(painter, x + 10, stacked_top + small_metrics.height() + 2, pct_text, color)
                
                painter.setFont(self.ticker_font)
                x += 10 + change_width
            painter.setFont(self.ticker_font)
            self.draw_text_with_global_glow(painter, x, tkr_y, sep, QtGui.QColor("#00B3FF"))
            painter.end()
            self.ticker_pixmaps.append(pixmap)
            self.ticker_pixmap_widths.append(total_width)
            self.ticker_area_templates.append([
                ('symbol', tkr, symbol_rect),
                ('price', tkr, price_rect)
            ])
        donate_text = "      Please Donate!          "
        rainbow_colors = [
            "#FF0000", "#FF7F00", "#FFFF00", "#00FF00", "#00B3FF", "#4B0082", "#9400D3"
        ]
        colors = [rainbow_colors[i % len(rainbow_colors)] for i in range(len(donate_text))]
        donate_font = self.ticker_font
        metrics = QtGui.QFontMetrics(donate_font)
        donate_height = self.ticker_height
        donate_pixmap_width = metrics.horizontalAdvance(donate_text) + 40
        donate_pixmap = QtGui.QPixmap(donate_pixmap_width, donate_height)
        donate_pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(donate_pixmap)
        x = 20
        donate_y = donate_height // 2 + metrics.ascent() // 2
        for i, char in enumerate(donate_text):
            color = QtGui.QColor(colors[i])
            painter.setFont(donate_font)
            
            # Draw shadow
            painter.setPen(QtGui.QColor("black"))
            painter.drawText(x + 1, donate_y + 1, char)
            
            # Draw character with global glow
            self.draw_text_with_global_glow(painter, x, donate_y, char, color)
            x += metrics.horizontalAdvance(char)
        painter.end()
        self._donate_pixmap = donate_pixmap
        self._donate_pixmap_width = donate_pixmap_width
        self._donate_area_template = [('donate', 'DONATE', QtCore.QRect(0, 0, donate_pixmap_width, donate_height))]

    def get_cycle_width(self):
        return sum(self.ticker_pixmap_widths)

    def apply_led_flicker(self, painter, width, height):
        """
        Apply realistic LED flickering effect.
        LEDs have subtle brightness variations that make them look more authentic.
        Uses time-based random variations for natural flicker patterns.
        """
        # Check if LED flicker effect is enabled in settings
        if not get_settings().get("led_flicker_effect", True):
            return  # Skip flicker effect if disabled
        
        import random
        
        # Use current time for pseudo-random but smooth flickering
        # This creates a time-varying seed that changes gradually
        current_time = time.time()
        flicker_seed = int(current_time * 60)  # Changes every ~16ms for 60fps
        random.seed(flicker_seed)
        
        # Create subtle random brightness variations across the display
        # Real LEDs have slight inconsistencies in brightness
        num_flicker_spots = 15  # Number of brightness variation areas
        
        for _ in range(num_flicker_spots):
            # Random position for flicker spot
            fx = random.randint(0, width)
            fy = random.randint(0, height)
            
            # Random size for flicker area (small spots)
            flicker_width = random.randint(20, 80)
            flicker_height = random.randint(10, 30)
            
            # Random brightness variation (very subtle)
            # Positive values = slight brightening, negative = slight dimming
            brightness_delta = random.randint(-15, 20)
            
            # Create semi-transparent overlay for flicker effect
            if brightness_delta > 0:
                # Brightening flicker (subtle white overlay)
                flicker_color = QtGui.QColor(255, 255, 255, brightness_delta)
            else:
                # Dimming flicker (subtle black overlay)
                flicker_color = QtGui.QColor(0, 0, 0, abs(brightness_delta))
            
            # Apply flicker with soft edges (ellipse for smooth transitions)
            painter.setBrush(QtGui.QBrush(flicker_color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(fx - flicker_width//2, fy - flicker_height//2, 
                              flicker_width, flicker_height)
        
        # Add occasional "power surge" flicker (rare, quick brightness spike)
        # This simulates voltage variations in LED power supply
        surge_chance = random.random()
        if surge_chance < 0.05:  # 5% chance each frame
            # Global brightness pulse
            surge_intensity = random.randint(5, 15)
            surge_color = QtGui.QColor(255, 255, 255, surge_intensity)
            painter.setBrush(QtGui.QBrush(surge_color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(0, 0, width, height)
        
        # Add subtle horizontal scan line flicker (mimics refresh rate)
        scan_y = int((current_time * 200) % height)  # Moves down slowly
        scan_color = QtGui.QColor(255, 255, 255, 8)
        painter.fillRect(0, scan_y, width, 2, scan_color)

    def apply_bloom_effect(self, painter, width, height):
        """
        Apply bloom/glow effect around bright colors.
        Simulates light emission from bright LEDs bleeding into surrounding areas.
        """
        # Check if bloom effect is enabled
        if not get_settings().get("led_bloom_effect", True):
            return
        
        # Create bloom effect around visible ticker content
        # Apply to each visible ticker element for consistent glow
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        
        # Draw bloom halos around each ticker click area (where text/icons are)
        for area_type, tkr, rect in self.ticker_click_areas:
            # Create radial gradient bloom centered on each element
            center_x = rect.center().x()
            center_y = rect.center().y()
            bloom_radius = max(rect.width(), rect.height()) * 0.8
            
            gradient = QtGui.QRadialGradient(center_x, center_y, bloom_radius)
            
            # Different bloom colors and intensity for different content
            if area_type == 'price':
                # Subtle bloom matching the price text color
                price, prev = self.prices.get(tkr, (None, None))
                if price is not None and prev is not None:
                    if price > prev:
                        bloom_color = QtGui.QColor(0, 255, 64)  # Green
                    elif price < prev:
                        bloom_color = QtGui.QColor(255, 85, 85)  # Red
                    else:
                        bloom_color = QtGui.QColor(255, 255, 255)  # White
                else:
                    bloom_color = QtGui.QColor(255, 215, 0)  # Gold for N/A
                gradient.setColorAt(0, QtGui.QColor(bloom_color.red(), bloom_color.green(), bloom_color.blue(), 33))
                gradient.setColorAt(0.5, QtGui.QColor(bloom_color.red(), bloom_color.green(), bloom_color.blue(), 13))
            elif area_type == 'symbol':
                
                gradient.setColorAt(0, QtGui.QColor(0, 179, 255, 33))
                gradient.setColorAt(0.5, QtGui.QColor(0, 179, 255, 13))
            else:
                # Minimal bloom for other elements like icons (don't obscure them)
                gradient.setColorAt(0, QtGui.QColor(200, 220, 255, 13))
                gradient.setColorAt(0.5, QtGui.QColor(200, 220, 255, 6))
            
            gradient.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
            
            painter.setBrush(QtGui.QBrush(gradient))
            painter.setPen(QtCore.Qt.NoPen)
            # Convert float values to int for drawEllipse
            painter.drawEllipse(int(center_x - bloom_radius), int(center_y - bloom_radius), 
                              int(bloom_radius * 2), int(bloom_radius * 2))
        
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

    def apply_bloom_to_rect(self, painter, rect, width, height):
        """
        Apply bloom effect to a specific rectangular area.
        Used for loading screen and other special cases.
        """
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        
        # Create radial gradient bloom centered on the rectangle
        center_x = rect.center().x()
        center_y = rect.center().y()
        bloom_radius = max(rect.width(), rect.height()) * 0.8
        
        gradient = QtGui.QRadialGradient(center_x, center_y, bloom_radius)
        gradient.setColorAt(0, QtGui.QColor(255, 255, 255, 39))
        gradient.setColorAt(0.5, QtGui.QColor(255, 255, 255, 17))
        gradient.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
        
        painter.setBrush(QtGui.QBrush(gradient))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(int(center_x - bloom_radius), int(center_y - bloom_radius), 
                          int(bloom_radius * 2), int(bloom_radius * 2))
        
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

    def apply_ghosting_effect(self, painter, width, height):
        """
        Apply motion blur/ghosting effect by drawing current content at offset positions.
        Simulates LED persistence and creates trailing effect on moving content.
        """
        # Check if ghosting effect is enabled
        if not get_settings().get("led_ghosting_effect", True):
            return
        
        # Draw ghost trails by rendering current content at offset positions
        painter.setOpacity(0.6)  # 60% opacity for more visible ghost trail
        
        base_cycle_width = self.get_cycle_width()
        donate_cycle_width = self._donate_pixmap_width + base_cycle_width

        cycle_positions = []
        # Use scroll speed to determine ghost offset (faster scrolling = more offset)
        ghost_offset = max(2, int(self.scroll_speed * 1.5))  # Minimum 2px, gentle scaling with speed
        x = self.offset + ghost_offset
        est_cycles = (width // min(base_cycle_width, donate_cycle_width)) + 6
        for i in range(est_cycles):
            if i % 3 == 0:
                cycle_positions.append((x, True))
                x += donate_cycle_width
            else:
                cycle_positions.append((x, False))
                x += base_cycle_width

        # Draw ghost content using same logic as main drawing
        for x_pos, is_donate in cycle_positions:
            draw_x = x_pos
            # Draw stock tickers first (same as main drawing)
            if hasattr(self, 'ticker_pixmaps') and hasattr(self, 'ticker_pixmap_widths'):
                for pixmap, w in zip(self.ticker_pixmaps, self.ticker_pixmap_widths):
                    if pixmap and not pixmap.isNull() and draw_x + w > 0 and draw_x < width:
                        painter.drawPixmap(draw_x, 0, pixmap)
                    draw_x += w
            # Then draw donate message at the end (if this cycle includes it)
            if is_donate and hasattr(self, '_donate_pixmap') and self._donate_pixmap and not self._donate_pixmap.isNull():
                if draw_x + self._donate_pixmap.width() > 0 and draw_x < width:
                    painter.drawPixmap(draw_x, 0, self._donate_pixmap)
        
        # Reset opacity
        painter.setOpacity(1.0)


    def apply_glass_glare_effect(self, painter, width, height):
        """
        Apply glass cover with reflections and glare effect.
        Simulates protective glass/plastic cover over LED display.
        """
        # Check if glass glare effect is enabled
        if not get_settings().get("led_glass_glare", True):
            return
        
        # Create horizontal glare bands (simulating light reflections on glass)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        
        # Main horizontal glare band (top 1/3 area)
        glare_gradient_1 = QtGui.QLinearGradient(0, 0, 0, height * 0.33)
        glare_gradient_1.setColorAt(0, QtGui.QColor(255, 255, 255, 45))
        glare_gradient_1.setColorAt(0.4, QtGui.QColor(255, 255, 255, 20))
        glare_gradient_1.setColorAt(0.7, QtGui.QColor(255, 255, 255, 8))
        glare_gradient_1.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
        
        painter.setBrush(QtGui.QBrush(glare_gradient_1))
        painter.setPen(QtCore.Qt.NoPen)
        # Draw horizontal band across top 1/3
        painter.drawRect(0, 0, width, int(height * 0.33))
        
        # Secondary horizontal glare (within top 1/3, slightly angled)
        glare_gradient_2 = QtGui.QLinearGradient(0, height * 0.15, width * 0.2, height * 0.33)
        glare_gradient_2.setColorAt(0, QtGui.QColor(200, 220, 255, 25))
        glare_gradient_2.setColorAt(0.4, QtGui.QColor(200, 220, 255, 12))
        glare_gradient_2.setColorAt(0.8, QtGui.QColor(200, 220, 255, 4))
        glare_gradient_2.setColorAt(1, QtGui.QColor(200, 220, 255, 0))
        
        painter.setBrush(QtGui.QBrush(glare_gradient_2))
        # Draw slightly slanted horizontal band within top 1/3
        glare_polygon_2 = QtGui.QPolygon([
            QtCore.QPoint(0, int(height * 0.15)),
            QtCore.QPoint(width, int(height * 0.18)),
            QtCore.QPoint(width, int(height * 0.33)),
            QtCore.QPoint(0, int(height * 0.30))
        ])
        painter.drawPolygon(glare_polygon_2)
        
        # Add subtle glass texture (horizontal lines simulating glass surface)
        # More prominent in top 1/3
        glass_texture_color = QtGui.QColor(255, 255, 255, 5)
        for y in range(0, int(height * 0.33), 15):
            painter.fillRect(0, y, width, 1, glass_texture_color)
        # Lighter texture for rest of display
        glass_texture_color_light = QtGui.QColor(255, 255, 255, 2)
        for y in range(int(height * 0.33), height, 25):
            painter.fillRect(0, y, width, 1, glass_texture_color_light)
        
        # Add corner highlights (where light hits glass edges)
        # Top-left corner - enhanced for top 1/3
        corner_gradient = QtGui.QRadialGradient(0, 0, min(width, height) * 0.35)
        corner_gradient.setColorAt(0, QtGui.QColor(255, 255, 255, 30))
        corner_gradient.setColorAt(0.5, QtGui.QColor(255, 255, 255, 10))
        corner_gradient.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
        painter.setBrush(QtGui.QBrush(corner_gradient))
        painter.drawRect(0, 0, int(width * 0.3), int(height * 0.33))
        
        # Bottom-right corner (dimmer)
        corner_gradient_2 = QtGui.QRadialGradient(width, height, min(width, height) * 0.2)
        corner_gradient_2.setColorAt(0, QtGui.QColor(255, 255, 255, 10))
        corner_gradient_2.setColorAt(0.7, QtGui.QColor(255, 255, 255, 2))
        corner_gradient_2.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
        painter.setBrush(QtGui.QBrush(corner_gradient_2))
        painter.drawRect(int(width * 0.7), int(height * 0.6), int(width * 0.3), int(height * 0.4))
        
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

    def paint_ticker(self, widget):
        self.ticker_click_areas = []
        painter = QtGui.QPainter(widget)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)  # Crisp pixels for LED look
        width = widget.width()
        height = self.ticker_height
        
        # Create realistic LED board background with depth
        # Base dark background (LED board substrate)
        base_color = QtGui.QColor(8, 10, 12)
        painter.fillRect(0, 0, width, height, base_color)
        
        # Add subtle vertical gradient for depth
        depth_grad = QtGui.QLinearGradient(0, 0, 0, height)
        depth_grad.setColorAt(0, QtGui.QColor(15, 18, 22, 180))
        depth_grad.setColorAt(0.5, QtGui.QColor(12, 14, 18, 120))
        depth_grad.setColorAt(1, QtGui.QColor(8, 10, 14, 160))
        painter.fillRect(0, 0, width, height, depth_grad)
        
        # Add horizontal scanlines (LED matrix rows)
        scanline_color = QtGui.QColor(0, 0, 0, 80)
        scanline_highlight = QtGui.QColor(25, 30, 38, 40)
        for y in range(0, height, 4):  # Every 4 pixels
            # Dark scanline
            painter.fillRect(0, y, width, 2, scanline_color)
            # Subtle highlight line
            if y + 2 < height:
                painter.fillRect(0, y + 2, width, 1, scanline_highlight)
        
        # Add subtle LED pixel grid pattern
        pixel_grid_color = QtGui.QColor(18, 22, 28, 30)
        for x in range(0, width, 6):  # Vertical lines every 6 pixels
            painter.fillRect(x, 0, 1, height, pixel_grid_color)
        
        if self.loading:
            painter.setFont(self.ticker_font)
            text = "TCKR: Loading"
            metrics = QtGui.QFontMetrics(self.ticker_font)
            text_width = metrics.horizontalAdvance(text)
            x = (width - text_width) // 2
            y = (height + metrics.ascent()) // 2
            self.draw_text_with_global_glow(painter, x, y, text, QtGui.QColor("#FFD700"))
            painter.end()
            return
        if not self.ticker_pixmaps:
            painter.end()
            return

        base_cycle_width = self.get_cycle_width()
        donate_cycle_width = self._donate_pixmap_width + base_cycle_width

        cycle_positions = []
        x = self.offset
        est_cycles = (width // min(base_cycle_width, donate_cycle_width)) + 6
        for i in range(est_cycles):
            if i % 3 == 0:
                cycle_positions.append((x, True))
                x += donate_cycle_width
            else:
                cycle_positions.append((x, False))
                x += base_cycle_width

        for x, is_donate in cycle_positions:
            draw_x = x
            # Draw stock tickers first
            for pixmap, w, area_tpls in zip(self.ticker_pixmaps, self.ticker_pixmap_widths, self.ticker_area_templates):
                painter.drawPixmap(draw_x, 0, pixmap)
                for area_type, tkr, rect in area_tpls:
                    offset_rect = QtCore.QRect(rect)
                    offset_rect.translate(draw_x, 0)
                    self.ticker_click_areas.append((area_type, tkr, offset_rect))
                draw_x += w
            # Then draw donate message at the end (if this cycle includes it)
            if is_donate:
                painter.drawPixmap(draw_x, 0, self._donate_pixmap)
                for area_type, tkr, rect in self._donate_area_template:
                    offset_rect = QtCore.QRect(rect)
                    offset_rect.translate(draw_x, 0)
                    self.ticker_click_areas.append((area_type, tkr, offset_rect))
                draw_x += self._donate_pixmap_width

        supercycle_width = donate_cycle_width + 2 * base_cycle_width

        self.offset_f = float(self.offset)
        self.offset_f -= self.scroll_speed
        self.offset = int(self.offset_f)
        if self.offset <= -supercycle_width:
            self.offset += supercycle_width
        
        # Apply bloom/glow effect (light bleeding from bright LEDs)
        self.apply_bloom_effect(painter, width, height)
        
        # Apply ghosting effect on top of everything (creates glow effect)
        self.apply_ghosting_effect(painter, width, height)
        
        # Apply glass cover with reflections/glare (final layer on top of everything)
        self.apply_glass_glare_effect(painter, width, height)
        
        painter.end()
    def ticker_mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            pos = event.pos()
            for area_type, tkr, rect in self.ticker_click_areas:
                if rect.contains(pos):
                    if area_type == 'donate':
                        webbrowser.open("https://paypal.me/paypaulc")
                    else:
                        url = f"https://www.tradingview.com/symbols/{tkr}/"
                        webbrowser.open(url)
                    break
    def contextMenuEvent(self, event):
        tray = getattr(self, 'tray_icon', None)
        if tray:
            tray.contextMenu().exec_(event.globalPos())
    def closeEvent(self, event):
        # Stop all timers immediately to prevent further processing
        if hasattr(self, 'timer') and self.timer.isActive():
            self.timer.stop()
        if hasattr(self, 'update_timer') and self.update_timer.isActive():
            self.update_timer.stop()
        if hasattr(self, 'market_status_timer') and self.market_status_timer.isActive():
            self.market_status_timer.stop()
        if hasattr(self, 'position_check_timer') and self.position_check_timer.isActive():
            self.position_check_timer.stop()
        
        # Clear any pending API fetch tasks in the thread pool
        QtCore.QThreadPool.globalInstance().clear()
        
        # Remove appbar quickly
        if sys.platform == "win32":
            remove_appbar(int(self.winId()))
        
        super().closeEvent(event)
    def enterEvent(self, event):
        if self.timer.isActive():
            self.timer.stop()
        event.accept()
    def leaveEvent(self, event):
        if not self.timer.isActive():
            self.timer.start(self.timer_interval)
        event.accept()
    def nativeEvent(self, eventType, message):
        # Only process Windows messages
        if eventType != "windows_generic_MSG":
            return False, 0
        
        if sys.platform != "win32":
            return False, 0
            
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        msg_id = user32.RegisterWindowMessageW("TCKR_APPBAR_MESSAGE")
        msg_ptr = int(message)
        
        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt_x", wintypes.LONG),
                ("pt_y", wintypes.LONG),
            ]
        
        msg = MSG.from_address(msg_ptr)
        
        if msg.message == msg_id:
            # AppBar callback received
            notification = msg.wParam
            print(f"[APPBAR EVENT] Received notification: {notification}")
            
            # ABN_POSCHANGED (1) - Another appbar changed position/size
            if notification == ABN_POSCHANGED:
                print(f"[APPBAR EVENT] ABN_POSCHANGED - Another appbar changed, reaffirming our position")
                
                # Prevent infinite loop - ignore notifications that occur shortly after we set the work area
                # This prevents our own work area changes from triggering a feedback loop
                import time as time_module
                current_time = time_module.time()
                time_since_last_set = current_time - self._last_work_area_set_time
                
                if time_since_last_set < 2.0:  # Ignore notifications within 2 seconds of our work area change
                    print(f"[APPBAR EVENT] Ignoring ABN_POSCHANGED ({time_since_last_set:.2f}s after work area change)")
                    return True, 0
                
                # Reaffirm our position when other appbars change (e.g., when an app docks)
                screen_index = get_settings().get("screen_index", 0)
                app = QtWidgets.QApplication.instance()
                screens = app.screens()
                if 0 <= screen_index < len(screens):
                    screen = screens[screen_index]
                else:
                    screen = app.primaryScreen()
                rect = screen.geometry()
                
                # CRITICAL: Get the actual physical window height for AppBar operations
                # On high-DPI screens, Qt's logical pixels differ from Windows physical pixels
                # We must use the physical height to maintain consistent space reservation
                hwnd = int(self.winId())
                actual_window_rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(actual_window_rect))
                actual_window_height = actual_window_rect.bottom - actual_window_rect.top
                print(f"[APPBAR EVENT] Window height: logical={self.ticker_height}px, physical={actual_window_height}px")
                
                # Query our current AppBar position
                shell32 = ctypes.windll.shell32
                abd = APPBARDATA()
                abd.cbSize = ctypes.sizeof(APPBARDATA)
                abd.hWnd = hwnd
                abd.uCallbackMessage = msg_id
                abd.uEdge = ABE_TOP
                abd.rc.left = rect.left()
                abd.rc.top = rect.top()
                abd.rc.right = rect.right()
                abd.rc.bottom = rect.top() + actual_window_height  # Use physical height
                
                # Query what Windows thinks our position should be
                shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
                print(f"[APPBAR EVENT] QUERYPOS result: top={abd.rc.top}, bottom={abd.rc.bottom}")
                
                # Reset to our desired position - always at the top with FULL physical height
                abd.rc.top = rect.top()
                abd.rc.bottom = rect.top() + actual_window_height  # Use physical height
                abd.rc.left = rect.left()
                abd.rc.right = rect.right()
                
                # Reaffirm our position with SETPOS
                shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
                print(f"[APPBAR EVENT] SETPOS reaffirmed: top={abd.rc.top}, bottom={abd.rc.bottom}, height={actual_window_height}px")
                
                # DON'T update work area here - it causes an infinite loop!
                # The work area is already set during initial AppBar registration
                # Updating it here triggers another ABN_POSCHANGED, creating a feedback loop
                
                # Force window position using SetWindowPos with physical height
                HWND_TOPMOST = -1
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 
                                  rect.left(), rect.top(), 
                                  rect.width(), actual_window_height,  # Use physical height
                                  SWP_SHOWWINDOW | SWP_NOACTIVATE)
                
                print(f"[APPBAR EVENT] Window repositioned to top: y={rect.top()}")
            
            # ABN_FULLSCREENAPP (2) - Full screen app activated/deactivated
            elif notification == ABN_FULLSCREENAPP:
                fullscreen_active = msg.lParam
                print(f"[APPBAR EVENT] ABN_FULLSCREENAPP - Fullscreen: {fullscreen_active}")
                # When a fullscreen app activates, we might want to hide or show the ticker
                # For now, we'll just maintain our position
            
            # ABN_WINDOWARRANGE (3) - User is rearranging windows
            elif notification == ABN_WINDOWARRANGE:
                arranging = msg.lParam
                print(f"[APPBAR EVENT] ABN_WINDOWARRANGE - Arranging: {arranging}")
                # Maintain position during window arrangement
            
            return True, 0
        
        return False, 0

class ManageStocksDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Stocks")
        self.stocks = load_stocks()
        self.sort_and_refresh()
        layout = QtWidgets.QVBoxLayout(self)
        self.list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.list_widget)
        self.refresh_list_widget()
        add_layout = QtWidgets.QHBoxLayout()
        self.ticker_entry = QtWidgets.QLineEdit()
        add_btn = QtWidgets.QPushButton("Add")
        add_btn.clicked.connect(self.add_stock)
        add_layout.addWidget(self.ticker_entry)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)
        remove_btn = QtWidgets.QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_selected)
        layout.addWidget(remove_btn)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save_and_close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def sort_and_refresh(self):
        self.stocks.sort(key=lambda s: s[0])

    def refresh_list_widget(self):
        self.list_widget.clear()
        for tkr, _ in self.stocks:
            self.list_widget.addItem(tkr)

    def add_stock(self):
        tkr = self.ticker_entry.text().strip().upper()
        if tkr and tkr not in [s[0] for s in self.stocks]:
            self.stocks.append([tkr, f"{tkr}.png"])
            self.sort_and_refresh()
            self.refresh_list_widget()
            self.ticker_entry.clear()

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            idx = self.list_widget.row(item)
            self.list_widget.takeItem(idx)
            del self.stocks[idx]
        self.sort_and_refresh()
        self.refresh_list_widget()

    def save_and_close(self):
        self.sort_and_refresh()
        save_stocks(self.stocks)
        self.accept()

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)

def parse_args():
    class CustomHelpFormatter(argparse.HelpFormatter):
        def format_help(self):
            help_text = super().format_help()   
            return '\n' + help_text
    
    parser = argparse.ArgumentParser(
        description="TCKR Stock Ticker Command Line Options",
        formatter_class=lambda prog: CustomHelpFormatter(prog, max_help_position=48, width=120),
        epilog="\n\n"
    )
    parser.add_argument("-a", "--api", dest="finnhub_api_key", type=str, help="Finnhub API key")
    parser.add_argument("-c", "--crypto-api", dest="coingecko_api_key", type=str, help=argparse.SUPPRESS)
    parser.add_argument("-t", "--tickers", dest="tickers", type=str, help="Comma-separated tickers (e.g. AAPL,MSFT,T)")
    parser.add_argument("-s", "--speed", dest="speed", type=int, help="Ticker scroll speed")
    parser.add_argument("-ht", "--height", dest="ticker_height", type=int, help="Ticker height in pixels")
    parser.add_argument("-u", "--update-interval", dest="update_interval", type=int, help="Update interval in seconds")
    parser.add_argument("-b", "--backup-settings", action="store_true", help="Restore settings from backup and save as current")
    
    return parser.parse_args()

def restore_settings_from_backup():
    backup_file = SETTINGS_FILE + ".backup"
    backup_tickers_file = STOCKS_FILE + ".backup"
    restored = False

    if os.path.exists(backup_file):
        with open(backup_file, "r") as f:
            settings = json.load(f)
        save_settings(settings)
        shutil.copy2(SETTINGS_FILE, backup_file)
        restored = True

    if os.path.exists(backup_tickers_file):
        with open(backup_tickers_file, "r") as f:
            tickers = json.load(f)
        save_stocks(tickers)
        shutil.copy2(STOCKS_FILE, backup_tickers_file)
        restored = True

    return restored

def backup_settings_file():
    if os.path.exists(SETTINGS_FILE):
        backup_file = SETTINGS_FILE + ".backup"
        shutil.copy2(SETTINGS_FILE, backup_file)

def backup_stocks_file():
    if os.path.exists(STOCKS_FILE):
        backup_file = STOCKS_FILE + ".backup"
        shutil.copy2(STOCKS_FILE, backup_file)

def apply_command_line_settings(args):
    if getattr(args, "backup_settings", False):
        restored = restore_settings_from_backup()
        if not restored:
            print("No backup settings file found to restore.")

    settings = get_settings()
    changed = False

    if args.finnhub_api_key:
        settings["finnhub_api_key"] = args.finnhub_api_key
        changed = True
    if args.coingecko_api_key:
        settings["coingecko_api_key"] = args.coingecko_api_key
        changed = True
    if args.speed is not None:
        settings["speed"] = args.speed
        changed = True
    if args.ticker_height is not None:
        settings["ticker_height"] = args.ticker_height
        changed = True
    if args.update_interval is not None:
        settings["update_interval"] = args.update_interval
        changed = True

    if changed:
        backup_settings_file()
        save_settings(settings)

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        if tickers:
            backup_stocks_file()
            save_stocks([[t, f"{t}.png"] for t in tickers])

def main():
    # CRITICAL: Handle --help FIRST when running as windowed .exe
    # This must happen before ANY other initialization
    if (hasattr(sys, '_MEIPASS') or getattr(sys, 'frozen', False)):
        if '-h' in sys.argv or '--help' in sys.argv:
            if sys.platform == 'win32':
                import ctypes
                
                # Show help in a message box (works perfectly for windowed .exe)
                help_text = """TCKR Stock Ticker - Command Line Options

Usage: TCKR [options]

Options:
  -h, --help
      Show this help message

  -a FINNHUB_API_KEY, --api FINNHUB_API_KEY
      Set your Finnhub API key

  -t TICKERS, --tickers TICKERS
      Comma-separated list of stock tickers
      Example: -t AAPL,MSFT,GOOGL

  -s SPEED, --speed SPEED
      Set ticker scroll speed (pixels per frame)

  -ht TICKER_HEIGHT, --height TICKER_HEIGHT
      Set ticker height in pixels

  -u UPDATE_INTERVAL, --update-interval UPDATE_INTERVAL
      Set price update interval in seconds

  -b, --backup-settings
      Restore settings from backup file

Examples:
  TCKR.exe -a your_api_key_here
  TCKR.exe -t AAPL,MSFT,GOOGL -s 2
  TCKR.exe -ht 60 -u 300"""
                
                # Show message box with help text
                # MB_OK | MB_ICONINFORMATION = 0x00000040
                ctypes.windll.user32.MessageBoxW(0, help_text, "TCKR Help", 0x00000040)
                
                sys.exit(0)
    
    # Parse arguments FIRST before any Qt initialization
    args = parse_args()
    apply_command_line_settings(args)

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseOpenGLES)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseDesktopOpenGL)

    # Cleanup any orphaned appbar registrations from previous instances
    cleanup_orphaned_appbars()

    app = QtWidgets.QApplication(sys.argv)
    icon_path = resource_path("TCKR.ico")
    app.setWindowIcon(QtGui.QIcon(icon_path)) # <-- Add this line
    app.setQuitOnLastWindowClosed(False)
    
    # Register global cleanup handlers for emergency situations
    if sys.platform == "win32":
        atexit.register(global_cleanup_handler)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    ticker_window = TickerWindow()
    
    # Set global reference for emergency cleanup
    global _global_ticker_window
    _global_ticker_window = ticker_window
    
    ticker_window.set_transparency(get_settings().get("transparency", 100))
    tray = TrayIcon(app, ticker_window)
    ticker_window.tray_icon = tray
    tray.show()
    
    # Add application exit handler for additional safety
    def emergency_cleanup():
        """Emergency cleanup function called when application is about to exit"""
        print("[EXIT] Emergency cleanup - ensuring AppBar is removed")
        if sys.platform == "win32" and hasattr(ticker_window, 'winId'):
            try:
                remove_appbar(int(ticker_window.winId()))
            except Exception as e:
                print(f"[EXIT] Emergency cleanup failed: {e}")
    
    app.aboutToQuit.connect(emergency_cleanup)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
