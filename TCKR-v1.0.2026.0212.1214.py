"""
Author: Paul R. Charovkine
Program: TCKR.py
Date: 2026.02.12
Version: 1.0.2026.0212.1214
License: GNU AGPLv3

Description:
This program implements a customizable stock ticker application using Tkinter for Windows.
It displays real-time stock prices and logos in a scrolling ticker bar at the top of the screen.
Users can manage the list of stocks, adjust the ticker height, and update their Finnhub API key
through modern, user-friendly dialog boxes. The ticker integrates with the Windows AppBar for
persistent display and supports restarting or closing the ticker from the GUI.
"""
import pip_system_certs.wrapt_requests
pip_system_certs.wrapt_requests.inject_truststore()
import sys
import os
import json
import requests
import time
import datetime
from urllib.parse import quote as url_quote
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtMultimedia import QSoundEffect
import webbrowser
import ctypes
from ctypes import wintypes
import concurrent.futures
import threading
import argparse
import shutil
import signal
from modern_gui_styles import *  # Modern dark theme styling

class DebugColors:
    # Reset
    RESET = '\033[0m'

    # Base colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Bright colors
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

# Color mapping for debug tags (related tags get similar colors)
DEBUG_TAG_COLORS = {
    # API related - Blue tones
    'API': DebugColors.BRIGHT_BLUE,
    'API-DATA': DebugColors.BLUE,
    'API CALL': DebugColors.BRIGHT_BLUE,
    'API RESPONSE': DebugColors.BLUE,
    'API WARNING': DebugColors.BRIGHT_YELLOW,
    'YAHOO API': DebugColors.CYAN,

    # WebSocket related - Green tones
    'WEBSOCKET': DebugColors.BRIGHT_GREEN,
    'RT Update': DebugColors.GREEN,

    # Performance related - Yellow/Orange tones
    'PERF': DebugColors.BRIGHT_YELLOW,
    'NUMBA': DebugColors.YELLOW,
    'FPS': DebugColors.YELLOW,
    'RENDER': DebugColors.BRIGHT_YELLOW,

    # Effects related - Purple/Magenta tones
    'EFFECTS': DebugColors.BRIGHT_MAGENTA,
    'BLOOM': DebugColors.MAGENTA,
    'GLOW': DebugColors.MAGENTA,

    # Market/Data related - Cyan tones
    'UPDATE': DebugColors.BRIGHT_CYAN,
    'MARKET': DebugColors.CYAN,
    'INIT': DebugColors.CYAN,
    'FETCH NOW': DebugColors.CYAN,
    'TCKR': DebugColors.CYAN,
    'API KEY': DebugColors.CYAN,
    'PAUSE': DebugColors.CYAN,
    'APPBAR TIMING': DebugColors.YELLOW,
    'APPBAR DIAGNOSTICS': DebugColors.YELLOW,
    'APPBAR WARNING': DebugColors.BRIGHT_YELLOW,
    'EMERGENCY': DebugColors.BRIGHT_RED,
    'SIGNAL': DebugColors.RED,
    'YAHOO API CALL': DebugColors.CYAN,
    'YAHOO API RESPONSE': DebugColors.CYAN,
    'YAHOO API DATA': DebugColors.CYAN,
    'YAHOO API ERROR': DebugColors.RED,
    'API CALL': DebugColors.BLUE,
    'API RESPONSE': DebugColors.BLUE,
    'API DATA': DebugColors.BLUE,

    # Error/Warning - Red tones
    'ERROR': DebugColors.BRIGHT_RED,
    'WARNING': DebugColors.RED,

    # General/Other - White/Gray
    'DEFAULT': DebugColors.WHITE,
}

def colored_print(message):
    """
    Print message with colored debug tags.
    Automatically detects [TAG] patterns and colors them appropriately.
    """
    import re
    import os
    import sys

    # Enable ANSI colors on Windows
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Get console handle
            console_handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            # Enable virtual terminal processing
            mode = ctypes.c_uint32()
            kernel32.GetConsoleMode(console_handle, ctypes.byref(mode))
            mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(console_handle, mode)
        except:
            pass  # Ignore if we can't enable ANSI colors

    # Find all [TAG] patterns in the message
    tag_pattern = r'\[([^\]]+)\]'

    def color_tag(match):
        tag = match.group(1)
        color = DEBUG_TAG_COLORS.get(tag, DEBUG_TAG_COLORS['DEFAULT'])
        return f"{color}[{tag}]{DebugColors.RESET}"

    # Apply coloring to tags
    colored_message = re.sub(tag_pattern, color_tag, message)

    # Print the colored message
    print(colored_message)

# Websocket support for real-time data
try:
    import websocket
    WEBSOCKET_AVAILABLE = True
    colored_print("[WEBSOCKET] ✅ websocket-client library available")
except ImportError:
    WEBSOCKET_AVAILABLE = False
    colored_print("[WEBSOCKET] ❌ websocket-client not available - install with 'pip install websocket-client'")

# Try to enable color support with colorama
try:
    import colorama
    colorama.init()
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False

# Debug flags - set to False to reduce console output
DEBUG_APPBAR = False  # AppBar registration/removal debug messages
DEBUG_POSITIONING = False  # Window positioning debug messages

# PERF ENHANCEMENT 7: Global session for connection pooling
_REQUEST_SESSION = None

def get_requests_session():
    """Get or create a requests session with connection pooling"""
    global _REQUEST_SESSION
    if _REQUEST_SESSION is None:
        _REQUEST_SESSION = requests.Session()
        # Configure connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3
        )
        _REQUEST_SESSION.mount('http://', adapter)
        _REQUEST_SESSION.mount('https://', adapter)
        colored_print("[PERF] Initialized HTTP session with connection pooling")
    return _REQUEST_SESSION
import atexit

# Performance optimization using Numba JIT compilation
# DEFERRED: Import after splash screen to avoid 3+ second startup delay
USE_OPT = False
opt = None

# Memory optimization using pixmap pooling
# DEFERRED: Import after splash screen
USE_MEMORY_POOL = False
get_pooled_pixmap = None
return_pooled_pixmap = None
managed_pixmap = None
get_pool_stats = None

APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "TCKR")
SETTINGS_FILE = os.path.join(APPDATA_DIR, "TCKR.Settings.json")
STOCKS_FILE = os.path.join(APPDATA_DIR, "TCKR.Tickers.json")

# Friendly display names for major market indices
INDEX_DISPLAY_NAMES = {
    '^GSPC': 'S&P500',
    '^IXIC': 'NASDAQ',
    '^DJI': 'DJI'
}

# Global variable to track the main ticker window for emergency cleanup
_global_ticker_window = None
_global_tray = None

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
    # We will respect the caller-provided desired physical height (height) but
    # ensure it's at least as large as the actual window height so the window fits.
    actual_window_rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(actual_window_rect))
    actual_window_height = actual_window_rect.bottom - actual_window_rect.top
    # Treat incoming `height` as desired physical pixels (caller should convert logical->physical)
    try:
        desired_physical = int(height)
    except Exception:
        desired_physical = actual_window_height
    # Ensure we reserve at least enough for the actual window
    appbar_height = max(actual_window_height, desired_physical)
    if DEBUG_APPBAR: print(f"[APPBAR] Desired physical height: {desired_physical}px, Actual window height: {actual_window_height}px, Using appbar_height={appbar_height}px")

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
    if DEBUG_APPBAR: print(f"[APPBAR] ABM_NEW result: {result}")
    if DEBUG_APPBAR: print(f"[APPBAR] Registration: left={abd.rc.left}, top={abd.rc.top}, right={abd.rc.right}, bottom={abd.rc.bottom}, width={abd.rc.right - abd.rc.left}")
    
    # Query position - this tells us where Windows wants to place us
    shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
    if DEBUG_APPBAR: print(f"[APPBAR] QUERYPOS returned: top={abd.rc.top}, bottom={abd.rc.bottom}")
    
    # CRITICAL: Set the proposed rectangle coordinates with PHYSICAL height
    # For top edge, we want the full width of the screen
    abd.rc.left = rect.left()
    abd.rc.top = rect.top()  # Always at the very top
    abd.rc.right = rect.right()  # Full width
    abd.rc.bottom = rect.top() + appbar_height  # Reserve using ACTUAL physical height
    
    # Set the position - this reserves the space
    shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
    if DEBUG_APPBAR: print(f"[APPBAR] SETPOS with: left={abd.rc.left}, top={abd.rc.top}, right={abd.rc.right}, bottom={abd.rc.bottom}, height={abd.rc.bottom - abd.rc.top}")
    
    # After SETPOS, check what Windows actually gave us
    shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
    actual_reserved_height = abd.rc.bottom - abd.rc.top
    if DEBUG_APPBAR: print(f"[APPBAR] After SETPOS, QUERYPOS shows: top={abd.rc.top}, bottom={abd.rc.bottom}, reserved={actual_reserved_height}")
    
    if actual_reserved_height < appbar_height:
        colored_print(f"[APPBAR WARNING] Windows only reserved {actual_reserved_height}px instead of {appbar_height}px")
        # Try one more time with a brief pause to let Windows process the request
        abd.rc.top = rect.top()
        abd.rc.bottom = rect.top() + appbar_height
        abd.rc.left = rect.left()
        abd.rc.right = rect.right()
        shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        time.sleep(0.05)  # Reduced delay
        shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        if abd.rc.bottom - abd.rc.top >= appbar_height:
            if DEBUG_APPBAR: print(f"[APPBAR] Reservation successful on retry")
        else:
            if DEBUG_APPBAR: print(f"[APPBAR] Space reservation limited by Windows - using available space")
    
    # Use the reserved appbar_height for work area offset
    work_area_top_offset = appbar_height
    
    # Broadcast WM_SETTINGCHANGE to force all applications to recalculate work area
    # This is critical - without this, other apps may not respect the AppBar reservation
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    
    # CRITICAL FIX: Verify and enforce work area adjustment
    # For multi-monitor setups, we need to check if we're on the primary monitor
    monitor_info = wintypes.RECT()
    monitor_info.left = rect.left()
    monitor_info.top = rect.top()
    monitor_info.right = rect.right()
    monitor_info.bottom = rect.bottom()
    
    # Check if this is the primary monitor (starts at x=0)
    is_primary_monitor = rect.left() == 0
    
    # Check current work area (only meaningful for primary monitor)
    work_area_before = wintypes.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area_before), 0)  # SPI_GETWORKAREA = 48
    if DEBUG_APPBAR: print(f"[APPBAR] Work area BEFORE: top={work_area_before.top}, bottom={work_area_before.bottom}")
    if DEBUG_APPBAR: print(f"[APPBAR] Monitor info: primary={is_primary_monitor}, x={rect.left()}")
    
    # After setting AppBar position, Windows should have adjusted work area automatically
    # Let's verify (but only check for primary monitor)
    work_area_check = wintypes.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area_check), 0)
    if DEBUG_APPBAR: print(f"[APPBAR] Work area AFTER SETPOS: top={work_area_check.top}, expected={rect.top() + work_area_top_offset}")
    
    # CRITICAL: Only manually adjust work area for primary monitor
    # Secondary monitors don't use the global work area - AppBar should be sufficient
    if is_primary_monitor and work_area_check.top < (rect.top() + work_area_top_offset):
        if DEBUG_APPBAR: print(f"[APPBAR] Work area not adjusted by AppBar API - manually setting it")
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
        if DEBUG_APPBAR: print(f"[APPBAR] SystemParametersInfo(SPI_SETWORKAREA) result: {result}")
        if DEBUG_APPBAR: print(f"[APPBAR] Set work area top to: {new_work_area.top} (screen top {rect.top()} + actual window height {work_area_top_offset})")
        
        # Small delay to let Windows process the change
        time.sleep(0.1)
        
        # Verify it worked
        work_area_verify = wintypes.RECT()
        user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area_verify), 0)
        if DEBUG_APPBAR: print(f"[APPBAR] Work area after manual adjustment: top={work_area_verify.top}")
    else:
        if is_primary_monitor:
            if DEBUG_APPBAR: print(f"[APPBAR] Work area already correctly set at top={work_area_check.top}")
        else:
            if DEBUG_APPBAR: print(f"[APPBAR] Secondary monitor - AppBar registration sufficient, work area not applicable")
    
    # Skip broadcast to avoid 1-2 second delays from hung windows
    # The SystemParametersInfoW calls already notified Windows
    skip_broadcast = True
    
    if not skip_broadcast and is_primary_monitor:
        # Broadcast WM_SETTINGCHANGE with work area change to notify other apps
        # Use shorter timeout (100ms) to avoid blocking startup
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 
                                    47, 0,  # SPI_SETWORKAREA = 47
                                    SMTO_ABORTIFHUNG, 100, None)
        if DEBUG_APPBAR: print(f"[APPBAR] Broadcasted WM_SETTINGCHANGE to all windows (primary monitor)")
    else:
        if DEBUG_APPBAR: print(f"[APPBAR] Skipping WM_SETTINGCHANGE broadcast to avoid delays")
    
    # CRITICAL: Force window position using SetWindowPos
    # Removed sleep and broadcast delays for faster startup
    
    # Use SetWindowPos with TOPMOST and NOACTIVATE to ensure we're at the absolute top
    # but don't steal focus from other windows
    HWND_TOPMOST = -1
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    # Use actual_window_height (physical pixels) instead of height (logical pixels)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, rect.left(), rect.top(), 
                       rect.width(), actual_window_height, SWP_SHOWWINDOW | SWP_NOACTIVATE)
    
    if DEBUG_APPBAR: print(f"[APPBAR] Final SetWindowPos to x={rect.left()}, y={rect.top()}, width={rect.width()}, height={actual_window_height}")
    
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
    import time as time_module
    start_time = time_module.time()
    
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    
    if DEBUG_APPBAR: print(f"[APPBAR] Removing AppBar registration for window handle {hwnd}")
    
    abd = APPBARDATA()
    abd.cbSize = ctypes.sizeof(APPBARDATA)
    abd.hWnd = hwnd
    result = shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
    if DEBUG_APPBAR: print(f"[APPBAR] ABM_REMOVE result: {result}")
    
    colored_print(f"[APPBAR TIMING] ABM_REMOVE took {(time_module.time() - start_time)*1000:.1f}ms")
    t1 = time_module.time()
    
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
        if DEBUG_APPBAR: print(f"[APPBAR] SystemParametersInfo auto-recalculate result: {result1}")
        
        colored_print(f"[APPBAR TIMING] SystemParametersInfoW took {(time_module.time() - t1)*1000:.1f}ms")
        t2 = time_module.time()
        
        # Skip slow broadcasts during startup/cleanup - they're not critical
        # The SystemParametersInfoW call already notified Windows of the change
        # Broadcasting to hung windows causes 3+ second delays
        skip_broadcast = True  # Set to False if you need to notify all apps
        
        if not skip_broadcast:
            # Method 2: Force a complete desktop refresh
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002
            
            # Broadcast work area change with shorter timeout for faster exit
            user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 
                                      SPI_SETWORKAREA, 0,
                                      SMTO_ABORTIFHUNG, 100, None)
            
            colored_print(f"[APPBAR TIMING] First SendMessageTimeoutW took {(time_module.time() - t2)*1000:.1f}ms")
            t3 = time_module.time()
            
            # Also broadcast display settings change to force a complete refresh
            user32.SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 
                                      0, ctypes.c_wchar_p("intl"),
                                      SMTO_ABORTIFHUNG, 100, None)  # Reduced from 3000ms to 100ms
            
            colored_print(f"[APPBAR TIMING] Second SendMessageTimeoutW took {(time_module.time() - t3)*1000:.1f}ms")
        else:
            colored_print(f"[APPBAR TIMING] Skipped broadcasts to avoid hung window delays")
        
        # Give Windows time to process the changes (removed - not needed without broadcasts)
        
        # Verify the work area was restored
        work_area_after = wintypes.RECT()
        user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area_after), 0)  # SPI_GETWORKAREA = 48
        if DEBUG_APPBAR: print(f"[APPBAR] Work area after removal: top={work_area_after.top}, left={work_area_after.left}, right={work_area_after.right}, bottom={work_area_after.bottom}")
        
        if DEBUG_APPBAR: print(f"[APPBAR] AppBar removal and work area restoration completed")
        
    colored_print(f"[APPBAR TIMING] Total remove_appbar took {(time_module.time() - start_time)*1000:.1f}ms")

# Global flag to prevent cleanup recursion
_cleanup_in_progress = False

def global_cleanup_handler():
    """Global cleanup function for unexpected application termination"""
    global _global_ticker_window, _cleanup_in_progress
    
    # Prevent recursive cleanup calls
    if _cleanup_in_progress:
        return
    _cleanup_in_progress = True
    
    if _global_ticker_window and sys.platform == "win32":
        try:
            colored_print("[EMERGENCY] Global cleanup handler activated - removing AppBar")
            remove_appbar(int(_global_ticker_window.winId()))
        except Exception as e:
            colored_print(f"[EMERGENCY] Global cleanup failed: {e}")

def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown"""
    global _cleanup_in_progress
    
    # Prevent recursive signal handling
    if _cleanup_in_progress:
        return
    
    colored_print(f"[SIGNAL] Received signal {signum} - performing emergency cleanup")
    global_cleanup_handler()
    
    # Force immediate exit without triggering more signals
    os._exit(0)

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
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            
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
    OPTIMIZED WITH NUMBA for faster color calculations.
    """
    market_open = is_market_open()
    
    # Use optimized color calculation if available
    if USE_OPT:
        market_rgb, status_rgb = opt.calculate_market_status_colors(market_open)
        market_color = QtGui.QColor(market_rgb[0], market_rgb[1], market_rgb[2])
        status_color = QtGui.QColor(status_rgb[0], status_rgb[1], status_rgb[2])
        
        if market_open:
            return ("Market:", market_color, "Open", status_color)
        else:
            return ("Market:", market_color, "Closed", status_color)
    else:
        # Original implementation
        if market_open:
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
    
    # Check if this window is on the primary monitor
    is_primary_monitor = window_rect.left == 0
    
    # Get work area (only meaningful for primary monitor)
    work_area = wintypes.RECT()
    user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0)  # SPI_GETWORKAREA = 48
    
    colored_print(f"[APPBAR DIAGNOSTICS]")
    print(f"  Window position: top={window_rect.top}, bottom={window_rect.bottom}, height={actual_height}")
    print(f"  Expected height: {expected_height}")
    print(f"  Monitor type: {'Primary (x=0)' if is_primary_monitor else f'Secondary (x={window_rect.left})'}")
    print(f"  Work area: top={work_area.top}, left={work_area.left}, right={work_area.right}, bottom={work_area.bottom}")
    print(f"  Space reserved at top: {work_area.top} pixels")
    
    if is_primary_monitor:
        # Only check work area for primary monitor
        if work_area.top < expected_height:
            print(f"  ⚠️ WARNING: Work area top ({work_area.top}) is less than expected height ({expected_height})")
            print(f"     This means Windows did not reserve the full space for the AppBar")
            print(f"     Other windows will overlap the ticker bar")
        elif work_area.top > expected_height:
            print(f"  ℹ️ Work area reserved MORE space than requested ({work_area.top} vs {expected_height})")
        else:
            print(f"  ✓ Work area correctly reserved {expected_height} pixels at top")
    else:
        # Secondary monitor - work area check doesn't apply
        print(f"  ℹ️ Secondary monitor detected - work area check not applicable")
        print(f"     AppBar should reserve space automatically on secondary monitors")
        print(f"     If other windows overlap, it may be a Windows compositor issue")
    
    return work_area.top

def cleanup_orphaned_appbars():
    """Cleanup any orphaned appbar registrations from previous TCKR instances"""
    if sys.platform != "win32":
        return
    
    # Skip cleanup entirely - it was causing more problems than it solved
    # by interfering with window detection and appbar registration
    colored_print("[STARTUP] Skipping appbar cleanup to avoid interference")

def load_performance_modules():
    """Load heavy performance modules AFTER splash screen is shown"""
    global USE_OPT, opt, USE_MEMORY_POOL
    global get_pooled_pixmap, return_pooled_pixmap, managed_pixmap, get_pool_stats
    
    # Load Numba JIT compilation module
    try:
        import ticker_utils_numba as opt_module
        opt = opt_module
        USE_OPT = True
        # Status message already printed by ticker_utils_numba module
    except ImportError:
        USE_OPT = False
        colored_print("[PERF] Numba file not found. Using pure Python (place ticker_utils_numba.py in the same directory)")
    
    # Load memory pooling module
    try:
        import memory_pool as mp
        get_pooled_pixmap = mp.get_pooled_pixmap
        return_pooled_pixmap = mp.return_pooled_pixmap
        managed_pixmap = mp.managed_pixmap
        get_pool_stats = mp.get_pool_stats
        USE_MEMORY_POOL = True
        colored_print("[PERF] Memory pool available for pixmap optimization")
    except ImportError:
        USE_MEMORY_POOL = False
        colored_print("[PERF] Memory pool not available (place memory_pool.py in same directory)")

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
        "led_bloom_intensity": 60,  # Bloom/glow effect intensity (0-100%) - default 60%
        "led_ghosting_effect": True,  # Enable motion blur/trailing effect
        # Ghost intensity controls both tint opacity and color strength (0-200)
        "led_ghost_intensity": 50,  # 50 = default (so preview/initial blur ~50%)
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
        "global_text_glow": True,  # Subtle glow on all text (less intense than 5% price change glow)
        "show_fps_overlay": False,  # FPS overlay disabled by default
        "show_update_countdown": False,  # Update countdown overlay disabled by default
        "price_indicator_style": "triangles",  # Options: "triangles" or "arrows"
        "enable_second_ticker": False,  # Enable/disable second ticker below the main one
        "second_ticker_speed": 2,  # Scroll speed for second ticker (same as main by default)
        "second_ticker_stock_file": "",  # Optional stock file for second ticker (empty = use same stocks)
        "show_sparklines": False,  # Toggle historical mini-sparklines (off by default for performance)
        "sparkline_period": "1d",  # Sparkline history period: "1d" or "5d"
        "sparkline_position": "left",  # Sparkline placement relative to price/change: "left" or "right"
    }


# Helper: compute dominant color of a pixmap by sampling pixels (fast and approximate)
def calculate_pixmap_dominant_color(pixmap, sample_step=6):
    try:
        img = pixmap.toImage().convertToFormat(QtGui.QImage.Format_ARGB32)
    except Exception:
        return QtGui.QColor(200, 200, 200)
    w = img.width()
    h = img.height()
    rsum = gsum = bsum = count = 0
    for y in range(0, h, sample_step):
        for x in range(0, w, sample_step):
            px = img.pixel(x, y)
            c = QtGui.QColor(px)
            if c.alpha() <= 16:
                continue
            rsum += c.red(); gsum += c.green(); bsum += c.blue(); count += 1
    if count == 0:
        return QtGui.QColor(200, 200, 200)
    return QtGui.QColor(rsum // count, gsum // count, bsum // count)


def calculate_bloom_factor(percent):
    """Return a nonlinear bloom multiplier for a percent value (0-100).
    This makes the upper range (75-100%) much stronger while keeping low
    values subtle. The function returns a multiplicative factor to apply
    to base alpha multipliers.
    """
    p = max(0.0, min(1.0, float(percent) / 100.0))
    # Non-linear scaling: stronger near the top end
    # base p times (1 + p^1.8 * 2) gives 100% -> factor 3.0, 50% -> ~1.57
    return p * (1.0 + (p ** 1.8) * 2.0)


class EffectsPreviewWidget(QtWidgets.QWidget):
    """Small live preview widget for Bloom and Ghosting settings.
    It draws a short sample ticker line and applies simplified bloom and ghost
    rendering based on the provided intensity settings.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(500, 54)
        self.ghost_enabled = True
        self.bloom_enabled = True
        self.ghost_intensity = 50
        self.bloom_intensity = 60

    def set_params(self, ghost_enabled=None, ghost_intensity=None, bloom_enabled=None, bloom_intensity=None):
        if ghost_enabled is not None:
            self.ghost_enabled = ghost_enabled
        if ghost_intensity is not None:
            self.ghost_intensity = ghost_intensity
        if bloom_enabled is not None:
            self.bloom_enabled = bloom_enabled
        if bloom_intensity is not None:
            self.bloom_intensity = bloom_intensity
        self.update()

    def _widget_checked(self, name, default=False):
        parent = self.parent()
        widget = getattr(parent, name, None)
        if widget is None or not hasattr(widget, 'isChecked'):
            return default
        try:
            return bool(widget.isChecked())
        except Exception:
            return default

    def _combo_data(self, name, default=None):
        parent = self.parent()
        widget = getattr(parent, name, None)
        if widget is None:
            return default
        try:
            value = widget.currentData()
            return default if value is None else value
        except Exception:
            return default

    def _draw_text_with_glow(self, painter, x, y, text, color, glow_enabled):
        if glow_enabled:
            glow = QtGui.QColor(255, 255, 255, 35)
            painter.setPen(glow)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                painter.drawText(int(x + dx), int(y + dy), text)
        painter.setPen(color)
        painter.drawText(int(x), int(y), text)

    def _draw_price_indicator(self, painter, style, x, center_y, up, color):
        painter.save()
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)
        size = 7
        if style == 'triangles':
            if up:
                points = [
                    QtCore.QPointF(x, center_y + size),
                    QtCore.QPointF(x + size, center_y - size),
                    QtCore.QPointF(x + (size * 2), center_y + size)
                ]
            else:
                points = [
                    QtCore.QPointF(x, center_y - size),
                    QtCore.QPointF(x + size, center_y + size),
                    QtCore.QPointF(x + (size * 2), center_y - size)
                ]
            painter.drawPolygon(QtGui.QPolygonF(points))
        elif style == 'thin_arrows':
            pen = QtGui.QPen(color, 1)
            painter.setPen(pen)
            if up:
                painter.drawLine(x + 7, center_y + 6, x + 7, center_y - 6)
                painter.drawLine(x + 7, center_y - 6, x + 3, center_y - 2)
                painter.drawLine(x + 7, center_y - 6, x + 11, center_y - 2)
            else:
                painter.drawLine(x + 7, center_y - 6, x + 7, center_y + 6)
                painter.drawLine(x + 7, center_y + 6, x + 3, center_y + 2)
                painter.drawLine(x + 7, center_y + 6, x + 11, center_y + 2)
        else:
            shaft_w = 4
            shaft_h = 9
            if up:
                painter.drawRect(x + 5, center_y - 2, shaft_w, shaft_h)
                points = [
                    QtCore.QPointF(x + 7, center_y - 9),
                    QtCore.QPointF(x + 1, center_y - 2),
                    QtCore.QPointF(x + 13, center_y - 2)
                ]
            else:
                painter.drawRect(x + 5, center_y - 7, shaft_w, shaft_h)
                points = [
                    QtCore.QPointF(x + 7, center_y + 9),
                    QtCore.QPointF(x + 1, center_y + 2),
                    QtCore.QPointF(x + 13, center_y + 2)
                ]
            painter.drawPolygon(QtGui.QPolygonF(points))
        painter.restore()

    def _draw_sparkline(self, painter, rect, color, period):
        if rect.width() < 20:
            return
        points = []
        w = rect.width()
        h = rect.height()
        mid = rect.y() + (h / 2.0)
        if period == '5d':
            values = [0.15, -0.05, 0.05, -0.15, -0.02, 0.10, 0.04, 0.20, 0.12, 0.28, 0.18]
        else:
            values = [0.00, 0.10, 0.04, 0.18, 0.09, 0.24, 0.14, 0.30]
        count = len(values)
        for i, val in enumerate(values):
            x = rect.x() + int((i / max(1, count - 1)) * (w - 1))
            y = int(mid - (val * (h * 0.9)))
            points.append(QtCore.QPoint(x, y))
        pen = QtGui.QPen(color, 2)
        painter.setPen(pen)
        for i in range(1, len(points)):
            painter.drawLine(points[i - 1], points[i])

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        bg = QtGui.QLinearGradient(0, 0, 0, self.height())
        bg.setColorAt(0, QtGui.QColor(15, 18, 22))
        bg.setColorAt(1, QtGui.QColor(8, 10, 14))
        painter.fillRect(0, 0, self.width(), self.height(), bg)

        sample_symbol = "TEST"
        sample_price = "123.45"
        sample_change = "+1.23"
        sample_percent = "(+1.01%)"
        is_up = True
        try:
            main_win = getattr(get_ticker_icon, '_window_instance', None)
            source_win = None
            if main_win:
                source_win = main_win
            elif hasattr(self.parent(), 'stocks'):
                source_win = self.parent()

            if source_win and hasattr(source_win, 'stocks') and source_win.stocks:
                first = source_win.stocks[0]
                sample_symbol = INDEX_DISPLAY_NAMES.get(first, first)
                if hasattr(source_win, 'prices') and first in getattr(source_win, 'prices'):
                    p, prev = source_win.prices.get(first, (None, None))
                    if p is not None:
                        sample_price = f"{p:.2f}"
                        if prev is not None and prev != 0:
                            diff = p - prev
                            pct = (diff / prev) * 100.0
                            is_up = diff >= 0
                            sign = "+" if diff >= 0 else ""
                            sample_change = f"{sign}{diff:.2f}"
                            sample_percent = f"({sign}{pct:.2f}%)"
        except Exception:
            pass

        show_sparklines = self._widget_checked('show_sparklines_checkbox', False)
        sparkline_position = self._combo_data('sparkline_position_combo', 'left')
        sparkline_period = self._combo_data('sparkline_period_combo', '1d')
        indicator_style = self._combo_data('price_indicator_combo', 'triangles')
        matrix_enabled = self._widget_checked('led_icon_matrix_checkbox', True)
        glass_enabled = self._widget_checked('led_glass_glare_checkbox', True)
        text_glow_enabled = self._widget_checked('global_text_glow_checkbox', True)

        parent_font = None
        try:
            main_win = getattr(get_ticker_icon, '_window_instance', None)
            if main_win and hasattr(main_win, 'ticker_font') and main_win.ticker_font is not None:
                parent_font = QtGui.QFont(main_win.ticker_font)
        except Exception:
            parent_font = None
        if parent_font is None and hasattr(self.parent(), 'ticker_font') and self.parent().ticker_font is not None:
            try:
                parent_font = QtGui.QFont(self.parent().ticker_font)
            except Exception:
                parent_font = None
        if parent_font is None:
            parent_font = QtGui.QFont("Consolas", 16)
        base_sz = parent_font.pointSize()
        if base_sz <= 0:
            base_sz = 16
        parent_font.setPointSize(max(9, int(base_sz * 1.08)))
        font = parent_font

        left_pad = 10
        right_pad = 10
        inner_top = 6
        inner_bottom = 6
        sparkline_w = 72 if show_sparklines else 0
        sparkline_gap = 8 if show_sparklines else 0

        cur_font = QtGui.QFont(font)
        cur_sz = max(9, cur_font.pointSize())
        while cur_sz >= 9:
            cur_font.setPointSize(cur_sz)
            metrics = QtGui.QFontMetrics(cur_font)
            sym_w = metrics.horizontalAdvance(sample_symbol)
            price_w = metrics.horizontalAdvance(sample_price)
            chg_w = metrics.horizontalAdvance(sample_change)
            pct_w = metrics.horizontalAdvance(sample_percent)
            indicator_w = 18
            content_w = sym_w + 10 + price_w + 6 + indicator_w + 6 + chg_w + 6 + pct_w
            available_w = self.width() - left_pad - right_pad - sparkline_w - sparkline_gap
            if content_w <= available_w:
                break
            cur_sz -= 1

        painter.setFont(cur_font)
        fm = QtGui.QFontMetrics(cur_font)
        baseline_y = (self.height() + fm.ascent() - fm.descent()) // 2

        if show_sparklines and sparkline_position == 'left':
            spark_rect = QtCore.QRect(left_pad, inner_top, sparkline_w, self.height() - inner_top - inner_bottom)
            content_left = left_pad + sparkline_w + sparkline_gap
            content_right = self.width() - right_pad
        elif show_sparklines:
            spark_rect = QtCore.QRect(self.width() - right_pad - sparkline_w, inner_top, sparkline_w, self.height() - inner_top - inner_bottom)
            content_left = left_pad
            content_right = self.width() - right_pad - sparkline_w - sparkline_gap
        else:
            spark_rect = QtCore.QRect(0, 0, 0, 0)
            content_left = left_pad
            content_right = self.width() - right_pad

        symbol_x = content_left
        price_x = symbol_x + fm.horizontalAdvance(sample_symbol) + 10
        indicator_x = price_x + fm.horizontalAdvance(sample_price) + 6
        change_x = indicator_x + 18 + 6
        percent_x = change_x + fm.horizontalAdvance(sample_change) + 6

        if percent_x + fm.horizontalAdvance(sample_percent) > content_right:
            percent_x = max(change_x + 4, content_right - fm.horizontalAdvance(sample_percent))

        symbol_color = QtGui.QColor("#00B3FF")
        up_color = QtGui.QColor("#00FF40")
        down_color = QtGui.QColor("#FF4A4A")
        value_color = up_color if is_up else down_color

        if self.ghost_enabled and self.ghost_intensity > 0:
            intensity = self.ghost_intensity / 100.0
            offsets = [1.0, 2.2]
            for i, off in enumerate(offsets[::-1]):
                alpha = int(max(6, 120 * (0.6 * (1.0 - (i / (len(offsets) + 0.5)))) * intensity))
                gcolor = QtGui.QColor(0, 179, 255, alpha)
                painter.setPen(gcolor)
                painter.drawText(int(symbol_x + off), int(baseline_y + off), sample_symbol)
                gcolor2 = QtGui.QColor(value_color.red(), value_color.green(), value_color.blue(), alpha)
                painter.setPen(gcolor2)
                painter.drawText(int(price_x + off), int(baseline_y + off), sample_price)
                painter.drawText(int(change_x + off), int(baseline_y + off), sample_change)
                painter.drawText(int(percent_x + off), int(baseline_y + off), sample_percent)

        if self.bloom_enabled and self.bloom_intensity > 0:
            bf = calculate_bloom_factor(self.bloom_intensity)
            sym_rect = QtCore.QRect(int(symbol_x), 0, fm.horizontalAdvance(sample_symbol), int(self.height()))
            val_rect = QtCore.QRect(int(price_x), 0, fm.horizontalAdvance(sample_price + " " + sample_change + " " + sample_percent), int(self.height()))
            sym_center = sym_rect.center()
            val_center = val_rect.center()
            sym_r = max(sym_rect.width(), sym_rect.height()) * 0.62
            val_r = max(val_rect.width(), val_rect.height()) * 0.60
            sym_grad = QtGui.QRadialGradient(sym_center.x(), sym_center.y(), sym_r)
            val_grad = QtGui.QRadialGradient(val_center.x(), val_center.y(), val_r)
            sym_alpha = int(60 * bf)
            val_alpha = int(65 * bf)
            sym_grad.setColorAt(0, QtGui.QColor(symbol_color.red(), symbol_color.green(), symbol_color.blue(), min(255, sym_alpha)))
            sym_grad.setColorAt(1, QtGui.QColor(0, 0, 0, 0))
            val_grad.setColorAt(0, QtGui.QColor(value_color.red(), value_color.green(), value_color.blue(), min(255, val_alpha)))
            val_grad.setColorAt(1, QtGui.QColor(0, 0, 0, 0))

            painter.save()
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
            painter.setBrush(QtGui.QBrush(sym_grad))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(int(sym_center.x() - sym_r), int(sym_center.y() - sym_r), int(sym_r * 2), int(sym_r * 2))
            painter.setBrush(QtGui.QBrush(val_grad))
            painter.drawEllipse(int(val_center.x() - val_r), int(val_center.y() - val_r), int(val_r * 2), int(val_r * 2))
            painter.restore()

        if show_sparklines:
            self._draw_sparkline(painter, spark_rect, value_color, sparkline_period)

        self._draw_text_with_glow(painter, symbol_x, baseline_y, sample_symbol, symbol_color, text_glow_enabled)
        self._draw_text_with_glow(painter, price_x, baseline_y, sample_price, value_color, text_glow_enabled)
        self._draw_price_indicator(painter, indicator_style, int(indicator_x), int(self.height() / 2), is_up, value_color)
        self._draw_text_with_glow(painter, change_x, baseline_y, sample_change, value_color, text_glow_enabled)
        self._draw_text_with_glow(painter, percent_x, baseline_y, sample_percent, value_color, text_glow_enabled)

        if matrix_enabled:
            painter.save()
            matrix_dot = QtGui.QColor(255, 255, 255, 12)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(matrix_dot)
            step = 8
            dot = 2
            for yy in range(3, self.height(), step):
                for xx in range(3, self.width(), step):
                    painter.drawRect(xx, yy, dot, dot)
            painter.restore()

        if glass_enabled:
            painter.save()
            glare = QtGui.QLinearGradient(0, 0, 0, self.height())
            glare.setColorAt(0.0, QtGui.QColor(255, 255, 255, 48))
            glare.setColorAt(0.25, QtGui.QColor(255, 255, 255, 12))
            glare.setColorAt(0.65, QtGui.QColor(255, 255, 255, 4))
            glare.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
            painter.fillRect(0, 0, self.width(), self.height(), glare)
            painter.fillRect(0, 2, self.width(), 1, QtGui.QColor(255, 255, 255, 55))
            painter.restore()

        painter.end()


def save_settings(settings):
    os.makedirs(APPDATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4, sort_keys=True)

def load_stocks():
    if os.path.exists(STOCKS_FILE):
        try:
            with open(STOCKS_FILE, "r") as f:
                stocks = json.load(f)
                # Sort stocks with special characters first, then alphanumeric
                # Custom key: non-alphanumeric first (using space), then the symbol
                def sort_key(s):
                    key = ('~' if s[0][0].isalnum() else ' ') + s[0].upper()
                    return key
                stocks.sort(key=sort_key)
                return stocks
        except Exception:
            pass
    # Default stocks on first run: Major Market Indices (no API key needed)
    return [
        ["^GSPC", "^GSPC.png"],  # S&P 500
        ["^IXIC", "^IXIC.png"],  # NASDAQ Composite
        ["^DJI", "^DJI.png"]      # Dow Jones Industrial Average
    ]

def save_stocks(stocks):
    os.makedirs(APPDATA_DIR, exist_ok=True)
    with open(STOCKS_FILE, "w") as f:
        json.dump(stocks, f, indent=4)

class FinnhubApiKeyDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔑 Finnhub API Key Required")
        
        # Apply modern theme
        apply_modern_theme(self)
        self.setMinimumWidth(500)
        
        # Ensure dialog appears on top and on same screen as parent
        self.setWindowFlags(
            QtCore.Qt.Dialog | 
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Title
        title = QtWidgets.QLabel("📊 API Key Required")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #00b3ff; margin-bottom: 4px;")
        layout.addWidget(title)

        # Description
        desc = QtWidgets.QLabel(
            'A Finnhub API key is required to fetch stock prices.<br>'
            'You can get a <b>free API key</b> by registering at Finnhub.'
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #e0e0e0; margin-bottom: 8px;")
        layout.addWidget(desc)

        # Link to register
        link = QtWidgets.QLabel(
            '👉 <a href="https://finnhub.io/register" style="color: #00b3ff; text-decoration: none;">Register at finnhub.io</a>'
        )
        link.setOpenExternalLinks(True)
        link.setStyleSheet("font-size: 11px; margin-bottom: 8px;")
        layout.addWidget(link)

        # Info note
        info_note = QtWidgets.QLabel(
            '<b>Note:</b> You can use TCKR without an API key - it will display major market indices '
            '(S&P 500, NASDAQ, Dow Jones) using Yahoo Finance. Individual stocks require a Finnhub API key.'
        )
        info_note.setWordWrap(True)
        info_note.setStyleSheet("""
            font-size: 10px; 
            color: #ffa500; 
            background: #2a2520;
            border: 1px solid #ffa500;
            border-radius: 4px;
            padding: 8px;
            margin: 8px 0;
        """)
        layout.addWidget(info_note)

        # API Key input group
        api_group = QtWidgets.QGroupBox("Enter API Key")
        api_layout = QtWidgets.QVBoxLayout(api_group)
        api_layout.setSpacing(8)
        api_layout.setContentsMargins(12, 20, 12, 12)

        # API Key input with eye toggle
        key_container = QtWidgets.QWidget()
        key_layout = QtWidgets.QHBoxLayout(key_container)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(4)
        
        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setPlaceholderText("Paste your Finnhub API key here")
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        
        self.key_toggle = QtWidgets.QPushButton("👁")
        self.key_toggle.setFixedSize(30, 26)
        self.key_toggle.setCheckable(True)
        self.key_toggle.setToolTip("Show/Hide API Key")
        self.key_toggle.clicked.connect(self.toggle_key_visibility)
        self.key_toggle.setStyleSheet("""
            QPushButton {
                background: #2a2d35;
                border: 1px solid #3a3d45;
                border-radius: 4px;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #3a3d45;
                border: 1px solid #00b3ff;
            }
            QPushButton:checked {
                background: #00b3ff;
                border: 1px solid #00d4ff;
            }
        """)
        
        key_layout.addWidget(self.api_key_edit)
        key_layout.addWidget(self.key_toggle)
        api_layout.addWidget(key_container)
        
        layout.addWidget(api_group)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(8)
        
        cancel_btn = QtWidgets.QPushButton("Skip (Use Indices Only)")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #3a3d45;
                border: 1px solid #4a4d55;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background: #4a4d55;
                border: 1px solid #5a5d65;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        ok_btn = QtWidgets.QPushButton("Save API Key")
        ok_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00b3ff, stop:1 #0088cc);
                border: 1px solid #00d4ff;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: 600;
                color: white;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00d4ff, stop:1 #00a3dd);
            }
            QPushButton:pressed {
                background: #0088cc;
            }
        """)
        ok_btn.clicked.connect(self.accept)
        ok_btn.setDefault(True)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)
    
    def showEvent(self, event):
        """Position dialog on same screen as parent when shown"""
        super().showEvent(event)
        
        # Center on parent's screen if parent exists
        if self.parent():
            parent_geo = self.parent().geometry()
            self.move(
                parent_geo.center().x() - self.width() // 2,
                parent_geo.center().y() - self.height() // 2
            )

    def toggle_key_visibility(self):
        """Toggle password visibility for API key field"""
        if self.key_toggle.isChecked():
            self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Normal)
        else:
            self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)

    def get_api_key(self):
        return self.api_key_edit.text().strip()

def ensure_finnhub_api_key(parent=None):
    settings = get_settings()
    api_key = settings.get("finnhub_api_key", "").strip()
    if api_key:
        colored_print(f"[API KEY] Found existing API key in settings")
        return api_key
    
    colored_print("[API KEY] No API key found - showing dialog")
    dlg = FinnhubApiKeyDialog(parent)
    colored_print("[API KEY] Dialog created, showing...")
    
    if dlg.exec_() == QtWidgets.QDialog.Accepted:
        api_key = dlg.get_api_key()
        if api_key:
            settings["finnhub_api_key"] = api_key
            save_settings(settings)
            colored_print("[API KEY] API key saved to settings")
            return api_key
    
    colored_print("[API KEY] Dialog cancelled or no key entered - continuing without API key")
    return None

def fetch_yahoo_quote(ticker):
    """
    Fetch quote data from Yahoo Finance for indices.
    Returns (price, prev_close) or (None, None) on error.
    """
    try:
        # Yahoo Finance uses a different URL structure
        encoded_ticker = url_quote(ticker, safe='')
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_ticker}"
        
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
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        colored_print(f"[YAHOO API CALL] GET {url}")
        response = get_requests_session().get(url, headers=headers, timeout=10, proxies=proxies, verify=verify)
        colored_print(f"[YAHOO API RESPONSE] {ticker}: Status {response.status_code}")
        response.raise_for_status()
        data = response.json()
        
        # Navigate Yahoo Finance's nested JSON structure
        if 'chart' in data and 'result' in data['chart'] and len(data['chart']['result']) > 0:
            result = data['chart']['result'][0]
            meta = result.get('meta', {})
            
            price = meta.get('regularMarketPrice')
            prev_close = meta.get('previousClose') or meta.get('chartPreviousClose')
            
            colored_print(f"[YAHOO API DATA] {ticker}: price={price}, prev_close={prev_close}")
            return price, prev_close
        else:
            colored_print(f"[YAHOO API ERROR] {ticker}: Unexpected response structure")
            return None, None
            
    except Exception as e:
        colored_print(f"[YAHOO API ERROR] {ticker}: {e}")
        return None, None

def fetch_finnhub_quote(ticker, api_key):
    # URL-encode the ticker symbol to handle special characters like ^
    encoded_ticker = url_quote(ticker, safe='')
    url = f"https://finnhub.io/api/v1/quote?symbol={encoded_ticker}&token={api_key}"
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
        colored_print(f"[API CALL] GET {url}")
        response = get_requests_session().get(url, timeout=10, proxies=proxies, verify=verify)
        colored_print(f"[API RESPONSE] {ticker}: Status {response.status_code}")
        response.raise_for_status()
        data = response.json()
        colored_print(f"[API DATA] {ticker}: Full response: {data}")
        print(f"[API DATA] {ticker}: price={data.get('c')}, prev_close={data.get('pc')}")
        price = data.get("c")
        prev_close = data.get("pc")
        # Check if price is 0 (which might indicate no data)
        if price == 0:
            print(f"[API WARNING] {ticker}: Price is 0, treating as None")
            price = None
        return ticker, (price, prev_close)
    except Exception as e:
        print(f"[API ERROR] {ticker}: {e}")
        return ticker, (None, None)

def fetch_all_stock_prices(tickers, api_key, api_key_2=None):
    """
    Fetch stock prices using one or two API keys.
    If api_key_2 is provided, alternates between keys every 30 calls.
    Uses adaptive delay that starts at 1s and increases if errors occur.
    Uses Yahoo Finance for index symbols (starting with ^).
    """
    prices = {}
    
    # Separate Yahoo Finance tickers (indices) from Finnhub tickers
    yahoo_tickers = [t for t in tickers if t.startswith('^')]
    finnhub_tickers = [t for t in tickers if not t.startswith('^')]
    
    colored_print(f"[API] Starting to fetch prices: {len(finnhub_tickers)} from Finnhub, {len(yahoo_tickers)} from Yahoo")
    
    # Fetch Yahoo Finance data first (no API key needed, no rate limits)
    if yahoo_tickers:
        colored_print(f"[YAHOO API] Fetching {len(yahoo_tickers)} indices from Yahoo Finance")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            yahoo_futures = [executor.submit(fetch_yahoo_quote, ticker) for ticker in yahoo_tickers]
            for ticker, future in zip(yahoo_tickers, yahoo_futures):
                price, prev_close = future.result()
                prices[ticker] = (price, prev_close)
    
    # Fetch Finnhub data with rate limiting
    if finnhub_tickers:
        batch_size = 10
        call_count = 0
        batch_delay = 1.0  # Start with 1 second delay
        consecutive_errors = 0
        
        colored_print(f"[API] Starting to fetch {len(finnhub_tickers)} tickers from Finnhub")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            for i in range(0, len(finnhub_tickers), batch_size):
                batch = finnhub_tickers[i:i+batch_size]
                
                # Determine which API key to use for this batch
                # Switch to second key after 30 calls (3 batches of 10)
                if api_key_2 and call_count >= 30:
                    current_key = api_key_2
                    colored_print(f"[API KEY] Using API Key 2 for batch {i//batch_size + 1}")
                else:
                    current_key = api_key
                    if api_key_2:
                        colored_print(f"[API KEY] Using API Key 1 for batch {i//batch_size + 1}")
                
                colored_print(f"[API] Fetching batch {i//batch_size + 1}: {batch}")
                futures = [executor.submit(fetch_finnhub_quote, ticker, current_key) for ticker in batch]
                batch_had_error = False
                for future in concurrent.futures.as_completed(futures):
                    tkr, (price, prev_close) = future.result()
                    if price is None:
                        batch_had_error = True
                    prices[tkr] = (price, prev_close)
                    call_count += 1
                    
                    # Reset counter after 60 calls to alternate back to first key
                    if call_count >= 60:
                        call_count = 0
                
                # Adaptive delay adjustment
                if batch_had_error:
                    consecutive_errors += 1
                    if consecutive_errors >= 2 and batch_delay < 5.0:
                        batch_delay = min(batch_delay + 0.5, 5.0)  # Increase delay, cap at 5s
                        colored_print(f"[API] Errors detected, increasing delay to {batch_delay:.1f}s")
                else:
                    if consecutive_errors > 0:
                        print(f"[API] No errors in this batch, keeping delay at {batch_delay:.1f}s")
                    consecutive_errors = 0
                        
                if i + batch_size < len(finnhub_tickers):
                    print(f"[API] Waiting {batch_delay:.1f} seconds before next batch...")
                    time.sleep(batch_delay)
    
    colored_print(f"[API] Completed fetching {len(prices)} prices")
    return prices

def fetch_all_stock_prices_with_429(tickers, api_key, api_key_2=None, force=False):
    """
    Fetch stock prices with 429 detection using one or two API keys.
    If api_key_2 is provided, alternates between keys every 30 calls.
    Uses adaptive delay that starts at 1s and increases on 429 errors.
    Uses Yahoo Finance for index symbols (starting with ^).
    Includes caching to prevent duplicate fetches within 30 seconds.
    """
    prices = {}

    # Check cache for recent fetches of the same tickers
    import time
    current_time = time.time()
    cache_key = tuple(sorted(tickers))  # Sort for consistent key

    if not hasattr(fetch_all_stock_prices_with_429, '_cache'):
        fetch_all_stock_prices_with_429._cache = {}

    if cache_key in fetch_all_stock_prices_with_429._cache:
        cached_time, cached_prices = fetch_all_stock_prices_with_429._cache[cache_key]
        # Use cache if it's less than 60 seconds old — unless forced
        age = current_time - cached_time
        if not force and age < 60:
            colored_print(f"[API CACHE] Using cached results for {len(tickers)} tickers (age: {age:.1f}s)")
            return cached_prices, False
        elif force and age < 60:
            colored_print(f"[API CACHE] Bypassing cached results due to force=True (age: {age:.1f}s)")
        else:
            colored_print(f"[API CACHE] Cache expired for {len(tickers)} tickers (age: {age:.1f}s) - fetching fresh data")

    colored_print(f"[API] Starting to fetch prices (with 429 detection) for {len(tickers)} tickers")
    
    # Separate Yahoo Finance tickers (indices) from Finnhub tickers
    yahoo_tickers = [t for t in tickers if t.startswith('^')]
    finnhub_tickers = [t for t in tickers if not t.startswith('^')]
    
    colored_print(f"[API] Starting to fetch prices (with 429 detection) for {len(tickers)} tickers")
    
    # Fetch Yahoo Finance data first (no API key needed, no rate limits)
    if yahoo_tickers:
        colored_print(f"[YAHOO API] Fetching {len(yahoo_tickers)} indices from Yahoo Finance")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            yahoo_futures = [executor.submit(fetch_yahoo_quote, ticker) for ticker in yahoo_tickers]
            for ticker, future in zip(yahoo_tickers, yahoo_futures):
                price, prev_close = future.result()
                prices[ticker] = (price, prev_close)
    
    batch_size = 10
    had_429 = False
    call_count = 0
    batch_delay = 1.0  # Start with 1 second delay
    consecutive_429s = 0
    
    def fetch_with_status(ticker, api_key):
        # URL-encode the ticker symbol to handle special characters like ^
        encoded_ticker = url_quote(ticker, safe='')
        url = f"https://finnhub.io/api/v1/quote?symbol={encoded_ticker}&token={api_key}"
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
            colored_print(f"[API CALL] GET {url}")
            response = get_requests_session().get(url, timeout=10, proxies=proxies, verify=verify)
            colored_print(f"[API RESPONSE] {ticker}: Status {response.status_code}")
            response.raise_for_status()
            data = response.json()
            colored_print(f"[API DATA] {ticker}: Full response: {data}")
            print(f"[API DATA] {ticker}: price={data.get('c')}, prev_close={data.get('pc')}")
            price = data.get("c")
            prev_close = data.get("pc")
            # Check if price is 0 (which might indicate no data)
            if price == 0:
                print(f"[API WARNING] {ticker}: Price is 0, treating as None")
                price = None
            return ticker, (price, prev_close), response.status_code
        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, 'status_code', None)
            print(f"[API ERROR] {ticker}: {e}")
            return ticker, (None, None), status_code
        except Exception as e:
            print(f"[API ERROR] {ticker}: {e}")
            return ticker, (None, None), None

    # Fetch Finnhub data with rate limiting and 429 detection
    if finnhub_tickers:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            for i in range(0, len(finnhub_tickers), batch_size):
                batch = finnhub_tickers[i:i+batch_size]
                
                # Determine which API key to use for this batch
                # Switch to second key after 30 calls (3 batches of 10)
                if api_key_2 and call_count >= 30:
                    current_key = api_key_2
                    colored_print(f"[API KEY] Using API Key 2 for batch {i//batch_size + 1}")
                else:
                    current_key = api_key
                    if api_key_2:
                        colored_print(f"[API KEY] Using API Key 1 for batch {i//batch_size + 1}")
                
                colored_print(f"[API] Fetching batch {i//batch_size + 1}: {batch}")
                futures = [executor.submit(fetch_with_status, ticker, current_key) for ticker in batch]
                batch_had_429 = False
                for future in concurrent.futures.as_completed(futures):
                    tkr, (price, prev_close), status_code = future.result()
                    prices[tkr] = (price, prev_close)
                    if status_code == 429:
                        had_429 = True
                        batch_had_429 = True
                        print(f"[API WARNING] Received 429 (rate limit) for {tkr}")
                    call_count += 1
                    
                    # Reset counter after 60 calls to alternate back to first key
                    if call_count >= 60:
                        call_count = 0
                
                # Adaptive delay adjustment based on 429 errors
                if batch_had_429:
                    consecutive_429s += 1
                    if batch_delay < 10.0:
                        batch_delay = min(batch_delay + 1.0, 10.0)  # Increase delay by 1s, cap at 10s
                        print(f"[API] 429 detected, increasing delay to {batch_delay:.1f}s")
                else:
                    if consecutive_429s > 0:
                        print(f"[API] No 429 in this batch, keeping delay at {batch_delay:.1f}s")
                        consecutive_429s = 0
                        
                    if i + batch_size < len(finnhub_tickers):
                        print(f"[API] Waiting {batch_delay:.1f} seconds before next batch...")
                        time.sleep(batch_delay)
    
    colored_print(f"[API] Completed fetching {len(prices)} prices (429 detected: {had_429})")

    # Cache the results
    fetch_all_stock_prices_with_429._cache[cache_key] = (current_time, prices.copy())

    # Clean old cache entries (older than 60 seconds)
    cache_keys_to_remove = []
    for key, (cache_time, _) in fetch_all_stock_prices_with_429._cache.items():
        if current_time - cache_time > 60:
            cache_keys_to_remove.append(key)
    for key in cache_keys_to_remove:
        del fetch_all_stock_prices_with_429._cache[key]

    return prices, had_429


class FinnhubWebSocketClient:
    """
    WebSocket client for real-time Finnhub stock data.
    Provides live price updates during market hours, falls back to polling after hours.
    """

    def __init__(self, api_key, window_instance):
        self.api_key = api_key
        self.window = window_instance

        # Debug tracking
        self.messages_received = 0
        self.price_updates_processed = 0
        self.connection_start_time = None
        self.last_message_time = None
        self.total_connection_time = 0
        self.reconnection_count = 0
        self.ws = None
        self.connected = False
        self.subscribed_symbols = set()
        # Queue of symbols to subscribe once connection is open
        self.queued_subscriptions = set()
        self.last_ping = time.time()
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.ping_interval = 30  # Send ping every 30 seconds
        self.connection_thread = None
        
        # PERF: Message batching and throttling to reduce jitter
        self.price_buffer = {}  # {symbol: (price, timestamp)}
        self.last_update_time = {}  # {symbol: timestamp} for rate limiting
        
        # Load settings for batching parameters
        settings = get_settings()
        self.batch_interval_ms = settings.get('websocket_batch_interval', 80)
        self.min_update_interval_ms = settings.get('websocket_min_update_interval', 50)
        self.min_change_threshold = settings.get('websocket_change_threshold', 0.0005)
        self.verbose_update_logs = bool(settings.get('websocket_verbose_logs', False))

    def connect(self):
        """Connect to Finnhub websocket for real-time data"""
        if not WEBSOCKET_AVAILABLE:
            colored_print("[WEBSOCKET] WebSocket library not available - skipping real-time connection")
            return False

        if not self.api_key:
            colored_print("[WEBSOCKET] No API key available - skipping real-time connection")
            return False

        try:
            import time
            self._connection_attempt_time = time.time()
            colored_print("[WEBSOCKET] 🔌 Attempting to connect to Finnhub websockets...")
            def on_message(ws, message):
                try:
                    # Debug: log first few messages to see if we're receiving data
                    if self.messages_received < 3:
                        colored_print(f"[WEBSOCKET] 📨 Received message: {message[:200]}{'...' if len(message) > 200 else ''}")

                    data = json.loads(message)
                    self._handle_message(data)
                except json.JSONDecodeError as e:
                    colored_print(f"[WEBSOCKET] Failed to parse message: {e}")

            def on_open(ws):
                import time
                self.connection_start_time = time.time()
                self.connected = True
                self.reconnect_attempts = 0
                connection_duration = time.time() - getattr(self, '_connection_attempt_time', time.time())
                colored_print(f"[WEBSOCKET] ✅ Connected to Finnhub real-time data (took {connection_duration:.1f}s)")
                colored_print(f"[WEBSOCKET] 📊 Status: Connected | Messages: {self.messages_received} | Updates: {self.price_updates_processed}")
                # Flush any queued subscriptions now that we're connected
                try:
                    if self.queued_subscriptions:
                        # Only subscribe to finnhub symbols (filter out indices)
                        finnhub_symbols = [s for s in list(self.queued_subscriptions) if not s.startswith('^')]
                        if finnhub_symbols:
                            sent = 0
                            for sym in finnhub_symbols:
                                try:
                                    self.ws.send(json.dumps({'type': 'subscribe', 'symbol': sym}))
                                    sent += 1
                                except Exception as e:
                                    colored_print(f"[WEBSOCKET] ❌ Failed to send queued subscribe for {sym}: {e}")
                            colored_print(f"[WEBSOCKET] 📥 Flushed queued subscriptions: sent {sent}/{len(finnhub_symbols)} messages")
                            # Update subscribed_symbols to include what we attempted
                            self.subscribed_symbols.update(finnhub_symbols)
                        # Clear the queue regardless - we've attempted to send
                        self.queued_subscriptions.clear()
                except Exception as e:
                    colored_print(f"[WEBSOCKET] ❌ Error flushing queued subscriptions: {e}")

            def on_close(ws, close_status_code, close_msg):
                import time
                self.connected = False
                if self.connection_start_time:
                    connection_duration = time.time() - self.connection_start_time
                    self.total_connection_time += connection_duration
                    colored_print(f"[WEBSOCKET] 🔌 Connection closed: {close_status_code} - {close_msg}")
                    colored_print(f"[WEBSOCKET] 📊 Session: {connection_duration:.1f}s | Total: {self.total_connection_time:.1f}s | Reconnects: {self.reconnection_count}")
                else:
                    colored_print(f"[WEBSOCKET] 🔌 Connection closed: {close_status_code} - {close_msg}")

            def on_error(ws, error):
                colored_print(f"[WEBSOCKET] ❌ Connection error: {error}")
                self.connected = False

            self.ws = websocket.WebSocketApp(
                f"wss://ws.finnhub.io?token={self.api_key}",
                on_message=on_message,
                on_open=on_open,
                on_close=on_close,
                on_error=on_error
            )

            # Start connection in background thread
            self.connection_thread = threading.Thread(target=self._run_websocket, daemon=True)
            self.connection_thread.start()

            return True
        except Exception as e:
            colored_print(f"[WEBSOCKET] Failed to initialize websocket connection: {e}")
            return False

    def _run_websocket(self):
        """Run the websocket connection with automatic reconnection"""
        while self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                self.ws.run_forever(ping_interval=self.ping_interval, ping_timeout=10)
                if not self.connected:
                    self.reconnect_attempts += 1
                    self.reconnection_count += 1
                    if self.reconnect_attempts < self.max_reconnect_attempts:
                        delay = min(2 ** self.reconnect_attempts, 30)  # Exponential backoff
                        colored_print(f"[WEBSOCKET] 🔄 Reconnecting in {delay}s (attempt {self.reconnect_attempts}/{self.max_reconnect_attempts})")
                        time.sleep(delay)
                    else:
                        colored_print("[WEBSOCKET] ❌ Max reconnection attempts reached - falling back to polling")
                        colored_print(f"[WEBSOCKET] 📊 Final stats - Reconnects: {self.reconnection_count} | Messages: {self.messages_received} | Updates: {self.price_updates_processed}")
                        break
                else:
                    break
            except Exception as e:
                colored_print(f"[WEBSOCKET] WebSocket error: {e}")
                self.reconnect_attempts += 1
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    time.sleep(5)
                else:
                    break

    def _handle_message(self, data):
        """Handle incoming websocket messages"""
        import time
        self.messages_received += 1
        self.last_message_time = time.time()
        msg_type = data.get('type')

        if msg_type == 'trade':
            # PERF: Buffer trades instead of processing immediately
            trades = data.get('data', [])
            trades_buffered = 0
            for trade in trades:
                symbol = trade.get('s')
                price = trade.get('p')
                timestamp = trade.get('t', 0) / 1000  # Convert ms to seconds

                if symbol and price:
                    # Buffer the update instead of emitting immediately
                    self.price_buffer[symbol] = (price, timestamp)
                    trades_buffered += 1
                    
            # Log buffering (messages accumulate until window processes them)
            if trades_buffered > 0:
                if self.messages_received <= 5 or self.messages_received % 50 == 0:
                    colored_print(f"[WEBSOCKET] 📦 Buffered {trades_buffered} trades ({len(self.price_buffer)} symbols total)")
        elif msg_type == 'ping':
            # Respond to ping
            if self.ws:
                try:
                    self.ws.send(json.dumps({'type': 'pong'}))
                except:
                    pass

        elif msg_type == 'error':
            error_msg = data.get('msg', 'Unknown error')
            colored_print(f"[WEBSOCKET] Error: {error_msg}")

    def process_buffered_updates(self, max_symbols=None):
        """Process buffered price updates - called from main thread timer
        
        Args:
            max_symbols: Maximum number of symbols to process (None = all)
        """
        if not self.price_buffer:
            return 0  # Return count of processed symbols
        
        buffer_size = len(self.price_buffer)
        symbols_to_process = list(self.price_buffer.keys())[:max_symbols] if max_symbols else list(self.price_buffer.keys())
        
        if symbols_to_process and self.verbose_update_logs:
            colored_print(f"[WEBSOCKET] 🔄 Processing {len(symbols_to_process)} of {buffer_size} buffered symbols...")
        
        import time
        current_time = time.time()
        updates_sent = 0
        symbols_skipped = 0
        updated_symbols = []
        
        # Process each selected symbol with rate limiting
        for symbol in symbols_to_process:
            if symbol not in self.price_buffer:
                continue  # Already removed
                
            price, timestamp = self.price_buffer[symbol]
            
            # Check if enough time has passed since last update for this symbol
            last_update = self.last_update_time.get(symbol, 0)
            if (current_time - last_update) * 1000 < self.min_update_interval_ms:
                symbols_skipped += 1
                continue  # Skip this symbol, too soon since last update
            
            # Check if change is significant enough (threshold: 0.05%)
            # Get previous price from window's stock_data if available
            should_update = True
            if hasattr(self.window, 'stock_data'):
                for stock_symbol, stock_price, stock_prev_close, _ in self.window.stock_data:
                    if stock_symbol == symbol and stock_price:
                        change_pct = abs((price - stock_price) / stock_price)
                        # Skip if change too small and updated recently
                        if change_pct < self.min_change_threshold and (current_time - last_update) < 5.0:
                            should_update = False
                            symbols_skipped += 1
                        break
            
            if should_update:
                # Update price directly in prices dict (instead of queuing via signal)
                # This ensures prices are updated BEFORE we rebuild the ticker
                self.price_updates_processed += 1
                
                # Update prices dict directly for all ticker windows
                if hasattr(self.window, 'tray_icon') and self.window.tray_icon:
                    targets = self.window.tray_icon.ticker_windows if hasattr(self.window.tray_icon, 'ticker_windows') else [self.window]
                    for ticker in targets:
                        if hasattr(ticker, 'stocks') and symbol in ticker.stocks:
                            old_price = ticker.prices.get(symbol, (None, None))[0]
                            prev_close = ticker.prices.get(symbol, (None, None))[1]
                            # Update price immediately
                            ticker.prices[symbol] = (price, prev_close)
                            ticker.bloom_cache_valid = False
                            
                            # Log significant price changes
                            if self.verbose_update_logs and old_price and abs(price - old_price) > 0.01:
                                change = price - old_price
                                change_pct = (change / old_price) * 100
                                colored_print(f"[WEBSOCKET] 💰 {symbol}: ${old_price:.2f} → ${price:.2f} ({change:+.2f}, {change_pct:+.2f}%)")
                
                self.last_update_time[symbol] = current_time
                updates_sent += 1
                # Track which symbols we updated so caller can rebuild incrementally
                if symbol not in updated_symbols:
                    updated_symbols.append(symbol)
                # Remove from buffer after processing
                del self.price_buffer[symbol]
        
        # Always log batch processing for debugging
        if self.verbose_update_logs and (updates_sent > 0 or symbols_skipped > 0):
            remaining = len(self.price_buffer)
            colored_print(f"[WEBSOCKET] 📈 Batch complete: {updates_sent} sent, {symbols_skipped} skipped | {remaining} remain | Total: {self.price_updates_processed} updates")
        
        return updates_sent, updated_symbols

    def subscribe_symbols(self, symbols):
        """Subscribe to real-time data for given symbols"""
        colored_print(f"[WEBSOCKET] subscribe_symbols called with {len(symbols)} symbols: {symbols[:5]}{'...' if len(symbols) > 5 else ''}")
        colored_print(f"[WEBSOCKET] Current state: connected={self.connected}, has_ws={self.ws is not None}, subscribed_count={len(self.subscribed_symbols)}")
        # Filter out Yahoo Finance symbols (^SPX, etc.) as they don't support websockets
        finnhub_symbols = [s for s in symbols if not s.startswith('^')]
        colored_print(f"[WEBSOCKET] Filtered to {len(finnhub_symbols)} Finnhub symbols")

        if not finnhub_symbols:
            colored_print(f"[WEBSOCKET] 📊 No Finnhub symbols to subscribe to (all Yahoo Finance indices)")
            return

        # If not connected yet, enqueue the requested symbols and ensure connection
        if not self.connected or not self.ws:
            # Add to queued subscriptions and attempt to establish connection if needed
            self.queued_subscriptions.update(finnhub_symbols)
            colored_print(f"[WEBSOCKET] ⚠️ Not connected - queued {len(self.queued_subscriptions)} symbols for subscribe (will flush on open)")
            if not self.ws:
                # Attempt to connect in background if we don't have a ws object
                try:
                    colored_print("[WEBSOCKET] No websocket instance - attempting connect()")
                    self.connect()
                except Exception as e:
                    colored_print(f"[WEBSOCKET] ❌ connect() attempt failed: {e}")
            return

        # We're connected - compute diffs and only send necessary subscribe/unsubscribe messages
        try:
            desired = set(finnhub_symbols)
            to_unsub = self.subscribed_symbols - desired
            to_sub = desired - self.subscribed_symbols

            # Unsubscribe only from symbols no longer desired
            if to_unsub:
                unsub_count = 0
                for sym in list(to_unsub):
                    try:
                        self.ws.send(json.dumps({'type': 'unsubscribe', 'symbol': sym}))
                        unsub_count += 1
                    except Exception as e:
                        colored_print(f"[WEBSOCKET] ❌ Failed to send unsubscribe for {sym}: {e}")
                colored_print(f"[WEBSOCKET] 📤 Unsubscribed from {unsub_count} symbols")

            # Subscribe to new symbols
            if to_sub:
                sent = 0
                for sym in list(to_sub):
                    try:
                        self.ws.send(json.dumps({'type': 'subscribe', 'symbol': sym}))
                        sent += 1
                    except Exception as e:
                        colored_print(f"[WEBSOCKET] ❌ Failed to send subscribe for {sym}: {e}")
                colored_print(f"[WEBSOCKET] 📥 Sent {sent}/{len(to_sub)} subscribe messages for new symbols")

            # Update the local subscription set to reflect what we attempted to subscribe
            self.subscribed_symbols.update(to_sub)
            # Remove unsubscribed symbols from the set
            for s in to_unsub:
                self.subscribed_symbols.discard(s)

        except Exception as e:
            colored_print(f"[WEBSOCKET] ❌ Failed to update subscriptions: {e}")

    def disconnect(self):
        """Disconnect from websocket"""
        # Clear buffers
        self.price_buffer.clear()
        self.last_update_time.clear()
        
        if self.ws:
            try:
                # Log final statistics before disconnecting
                import time
                session_duration = time.time() - getattr(self, 'connection_start_time', time.time()) if self.connected else 0
                colored_print(f"[WEBSOCKET] 🔌 Disconnecting... Session: {session_duration:.1f}s | Messages: {self.messages_received} | Updates: {self.price_updates_processed}")
                self.ws.close()
            except Exception as e:
                colored_print(f"[WEBSOCKET] Error during disconnect: {e}")
            self.ws = None
        self.connected = False
        self.subscribed_symbols.clear()

    def is_real_time_available(self):
        """Check if real-time websocket connection is active"""
        return self.connected and bool(self.subscribed_symbols)

    def get_debug_status(self):
        """Get current websocket debug status"""
        import time
        current_time = time.time()
        connection_duration = current_time - getattr(self, 'connection_start_time', current_time) if self.connected else 0
        time_since_last_msg = current_time - getattr(self, 'last_message_time', current_time) if self.last_message_time else 0

        return {
            'connected': self.connected,
            'subscribed_symbols': len(self.subscribed_symbols),
            'messages_received': self.messages_received,
            'price_updates_processed': self.price_updates_processed,
            'connection_duration': connection_duration,
            'time_since_last_message': time_since_last_msg,
            'reconnection_count': self.reconnection_count,
            'total_connection_time': self.total_connection_time
        }

    def log_status_summary(self):
        """Log a summary of current websocket status"""
        status = self.get_debug_status()
        if status['connected']:
            colored_print(f"[WEBSOCKET] 📊 Status: ✅ Connected | {status['subscribed_symbols']} symbols | {status['messages_received']} msgs | {status['price_updates_processed']} updates | {status['connection_duration']:.1f}s connected")
        else:
            colored_print(f"[WEBSOCKET] 📊 Status: ❌ Disconnected | {status['messages_received']} total msgs | {status['price_updates_processed']} total updates | {status['reconnection_count']} reconnects")


def get_ticker_icon(ticker, size=32):
    # PERF ENHANCEMENT 4: Icon cache with LRU eviction
    cache_key = f"{ticker.upper()}_{size}"
    
    # Check if we have a global window instance for cache access
    if hasattr(get_ticker_icon, '_window_instance') and get_ticker_icon._window_instance:
        window = get_ticker_icon._window_instance
        if cache_key in window.icon_cache:
            window.icon_cache_hits += 1
            # Move to end of dict for LRU tracking
            cached_pixmap = window.icon_cache[cache_key]
            del window.icon_cache[cache_key]
            window.icon_cache[cache_key] = cached_pixmap
            return cached_pixmap
        else:
            window.icon_cache_misses += 1
    
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
            resp = get_requests_session().get(url, timeout=5)
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

    # Subtle pixelation effect (reduced for better clarity) - optimized calculation
    if USE_OPT:
        pixel_size = opt.optimize_pixelation_effect(size, 1.15)
    else:
        pixel_size = max(16, int(size // 1.15))  # Very subtle pixelation for retro feel without losing clarity
        
    small_pixmap = pixmap.scaled(pixel_size, pixel_size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
    pixmap = small_pixmap.scaled(size, size, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

    # Apply scanlines and LED matrix overlay to icon
    scanline_pixmap = QtGui.QPixmap(pixmap.size())
    scanline_pixmap.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(scanline_pixmap)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
    painter.drawPixmap(0, 0, pixmap)
    
    # LED Matrix Overlay (if enabled in settings) - horizontal lines only
    if get_settings().get("led_icon_matrix", True):
        led_grid_color = QtGui.QColor(0, 0, 0, 30)  # Lighter for better visibility
        
        if USE_OPT:
            # Use optimized grid calculations - horizontal lines only
            _, h_positions = opt.calculate_grid_positions(pixmap.width(), pixmap.height(), 6)
            
            # Draw horizontal lines only
            for y_pos in h_positions:
                if y_pos < pixmap.height():
                    painter.fillRect(0, y_pos, pixmap.width(), 1, led_grid_color)
        else:
            # Original grid implementation - horizontal lines only
            for y in range(0, pixmap.height(), 6):
                painter.fillRect(0, y, pixmap.width(), 1, led_grid_color)
    
    painter.end()
    
    # PERF ENHANCEMENT 4: Store in cache with LRU management
    if hasattr(get_ticker_icon, '_window_instance') and get_ticker_icon._window_instance:
        window = get_ticker_icon._window_instance
        window.icon_cache[cache_key] = scanline_pixmap
        window.manage_icon_cache_lru()
    
    return scanline_pixmap

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, tray_icon=None):
        super().__init__(parent)
        self.tray_icon = tray_icon
        self.setWindowTitle("⚙️ TCKR Settings")
        self.settings = get_settings()
        self.original_settings = self.settings.copy()
        
        # Apply modern theme
        apply_modern_theme(self)
        self.setMinimumWidth(640)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # === API KEYS GROUP ===
        api_group = QtWidgets.QGroupBox("🔑 API Keys")
        api_layout = QtWidgets.QFormLayout(api_group)
        api_layout.setSpacing(10)
        api_layout.setContentsMargins(14, 20, 14, 14)

        label_col_width = 165
        combo_col_width = 170
        spin_col_width = 130
        pair_gap = 12
        input_height = 30

        def make_row_label(text):
            label = QtWidgets.QLabel(text)
            label.setFixedWidth(label_col_width)
            label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            return label

        def make_unit_label(text):
            label = QtWidgets.QLabel(text)
            label.setStyleSheet("color: #9aa3b2; font-size: 11px;")
            return label

        # Primary Key with eye icon
        primary_key_container = QtWidgets.QWidget()
        primary_key_layout = QtWidgets.QHBoxLayout(primary_key_container)
        primary_key_layout.setContentsMargins(0, 0, 0, 0)
        primary_key_layout.setSpacing(4)
        
        self.finnhub_api_key_edit = QtWidgets.QLineEdit(self.settings.get("finnhub_api_key", ""))
        self.finnhub_api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.finnhub_api_key_edit.setPlaceholderText("Primary Finnhub API key")
        self.finnhub_api_key_edit.setFixedHeight(input_height)
        
        self.primary_key_toggle = QtWidgets.QPushButton("👁")
        self.primary_key_toggle.setFixedSize(24, 26)
        self.primary_key_toggle.setCheckable(True)
        self.primary_key_toggle.setToolTip("Show/Hide API Key")
        self.primary_key_toggle.clicked.connect(lambda: self.toggle_key_visibility(self.finnhub_api_key_edit, self.primary_key_toggle))
        self.primary_key_toggle.setStyleSheet("""
            QPushButton {
                background: #2a2d35;
                border: 1px solid #3a3d45;
                border-radius: 4px;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #3a3d45;
                border: 1px solid #00b3ff;
            }
            QPushButton:checked {
                background: #00b3ff;
                border: 1px solid #00d4ff;
            }
        """)

        self.primary_key_test_btn = QtWidgets.QPushButton("TEST")
        self.primary_key_test_btn.setFixedSize(56, 26)
        self.primary_key_test_btn.setToolTip("Test API key against Finnhub endpoint")
        self.primary_key_status_label = QtWidgets.QLabel("")
        self.primary_key_status_label.setMinimumWidth(96)
        self.primary_key_status_label.setStyleSheet("color: #9aa3b2; font-size: 11px;")
        self.primary_key_test_btn.clicked.connect(lambda: self.test_api_key(self.finnhub_api_key_edit, "Primary", self.primary_key_status_label))
        
        primary_key_layout.addWidget(self.finnhub_api_key_edit)
        primary_key_layout.addWidget(self.primary_key_toggle)
        primary_key_layout.addWidget(self.primary_key_test_btn)
        primary_key_layout.addWidget(self.primary_key_status_label)
        primary_key_row = QtWidgets.QWidget()
        primary_key_row_layout = QtWidgets.QHBoxLayout(primary_key_row)
        primary_key_row_layout.setContentsMargins(0, 0, 0, 0)
        primary_key_row_layout.setSpacing(8)
        primary_key_row_layout.addWidget(make_row_label("Primary Key:"))
        primary_key_row_layout.addWidget(primary_key_container)
        api_layout.addRow(primary_key_row)

        # Secondary Key with eye icon
        secondary_key_container = QtWidgets.QWidget()
        secondary_key_layout = QtWidgets.QHBoxLayout(secondary_key_container)
        secondary_key_layout.setContentsMargins(0, 0, 0, 0)
        secondary_key_layout.setSpacing(4)
        
        self.finnhub_api_key_2_edit = QtWidgets.QLineEdit(self.settings.get("finnhub_api_key_2", ""))
        self.finnhub_api_key_2_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.finnhub_api_key_2_edit.setPlaceholderText("Optional - for load balancing")
        self.finnhub_api_key_2_edit.setFixedHeight(input_height)
        
        self.secondary_key_toggle = QtWidgets.QPushButton("👁")
        self.secondary_key_toggle.setFixedSize(24, 26)
        self.secondary_key_toggle.setCheckable(True)
        self.secondary_key_toggle.setToolTip("Show/Hide API Key")
        self.secondary_key_toggle.clicked.connect(lambda: self.toggle_key_visibility(self.finnhub_api_key_2_edit, self.secondary_key_toggle))
        self.secondary_key_toggle.setStyleSheet("""
            QPushButton {
                background: #2a2d35;
                border: 1px solid #3a3d45;
                border-radius: 4px;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background: #3a3d45;
                border: 1px solid #00b3ff;
            }
            QPushButton:checked {
                background: #00b3ff;
                border: 1px solid #00d4ff;
            }
        """)

        self.secondary_key_test_btn = QtWidgets.QPushButton("TEST")
        self.secondary_key_test_btn.setFixedSize(56, 26)
        self.secondary_key_test_btn.setToolTip("Test API key against Finnhub endpoint")
        self.secondary_key_status_label = QtWidgets.QLabel("")
        self.secondary_key_status_label.setMinimumWidth(96)
        self.secondary_key_status_label.setStyleSheet("color: #9aa3b2; font-size: 11px;")
        self.secondary_key_test_btn.clicked.connect(lambda: self.test_api_key(self.finnhub_api_key_2_edit, "Secondary", self.secondary_key_status_label))
        
        secondary_key_layout.addWidget(self.finnhub_api_key_2_edit)
        secondary_key_layout.addWidget(self.secondary_key_toggle)
        secondary_key_layout.addWidget(self.secondary_key_test_btn)
        secondary_key_layout.addWidget(self.secondary_key_status_label)
        secondary_key_row = QtWidgets.QWidget()
        secondary_key_row_layout = QtWidgets.QHBoxLayout(secondary_key_row)
        secondary_key_row_layout.setContentsMargins(0, 0, 0, 0)
        secondary_key_row_layout.setSpacing(8)
        secondary_key_row_layout.addWidget(make_row_label("Secondary Key:"))
        secondary_key_row_layout.addWidget(secondary_key_container)
        api_layout.addRow(secondary_key_row)
        
        update_interval_row = QtWidgets.QWidget()
        update_interval_layout = QtWidgets.QHBoxLayout(update_interval_row)
        update_interval_layout.setContentsMargins(0, 0, 0, 0)
        update_interval_layout.setSpacing(8)
        self.update_interval_spin = QtWidgets.QSpinBox()
        self.update_interval_spin.setRange(10, 3600)
        self.update_interval_spin.setValue(self.settings.get("update_interval", 300))
        self.update_interval_spin.setToolTip("How often to fetch prices from API")
        self.update_interval_spin.setFixedWidth(spin_col_width)
        self.update_interval_spin.setFixedHeight(input_height)
        update_interval_layout.addWidget(make_row_label("Update Interval:"))
        update_interval_layout.addWidget(self.update_interval_spin)
        update_interval_layout.addWidget(make_unit_label("sec"))
        update_interval_layout.addStretch(1)
        api_layout.addRow(update_interval_row)
        
        ws_refresh_row = QtWidgets.QWidget()
        ws_refresh_layout = QtWidgets.QHBoxLayout(ws_refresh_row)
        ws_refresh_layout.setContentsMargins(0, 0, 0, 0)
        ws_refresh_layout.setSpacing(8)
        ws_refresh_field_label = make_row_label("WS Visual Refresh:")
        ws_refresh_field_label.setToolTip("How often to update display with WebSocket prices\n0 = Disabled (perfectly smooth, no stutter)\n15-30 = Periodic updates (causes brief stutter)")
        self.ws_refresh_spin = QtWidgets.QSpinBox()
        self.ws_refresh_spin.setRange(0, 60)
        self.ws_refresh_spin.setValue(self.settings.get("websocket_visual_refresh_seconds", 0))
        self.ws_refresh_spin.setToolTip("0 = Smooth scrolling (no WS updates)\n15-30 = Periodic updates (brief stutter)")
        self.ws_refresh_spin.setFixedWidth(spin_col_width)
        self.ws_refresh_spin.setFixedHeight(input_height)
        ws_refresh_layout.addWidget(ws_refresh_field_label)
        ws_refresh_layout.addWidget(self.ws_refresh_spin)
        ws_refresh_layout.addWidget(make_unit_label("sec"))
        ws_refresh_layout.addStretch(1)
        api_layout.addRow(ws_refresh_row)
        
        layout.addWidget(api_group)
        
        # === APPEARANCE GROUP ===
        appearance_group = QtWidgets.QGroupBox("🎨 Appearance")
        appearance_layout = QtWidgets.QGridLayout(appearance_group)
        appearance_layout.setSpacing(10)
        appearance_layout.setContentsMargins(14, 20, 14, 14)
        appearance_layout.setColumnStretch(0, 1)
        appearance_layout.setColumnStretch(1, 1)

        def make_appearance_field(label_text, field_widget, unit_text=None):
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(make_row_label(label_text))
            row_layout.addWidget(field_widget)
            if unit_text:
                row_layout.addWidget(make_unit_label(unit_text))
            row_layout.addStretch(1)
            return row

        self.display_combo = QtWidgets.QComboBox()
        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        for i, screen in enumerate(screens):
            geom = screen.geometry()
            self.display_combo.addItem(f"Display {i+1} ({geom.width()}×{geom.height()})")
        self.display_combo.setCurrentIndex(self.settings.get("screen_index", 0))
        self.display_combo.setFixedWidth(combo_col_width)
        self.display_combo.setFixedHeight(input_height)
        display_row = make_appearance_field("Display:", self.display_combo)
        
        self.scroll_speed_spin = QtWidgets.QSpinBox()
        self.scroll_speed_spin.setRange(1, 50)
        self.scroll_speed_spin.setValue(self.settings.get("speed", 2))
        
        self.ticker_height_spin = QtWidgets.QSpinBox()
        self.ticker_height_spin.setRange(24, 200)
        self.ticker_height_spin.setValue(self.settings.get("ticker_height", 60))
        self.scroll_speed_spin.setFixedWidth(spin_col_width)
        self.scroll_speed_spin.setFixedHeight(input_height)
        self.ticker_height_spin.setFixedWidth(spin_col_width)
        self.ticker_height_spin.setFixedHeight(input_height)
        scroll_speed_row = make_appearance_field("Scroll Speed:", self.scroll_speed_spin, "px/frame")
        height_row = make_appearance_field("Height:", self.ticker_height_spin, "px")
        
        self.transparency_spin = QtWidgets.QSpinBox()
        self.transparency_spin.setRange(0, 100)
        self.transparency_spin.setValue(self.settings.get("transparency", 100))
        self.transparency_spin.setFixedWidth(spin_col_width)
        self.transparency_spin.setFixedHeight(input_height)
        transparency_row = make_appearance_field("Transparency:", self.transparency_spin, "%")
        
        self.price_indicator_combo = QtWidgets.QComboBox()
        self.price_indicator_combo.addItem("Arrows - Thick", "arrows")
        self.price_indicator_combo.addItem("Arrows - Thin", "thin_arrows")
        self.price_indicator_combo.addItem("Triangles", "triangles")
        current_indicator = self.settings.get("price_indicator_style", "triangles")
        index = self.price_indicator_combo.findData(current_indicator)
        if index >= 0:
            self.price_indicator_combo.setCurrentIndex(index)
        self.price_indicator_combo.setFixedWidth(combo_col_width)
        self.price_indicator_combo.setFixedHeight(input_height)
        indicator_row = make_appearance_field("Price Indicator:", self.price_indicator_combo)

        # Second ticker settings
        self.enable_second_ticker_checkbox = QtWidgets.QCheckBox("Enable Second Ticker")
        self.enable_second_ticker_checkbox.setChecked(self.settings.get("enable_second_ticker", False))

        self.second_ticker_speed_spin = QtWidgets.QSpinBox()
        self.second_ticker_speed_spin.setRange(1, 50)
        self.second_ticker_speed_spin.setValue(self.settings.get("second_ticker_speed", 2))
        self.second_ticker_speed_spin.setEnabled(self.settings.get("enable_second_ticker", False))
        self.second_ticker_speed_spin.setFixedWidth(spin_col_width)
        self.second_ticker_speed_spin.setFixedHeight(input_height)

        second_ticker_enable_field = QtWidgets.QWidget()
        second_ticker_enable_layout = QtWidgets.QHBoxLayout(second_ticker_enable_field)
        second_ticker_enable_layout.setContentsMargins(0, 0, 0, 0)
        second_ticker_enable_layout.setSpacing(8)
        second_ticker_enable_layout.addWidget(self.enable_second_ticker_checkbox)
        second_ticker_enable_layout.addStretch(1)
        enable_second_ticker_row = make_appearance_field("Second Ticker:", second_ticker_enable_field)

        second_ticker_speed_row = make_appearance_field("Second Ticker Speed:", self.second_ticker_speed_spin, "px/frame")

        self.second_ticker_stock_file_edit = QtWidgets.QLineEdit()
        self.second_ticker_stock_file_edit.setText(self.settings.get("second_ticker_stock_file", ""))
        self.second_ticker_stock_file_edit.setPlaceholderText("Leave empty to use same stocks as main ticker")
        self.second_ticker_stock_file_edit.setEnabled(self.settings.get("enable_second_ticker", False))
        self.second_ticker_stock_file_edit.setFixedHeight(input_height)

        # Add browse button for stock file
        stock_file_container = QtWidgets.QWidget()
        stock_file_layout = QtWidgets.QHBoxLayout(stock_file_container)
        stock_file_layout.setContentsMargins(0, 0, 0, 0)
        stock_file_layout.setSpacing(4)
        stock_file_layout.addWidget(self.second_ticker_stock_file_edit)

        self.second_ticker_stock_browse_btn = QtWidgets.QPushButton("📁")
        self.second_ticker_stock_browse_btn.setFixedSize(30, 26)
        self.second_ticker_stock_browse_btn.setToolTip("Browse for stock file")
        self.second_ticker_stock_browse_btn.clicked.connect(self.browse_second_ticker_stock_file)
        self.second_ticker_stock_browse_btn.setEnabled(self.settings.get("enable_second_ticker", False))
        stock_file_layout.addWidget(self.second_ticker_stock_browse_btn)

        # Historical mini-sparklines
        self.show_sparklines_checkbox = QtWidgets.QCheckBox("Show Historical Mini-Sparklines")
        self.show_sparklines_checkbox.setChecked(self.settings.get("show_sparklines", False))
        show_sparklines_field = QtWidgets.QWidget()
        show_sparklines_layout = QtWidgets.QHBoxLayout(show_sparklines_field)
        show_sparklines_layout.setContentsMargins(0, 0, 0, 0)
        show_sparklines_layout.setSpacing(8)
        show_sparklines_layout.addWidget(self.show_sparklines_checkbox)
        show_sparklines_layout.addStretch(1)
        show_sparklines_row = make_appearance_field("Sparklines:", show_sparklines_field)

        self.sparkline_period_combo = QtWidgets.QComboBox()
        self.sparkline_period_combo.addItem("1D", "1d")
        self.sparkline_period_combo.addItem("5D", "5d")
        current_period = self.settings.get("sparkline_period", "1d")
        period_index = self.sparkline_period_combo.findData(current_period)
        self.sparkline_period_combo.setCurrentIndex(period_index if period_index >= 0 else 0)
        self.sparkline_period_combo.setEnabled(self.show_sparklines_checkbox.isChecked())
        self.show_sparklines_checkbox.toggled.connect(self.sparkline_period_combo.setEnabled)
        self.sparkline_period_combo.setFixedWidth(combo_col_width)
        self.sparkline_period_combo.setFixedHeight(input_height)

        self.sparkline_position_combo = QtWidgets.QComboBox()
        self.sparkline_position_combo.addItem("Left of Price", "left")
        self.sparkline_position_combo.addItem("Right of Price", "right")
        current_position = self.settings.get("sparkline_position", "left")
        position_index = self.sparkline_position_combo.findData(current_position)
        self.sparkline_position_combo.setCurrentIndex(position_index if position_index >= 0 else 0)
        self.sparkline_position_combo.setEnabled(self.show_sparklines_checkbox.isChecked())
        self.show_sparklines_checkbox.toggled.connect(self.sparkline_position_combo.setEnabled)
        self.sparkline_position_combo.setFixedWidth(combo_col_width)
        self.sparkline_position_combo.setFixedHeight(input_height)
        sparkline_range_row = make_appearance_field("Sparkline Range:", self.sparkline_period_combo)
        sparkline_position_row = make_appearance_field("Sparkline Position:", self.sparkline_position_combo)

        appearance_layout.addWidget(display_row, 0, 0)
        appearance_layout.addWidget(scroll_speed_row, 0, 1)
        appearance_layout.addWidget(height_row, 1, 0)
        appearance_layout.addWidget(transparency_row, 1, 1)
        appearance_layout.addWidget(indicator_row, 2, 0)
        appearance_layout.addWidget(show_sparklines_row, 2, 1)
        appearance_layout.addWidget(sparkline_range_row, 3, 0)
        appearance_layout.addWidget(sparkline_position_row, 3, 1)

        second_ticker_separator = QtWidgets.QFrame()
        second_ticker_separator.setFrameShape(QtWidgets.QFrame.HLine)
        second_ticker_separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        appearance_layout.addWidget(second_ticker_separator, 4, 0, 1, 2)

        appearance_layout.addWidget(enable_second_ticker_row, 5, 0)
        appearance_layout.addWidget(second_ticker_speed_row, 5, 1)

        second_ticker_stocks_row = QtWidgets.QWidget()
        second_ticker_stocks_layout = QtWidgets.QHBoxLayout(second_ticker_stocks_row)
        second_ticker_stocks_layout.setContentsMargins(0, 0, 0, 0)
        second_ticker_stocks_layout.setSpacing(8)
        second_ticker_stocks_layout.addWidget(make_row_label("Second Ticker Stocks:"))
        second_ticker_stocks_layout.addWidget(stock_file_container)
        second_ticker_stocks_layout.addStretch(1)
        appearance_layout.addWidget(second_ticker_stocks_row, 6, 0, 1, 2)

        # Connect checkbox to enable/disable controls
        self.enable_second_ticker_checkbox.stateChanged.connect(self.toggle_second_ticker_controls)

        layout.addWidget(appearance_group)
        
        # === VISUAL EFFECTS GROUP ===
        effects_group = QtWidgets.QGroupBox("✨ Visual Effects")
        effects_layout = QtWidgets.QGridLayout(effects_group)
        effects_layout.setSpacing(10)
        effects_layout.setContentsMargins(14, 20, 14, 14)
        effects_layout.setColumnStretch(0, 1)
        effects_layout.setColumnStretch(1, 1)

        def make_effect_field(label_text, content_widget):
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            row_layout.addWidget(make_row_label(label_text))
            row_layout.addWidget(content_widget)
            row_layout.addStretch(1)
            return row

        bloom_content = QtWidgets.QWidget()
        bloom_layout = QtWidgets.QHBoxLayout(bloom_content)
        bloom_layout.setContentsMargins(0, 0, 0, 0)
        bloom_layout.setSpacing(8)
        self.led_bloom_checkbox = QtWidgets.QCheckBox("LED Bloom/Glow Effect")
        self.led_bloom_checkbox.setChecked(self.settings.get("led_bloom_effect", True))
        bloom_layout.addWidget(self.led_bloom_checkbox)
        
        bloom_layout.addSpacing(pair_gap)
        intensity_label = QtWidgets.QLabel("Intensity:")
        intensity_label.setStyleSheet("color: #b0b0b0; font-size: 10px;")
        self.led_bloom_intensity_spin = QtWidgets.QSpinBox()
        self.led_bloom_intensity_spin.setRange(0, 100)
        self.led_bloom_intensity_spin.setValue(self.settings.get("led_bloom_intensity", 60))
        self.led_bloom_intensity_spin.setToolTip("Adjust bloom/glow intensity\n0% = Off | 50% = Subtle | 100% = Strong (non-linear)")
        self.led_bloom_intensity_spin.setFixedWidth(80)
        self.led_bloom_intensity_spin.setFixedHeight(input_height)
        bloom_layout.addWidget(intensity_label)
        bloom_layout.addWidget(self.led_bloom_intensity_spin)
        bloom_layout.addWidget(make_unit_label("%"))
        bloom_layout.addStretch()
        bloom_row = make_effect_field("Bloom:", bloom_content)
        
        ghost_content = QtWidgets.QWidget()
        ghost_row = QtWidgets.QHBoxLayout(ghost_content)
        ghost_row.setContentsMargins(0, 0, 0, 0)
        ghost_row.setSpacing(8)
        self.led_ghosting_checkbox = QtWidgets.QCheckBox("Motion Blur/Ghosting")
        self.led_ghosting_checkbox.setChecked(self.settings.get("led_ghosting_effect", True))
        ghost_row.addWidget(self.led_ghosting_checkbox)

        ghost_row.addSpacing(pair_gap)
        giz_label = QtWidgets.QLabel("Intensity:")
        giz_label.setStyleSheet("color: #b0b0b0; font-size: 10px;")
        ghost_row.addWidget(giz_label)

        self.led_ghost_intensity_spin = QtWidgets.QSpinBox()
        self.led_ghost_intensity_spin.setRange(0, 100)
        self.led_ghost_intensity_spin.setValue(self.settings.get("led_ghost_intensity", 50))
        self.led_ghost_intensity_spin.setToolTip("Controls ghost opacity and color strength. 0% = Off | 100% = Default")
        self.led_ghost_intensity_spin.setFixedWidth(80)
        self.led_ghost_intensity_spin.setFixedHeight(input_height)
        ghost_row.addWidget(self.led_ghost_intensity_spin)
        ghost_row.addWidget(make_unit_label("%"))
        ghost_row.addStretch()
        ghosting_row = make_effect_field("Ghosting:", ghost_content)

        self.effects_preview = EffectsPreviewWidget(self)

        self.led_icon_matrix_checkbox = QtWidgets.QCheckBox("LED Icon Matrix Overlay")
        self.led_icon_matrix_checkbox.setChecked(self.settings.get("led_icon_matrix", True))

        self.led_glass_glare_checkbox = QtWidgets.QCheckBox("Glass Cover with Glare")
        self.led_glass_glare_checkbox.setChecked(self.settings.get("led_glass_glare", True))

        self.global_text_glow_checkbox = QtWidgets.QCheckBox("Subtle Text Glow")
        self.global_text_glow_checkbox.setChecked(self.settings.get("global_text_glow", True))

        options_container = QtWidgets.QWidget()
        options_stack = QtWidgets.QVBoxLayout(options_container)
        options_stack.setContentsMargins(0, 0, 0, 0)
        options_stack.setSpacing(4)
        options_stack.addWidget(self.led_icon_matrix_checkbox)
        options_stack.addWidget(self.led_glass_glare_checkbox)
        options_stack.addWidget(self.global_text_glow_checkbox)
        options_row = make_effect_field("Options:", options_container)

        preview_container = QtWidgets.QWidget()
        preview_layout = QtWidgets.QHBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)
        preview_layout.addWidget(make_row_label("Preview:"))
        preview_layout.addWidget(self.effects_preview)
        preview_layout.addStretch()

        effects_layout.addWidget(bloom_row, 0, 0)
        effects_layout.addWidget(ghosting_row, 0, 1)
        effects_layout.addWidget(options_row, 1, 0, 1, 2)
        effects_layout.addWidget(preview_container, 2, 0, 1, 2)

        self.led_ghost_intensity_spin.valueChanged.connect(lambda v: self.effects_preview.set_params(ghost_intensity=v))
        self.led_bloom_intensity_spin.valueChanged.connect(lambda v: self.effects_preview.set_params(bloom_intensity=v))
        self.led_ghosting_checkbox.stateChanged.connect(lambda s: self.effects_preview.set_params(ghost_enabled=bool(s)))
        self.led_bloom_checkbox.stateChanged.connect(lambda s: self.effects_preview.set_params(bloom_enabled=bool(s)))
        self.led_icon_matrix_checkbox.stateChanged.connect(lambda _: self.effects_preview.update())
        self.led_glass_glare_checkbox.stateChanged.connect(lambda _: self.effects_preview.update())
        self.global_text_glow_checkbox.stateChanged.connect(lambda _: self.effects_preview.update())
        self.price_indicator_combo.currentIndexChanged.connect(lambda _: self.effects_preview.update())
        self.show_sparklines_checkbox.stateChanged.connect(lambda _: self.effects_preview.update())
        self.sparkline_position_combo.currentIndexChanged.connect(lambda _: self.effects_preview.update())
        self.sparkline_period_combo.currentIndexChanged.connect(lambda _: self.effects_preview.update())
        
        layout.addWidget(effects_group)
        
        # === SOUND & NETWORK (Side by side) ===
        misc_layout = QtWidgets.QHBoxLayout()
        misc_layout.setSpacing(12)
        
        # Sound checkbox
        sound_group = QtWidgets.QGroupBox("🔊 Sound")
        sound_layout = QtWidgets.QVBoxLayout(sound_group)
        sound_layout.setSpacing(10)
        sound_layout.setContentsMargins(14, 20, 14, 14)
        self.play_sound_checkbox = QtWidgets.QCheckBox("Play on Update")
        self.play_sound_checkbox.setChecked(self.settings.get("play_sound_on_update", True))
        sound_layout.addWidget(self.play_sound_checkbox)
        sound_layout.addStretch(1)
        sound_group.setMaximumWidth(170)
        misc_layout.addWidget(sound_group, 0)
        
        # Network settings (compact)
        net_group = QtWidgets.QGroupBox("🌐 Network")
        net_layout = QtWidgets.QVBoxLayout(net_group)
        net_layout.setSpacing(10)
        net_layout.setContentsMargins(14, 20, 14, 14)
        
        self.use_proxy_checkbox = QtWidgets.QCheckBox("Use Proxy")
        self.use_proxy_checkbox.setChecked(bool(self.settings.get("use_proxy", False)))
        net_layout.addWidget(self.use_proxy_checkbox)
        
        self.proxy_edit = QtWidgets.QLineEdit(self.settings.get("proxy", ""))
        self.proxy_edit.setPlaceholderText("http://proxy:port")
        self.proxy_edit.setEnabled(self.use_proxy_checkbox.isChecked())
        self.proxy_edit.setFixedHeight(input_height)
        self.use_proxy_checkbox.toggled.connect(self.proxy_edit.setEnabled)
        net_layout.addWidget(self.proxy_edit)
        
        self.use_cert_checkbox = QtWidgets.QCheckBox("Use Certificate")
        self.use_cert_checkbox.setChecked(bool(self.settings.get("use_cert", False)))
        net_layout.addWidget(self.use_cert_checkbox)
        
        cert_layout = QtWidgets.QHBoxLayout()
        self.cert_file_edit = QtWidgets.QLineEdit(self.settings.get("cert_file", ""))
        self.cert_file_edit.setPlaceholderText("certificate.pem")
        self.cert_file_edit.setEnabled(self.use_cert_checkbox.isChecked())
        self.cert_file_edit.setFixedHeight(input_height)
        self.cert_file_btn = QtWidgets.QPushButton("📁")
        self.cert_file_btn.setFixedWidth(32)
        self.cert_file_btn.setFixedHeight(input_height)
        self.cert_file_btn.setEnabled(self.use_cert_checkbox.isChecked())
        self.cert_file_btn.clicked.connect(self.browse_cert_file)
        self.use_cert_checkbox.toggled.connect(self.cert_file_edit.setEnabled)
        self.use_cert_checkbox.toggled.connect(self.cert_file_btn.setEnabled)
        cert_layout.addWidget(self.cert_file_edit)
        cert_layout.addWidget(self.cert_file_btn)
        net_layout.addLayout(cert_layout)
        
        misc_layout.addWidget(net_group, 1)
        layout.addLayout(misc_layout)
        
        # === BUTTONS ===
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Apply | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(QtWidgets.QDialogButtonBox.Apply).clicked.connect(self.apply_settings)
        
        # Style OK button with accent
        ok_button = btns.button(QtWidgets.QDialogButtonBox.Ok)
        make_accent_button(ok_button)
        
        # Style Apply button with success color
        apply_button = btns.button(QtWidgets.QDialogButtonBox.Apply)
        make_success_button(apply_button)
        
        layout.addWidget(btns)

    def toggle_key_visibility(self, line_edit, button):
        """Toggle API key visibility between hidden and revealed"""
        if line_edit.echoMode() == QtWidgets.QLineEdit.Password:
            line_edit.setEchoMode(QtWidgets.QLineEdit.Normal)
            button.setText("👁")
        else:
            line_edit.setEchoMode(QtWidgets.QLineEdit.Password)
            button.setText("👁")

    def browse_cert_file(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Certificate File", "", "Certificate Files (*.pem *.crt *.cer);;All Files (*)")
        if fname:
            self.cert_file_edit.setText(fname)

    def browse_second_ticker_stock_file(self):
        fname, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Stock File", "", "JSON Files (*.json);;All Files (*)")
        if fname:
            self.second_ticker_stock_file_edit.setText(fname)

    def _set_api_test_status(self, status_label, text, ok=None, auto_clear=False):
        status_label.setText(text)
        seq = int(status_label.property("status_seq") or 0) + 1
        status_label.setProperty("status_seq", seq)

        if ok is True:
            status_label.setStyleSheet("color: #21c55d; font-size: 11px; font-weight: 600;")
        elif ok is False:
            status_label.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: 600;")
        else:
            status_label.setStyleSheet("color: #9aa3b2; font-size: 11px;")

        if auto_clear:
            QtCore.QTimer.singleShot(5000, lambda lbl=status_label, s=seq: self._clear_api_test_status(lbl, s))

    def _clear_api_test_status(self, status_label, seq):
        if int(status_label.property("status_seq") or 0) != int(seq):
            return
        status_label.setText("")
        status_label.setStyleSheet("color: #9aa3b2; font-size: 11px;")

    def test_api_key(self, line_edit, key_label, status_label):
        """Test Finnhub API key and show result to user."""
        api_key = line_edit.text().strip()
        self._set_api_test_status(status_label, "Testing...", ok=None, auto_clear=False)
        QtWidgets.QApplication.processEvents()

        if not api_key:
            self._set_api_test_status(status_label, "Empty key", ok=False, auto_clear=True)
            QtWidgets.QMessageBox.warning(self, "API Key Test", f"{key_label} API key is empty.")
            return

        url = "https://finnhub.io/api/v1/quote"
        params = {"symbol": "AAPL", "token": api_key}
        headers = {"User-Agent": "TCKR/1.0"}

        proxies = None
        if self.use_proxy_checkbox.isChecked() and self.proxy_edit.text().strip():
            proxy = self.proxy_edit.text().strip()
            proxies = {"http": proxy, "https": proxy}

        verify = True
        if self.use_cert_checkbox.isChecked() and self.cert_file_edit.text().strip():
            verify = self.cert_file_edit.text().strip()

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=8,
                proxies=proxies,
                verify=verify
            )
        except Exception as e:
            self._set_api_test_status(status_label, "Failed", ok=False, auto_clear=True)
            QtWidgets.QMessageBox.critical(self, "API Key Test", f"Request failed: {e}")
            return

        if response.status_code != 200:
            self._set_api_test_status(status_label, f"HTTP {response.status_code}", ok=False, auto_clear=True)
            body_preview = (response.text or "").strip()[:200]
            QtWidgets.QMessageBox.warning(
                self,
                "API Key Test",
                f"HTTP {response.status_code} from Finnhub.\n\nResponse: {body_preview}"
            )
            return

        try:
            payload = response.json()
        except Exception:
            self._set_api_test_status(status_label, "Bad response", ok=False, auto_clear=True)
            QtWidgets.QMessageBox.warning(self, "API Key Test", "Endpoint returned non-JSON response.")
            return

        if isinstance(payload, dict) and payload.get("error"):
            self._set_api_test_status(status_label, "Invalid", ok=False, auto_clear=True)
            QtWidgets.QMessageBox.warning(self, "API Key Test", f"Finnhub error: {payload.get('error')}")
            return

        # Valid quote payloads include at least one standard quote key (e.g., current price 'c').
        if isinstance(payload, dict) and "c" in payload:
            self._set_api_test_status(status_label, "OK", ok=True, auto_clear=True)
            QtWidgets.QMessageBox.information(self, "API Key Test", f"{key_label} API key is valid (OK response).")
        else:
            self._set_api_test_status(status_label, "Unexpected", ok=False, auto_clear=True)
            QtWidgets.QMessageBox.warning(self, "API Key Test", "Unexpected response format from Finnhub endpoint.")

    def toggle_second_ticker_controls(self):
        enabled = self.enable_second_ticker_checkbox.isChecked()
        self.second_ticker_speed_spin.setEnabled(enabled)
        self.second_ticker_stock_file_edit.setEnabled(enabled)
        self.second_ticker_stock_browse_btn.setEnabled(enabled)


    def apply_settings(self):
        """Apply settings without closing dialog"""
        s = get_settings()
        s["transparency"] = self.transparency_spin.value()
        s["speed"] = self.scroll_speed_spin.value()
        s["ticker_height"] = self.ticker_height_spin.value()
        s["update_interval"] = self.update_interval_spin.value()
        s["screen_index"] = self.display_combo.currentIndex()
        s["price_indicator_style"] = self.price_indicator_combo.currentData()
        s["use_cert"] = self.use_cert_checkbox.isChecked()
        s["cert_file"] = self.cert_file_edit.text().strip()
        s["use_proxy"] = self.use_proxy_checkbox.isChecked()
        s["proxy"] = self.proxy_edit.text().strip()
        s["led_bloom_effect"] = self.led_bloom_checkbox.isChecked()
        s["led_bloom_intensity"] = self.led_bloom_intensity_spin.value()
        s["led_ghosting_effect"] = self.led_ghosting_checkbox.isChecked()
        # Store single ghost intensity (controls both color strength & alpha)
        s["led_ghost_intensity"] = self.led_ghost_intensity_spin.value()
        s["led_icon_matrix"] = self.led_icon_matrix_checkbox.isChecked()
        s["led_glass_glare"] = self.led_glass_glare_checkbox.isChecked()
        s["global_text_glow"] = self.global_text_glow_checkbox.isChecked()
        s["play_sound_on_update"] = self.play_sound_checkbox.isChecked()
        s["finnhub_api_key"] = self.finnhub_api_key_edit.text().strip()
        s["finnhub_api_key_2"] = self.finnhub_api_key_2_edit.text().strip()
        s["websocket_visual_refresh_seconds"] = self.ws_refresh_spin.value()
        s["enable_second_ticker"] = self.enable_second_ticker_checkbox.isChecked()
        s["second_ticker_speed"] = self.second_ticker_speed_spin.value()
        s["second_ticker_stock_file"] = self.second_ticker_stock_file_edit.text().strip()
        s["show_sparklines"] = self.show_sparklines_checkbox.isChecked()
        s["sparkline_period"] = self.sparkline_period_combo.currentData()
        s["sparkline_position"] = self.sparkline_position_combo.currentData()
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
            self.original_settings.get("finnhub_api_key_2") != s["finnhub_api_key_2"] or
            self.original_settings.get("websocket_visual_refresh_seconds") != s["websocket_visual_refresh_seconds"] or
            self.original_settings.get("enable_second_ticker") != s["enable_second_ticker"] or
            self.original_settings.get("second_ticker_stock_file") != s["second_ticker_stock_file"]
        )
        
        if self.tray_icon and hasattr(self.tray_icon, 'ticker_windows'):
            target_widgets = [w for w in self.tray_icon.ticker_windows if isinstance(w, TickerWindow)]
        else:
            app = QtWidgets.QApplication.instance()
            target_widgets = [w for w in app.topLevelWidgets() if isinstance(w, TickerWindow)]

        visual_or_style_changed = (
            self.original_settings.get("led_bloom_effect") != s["led_bloom_effect"] or
            self.original_settings.get("led_bloom_intensity") != s["led_bloom_intensity"] or
            self.original_settings.get("led_ghosting_effect") != s["led_ghosting_effect"] or
            self.original_settings.get("led_ghost_intensity") != s.get("led_ghost_intensity") or
            self.original_settings.get("led_icon_matrix") != s["led_icon_matrix"] or
            self.original_settings.get("led_glass_glare") != s["led_glass_glare"] or
            self.original_settings.get("global_text_glow") != s["global_text_glow"] or
            self.original_settings.get("price_indicator_style") != s["price_indicator_style"]
        )

        for widget in target_widgets:
                if major_changes:
                    # Signal that ticker needs to be restarted
                    self.needs_restart = True
                else:
                    # Apply simple changes without restart
                    if self.original_settings.get("update_interval") != s["update_interval"]:
                        widget.apply_update_interval()

                    # If the global primary speed changed, apply it ONLY to primary ticker windows
                    if self.original_settings.get("speed") != s["speed"]:
                        if not getattr(widget, 'is_second_ticker', False):
                            widget.apply_speed()

                    # If second ticker speed changed, apply it ONLY to second ticker windows
                    if self.original_settings.get("second_ticker_speed") != s.get("second_ticker_speed"):
                        if getattr(widget, 'is_second_ticker', False):
                            widget.scroll_speed = float(max(1, s.get("second_ticker_speed", 2)))
                            # Force an immediate visual update so the new speed takes effect
                            try:
                                if hasattr(widget, 'gl_widget') and widget.gl_widget:
                                    widget.gl_widget.update()
                            except Exception:
                                pass

                    if self.original_settings.get("transparency") != s["transparency"]:
                        widget.apply_transparency()
                    if self.original_settings.get("play_sound_on_update") != s["play_sound_on_update"]:
                        pass  # Sound setting doesn't need immediate action
                    
                    # Check if any visual effects changed
                    if visual_or_style_changed:
                        # Instantly apply visual effect changes by updating cached settings and triggering repaint
                        new_cached = {
                            'bloom': s.get("led_bloom_effect", True),
                            'ghosting': s.get("led_ghosting_effect", True),
                            'glass': s.get("led_glass_glare", True)
                        }
                        widget._cached_effect_settings = new_cached

                        # Reset settings cache time so any other cached helpers will reload
                        widget._settings_cache_time = 0
                        widget._cached_settings = s.copy()

                        # Rebuild ticker text if global_text_glow changed (affects text rendering)
                        if self.original_settings.get("global_text_glow") != s["global_text_glow"]:
                            widget.build_ticker_text(reset_scroll=False)

                        # Rebuild ticker pixmaps if price indicator style changed
                        if self.original_settings.get("price_indicator_style") != s["price_indicator_style"]:
                            widget.build_ticker_pixmaps()

                    # Rebuild pixmaps if ghost intensity or ghosting toggled (cached ghost pixmaps must be regenerated)
                    if (self.original_settings.get("led_ghost_intensity") != s.get("led_ghost_intensity") or
                        self.original_settings.get("led_ghosting_effect") != s.get("led_ghosting_effect")):
                        widget.build_ticker_pixmaps()

                    # Apply sparkline settings immediately (no restart required)
                    if (self.original_settings.get("show_sparklines", False) != s.get("show_sparklines", False) or
                        self.original_settings.get("sparkline_period", "1d") != s.get("sparkline_period", "1d") or
                        self.original_settings.get("sparkline_position", "left") != s.get("sparkline_position", "left")):
                        widget.show_sparklines = s.get("show_sparklines", False)
                        widget.sparkline_period = s.get("sparkline_period", "1d")
                        widget.sparkline_position = s.get("sparkline_position", "left")
                        if hasattr(widget, 'sparkline_cache'):
                            widget.sparkline_cache.clear()
                        if hasattr(widget, 'sparkline_inflight'):
                            widget.sparkline_inflight.clear()
                        widget.build_ticker_pixmaps()

                    # Force immediate repaint to show new visual effects
                    widget.gl_widget.update()
                    print("[SETTINGS] Visual effects applied instantly")

        # Keep dual-ticker placement stable after appearance-only rebuilds
        if not major_changes and visual_or_style_changed and self.tray_icon and hasattr(self.tray_icon, 'ticker_windows'):
            for i, ticker in enumerate([w for w in self.tray_icon.ticker_windows if isinstance(w, TickerWindow)]):
                QtCore.QTimer.singleShot(30 * i, ticker.ensure_top_position)
        
        # Update original_settings to current values for next apply
        self.original_settings = s.copy()
        
        # Set flag to indicate if restart is needed
        if not hasattr(self, 'needs_restart'):
            self.needs_restart = False

    def accept(self):
        """Apply settings and close dialog"""
        self.apply_settings()
        super().accept()

class PriceFetchWorker(QtCore.QThread):
    prices_fetched = QtCore.pyqtSignal(dict)
    def __init__(self, tickers, api_key, api_key_2=None):
        super().__init__()
        self.tickers = tickers
        self.api_key = api_key
        self.api_key_2 = api_key_2
    def run(self):
        print(f"[WORKER] PriceFetchWorker thread started")
        prices = fetch_all_stock_prices(self.tickers, self.api_key, self.api_key_2)
        print(f"[WORKER] PriceFetchWorker emitting prices signal")
        self.prices_fetched.emit(prices)

class PixmapRebuildWorker(QtCore.QThread):
    """Background worker to rebuild ticker pixmaps without blocking the main render loop"""
    pixmaps_ready = QtCore.pyqtSignal(list, list, list)  # pixmaps, widths, area_templates
    
    def __init__(self, ticker_window):
        super().__init__()
        self.ticker_window = ticker_window
        
    def run(self):
        """Build ticker pixmaps in background thread"""
        try:
            colored_print("[PIXMAP WORKER] Building ticker pixmaps in background...")
            
            # Build pixmaps (this is the expensive operation)
            # We need to call the window's build_ticker_pixmaps_internal method
            # which does all the work but doesn't set the window's attributes
            pixmaps, widths, areas = self.ticker_window.build_ticker_pixmaps_background()
            
            # Emit the completed pixmaps
            colored_print(f"[PIXMAP WORKER] Built {len(pixmaps)} pixmaps, emitting signal")
            self.pixmaps_ready.emit(pixmaps, widths, areas)
        except Exception as e:
            colored_print(f"[PIXMAP WORKER] Error building pixmaps: {e}")

class TickerGLWidget(QtWidgets.QWidget):  # Changed from QOpenGLWidget to QWidget
    def __init__(self, parent):
        super().__init__(parent)
        self.ticker_window = parent
        self.setMouseTracking(True)
        
        # Enable continuous rendering for smooth animation - let VSync handle frame pacing
        # This is simpler and more reliable than trying to time frames ourselves
        self.continuous_rendering = True
        
        # Enable double buffering for smooth rendering
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WA_PaintOnScreen, False)  # Use double buffer, not direct painting
        self.setAttribute(QtCore.Qt.WA_NativeWindow, False)   # Prevent native window creation overhead
        self.setAttribute(QtCore.Qt.WA_DontCreateNativeAncestors, True)  # Optimize rendering
        
        # Set update behavior for immediate, non-synced updates
        self.setAttribute(QtCore.Qt.WA_UpdatesDisabled, False)
        self.setUpdatesEnabled(True)
        
        # Visual effects toggle (enabled by default, user can toggle with button)
        self.effects_enabled = True
        
        colored_print(f"[PERF] Using continuous rendering with VSync for smooth scrolling")
        
    def paintEvent(self, event):
        # Track when paintEvent is called vs when it finishes
        if not hasattr(self, '_paint_call_time'):
            self._paint_call_time = 0
            self._paint_delay_warnings = 0
            self._last_paint_time = 0
        
        import time
        call_time = time.perf_counter()
        delay = (call_time - self._paint_call_time) * 1000 if self._paint_call_time > 0 else 0
        
        # Check if Windows is delaying our paint events
        if delay > 25 and self._paint_call_time > 0:
            self._paint_delay_warnings += 1
            if self._paint_delay_warnings % 60 == 1:
                print(f"[PAINT DELAY] Windows delaying paintEvent: {delay:.1f}ms")
        
        self.ticker_window.paint_ticker(self)
        self._paint_call_time = call_time
        
        # Continuous rendering with tight FPS cap for smooth scrolling
        if self.continuous_rendering:
            # Target slightly higher to compensate for overhead and hit true 60 FPS
            target_interval = 1.0 / 61.5  # ~16.26ms - compensates for paint overhead
            current_time = time.perf_counter()
            elapsed = current_time - self._last_paint_time
            
            if elapsed < target_interval:
                # Sleep for the full remaining time to hit target FPS
                sleep_time = target_interval - elapsed
                if sleep_time > 0.001:
                    time.sleep(sleep_time)
            
            self._last_paint_time = time.perf_counter()
            self.update()
            
    def mousePressEvent(self, event):
        self.ticker_window.ticker_mousePressEvent(event)
    def enterEvent(self, event):
        self.ticker_window.enterEvent(event)
    def leaveEvent(self, event):
        self.ticker_window.leaveEvent(event)
        self.unsetCursor()
    def mouseMoveEvent(self, event):
        pos = event.pos()
        # Check if ticker_click_areas exists before accessing
        if hasattr(self.ticker_window, 'ticker_click_areas'):
            for _, _, rect in self.ticker_window.ticker_click_areas:
                if rect.contains(pos):
                    self.setCursor(QtCore.Qt.PointingHandCursor)
                    break
            else:
                self.unsetCursor()
        else:
            self.unsetCursor()

class TrayIcon(QtWidgets.QSystemTrayIcon):
    def __init__(self, parent, ticker_window):
        icon_path = os.path.join(os.path.dirname(__file__), "TCKR.ico")
        icon = QtGui.QIcon(icon_path) if os.path.exists(icon_path) else parent.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon)
        super().__init__(icon, parent)
        self.ticker_windows = [ticker_window]  # List of all ticker windows
        self.primary_ticker = ticker_window  # Primary ticker for coordination

        # Create tray menu
        menu = QtWidgets.QMenu()
        self.settings_action = menu.addAction("Settings...")
        self.stocks_action = menu.addAction("Manage Stocks...")
        menu.addSeparator()
        self.pause_action = menu.addAction("Pause Scrolling")
        self.pause_action.setCheckable(True)
        self.pause_action.setChecked(False)  # Not paused by default
        self.fetch_now_action = menu.addAction("🔄 Fetch Prices Now")
        menu.addSeparator()
        self.effects_action = menu.addAction("Use Visual Effects (Bloom/Glow/Glass)")
        self.effects_action.setCheckable(True)
        self.effects_action.setChecked(True)  # Enabled by default

        # Websocket status action
        self.websocket_status_action = menu.addAction("📊 Show WebSocket Status")
        menu.addSeparator()

        # Load overlay settings from file
        settings = get_settings()
        self.fps_overlay_action = menu.addAction("Show FPS Overlay")
        self.fps_overlay_action.setCheckable(True)
        self.fps_overlay_action.setChecked(settings.get('show_fps_overlay', False))
        self.update_countdown_action = menu.addAction("Show Update Countdown")
        self.update_countdown_action.setCheckable(True)
        self.update_countdown_action.setChecked(settings.get('show_update_countdown', False))
        menu.addSeparator()
        self.about_action = menu.addAction("About...")
        menu.addSeparator()
        self.exit_action = menu.addAction("Exit")

        self.setContextMenu(menu)
        self.settings_action.triggered.connect(self.show_settings)
        self.stocks_action.triggered.connect(self.show_manage_stocks)
        self.pause_action.triggered.connect(self.toggle_pause)
        self.fetch_now_action.triggered.connect(self.fetch_prices_now)
        self.effects_action.triggered.connect(self.toggle_effects)
        self.websocket_status_action.triggered.connect(self.show_websocket_status)
        self.fps_overlay_action.triggered.connect(self.toggle_fps_overlay)
        self.update_countdown_action.triggered.connect(self.toggle_update_countdown)
        self.about_action.triggered.connect(self.show_about)
        self.exit_action.triggered.connect(self.safe_exit)
        self.activated.connect(self.on_activated)

    def add_ticker_window(self, ticker_window):
        """Add a ticker window to the managed list"""
        if ticker_window not in self.ticker_windows:
            self.ticker_windows.append(ticker_window)
            ticker_window.tray_icon = self

    def remove_ticker_window(self, ticker_window):
        """Remove a ticker window from the managed list"""
        if ticker_window in self.ticker_windows:
            self.ticker_windows.remove(ticker_window)
            # If removing primary, promote another
            if ticker_window == self.primary_ticker and self.ticker_windows:
                self.primary_ticker = self.ticker_windows[0]

    def toggle_fps_overlay(self):
        """Toggle FPS overlay on/off"""
        if hasattr(self.primary_ticker, 'show_fps_overlay'):
            # Toggle the overlay
            current_state = self.primary_ticker.show_fps_overlay
            self.primary_ticker.show_fps_overlay = not current_state

            # Update the menu item checkmark
            self.fps_overlay_action.setChecked(not current_state)

            # Save to settings
            settings = get_settings()
            settings['show_fps_overlay'] = not current_state
            save_settings(settings)

            # Update all ticker windows
            for ticker in self.ticker_windows:
                if hasattr(ticker, 'show_fps_overlay'):
                    ticker.show_fps_overlay = not current_state

            # Print status
            status = "enabled" if not current_state else "disabled"
            print(f"[FPS OVERLAY] FPS overlay {status}")

    def toggle_update_countdown(self):
        """Toggle update countdown overlay on/off"""
        if hasattr(self.primary_ticker, 'show_update_countdown'):
            # Toggle the overlay
            current_state = self.primary_ticker.show_update_countdown
            self.primary_ticker.show_update_countdown = not current_state

            # Update the menu item checkmark
            self.update_countdown_action.setChecked(not current_state)

            # Save to settings
            settings = get_settings()
            settings['show_update_countdown'] = not current_state
            save_settings(settings)

            # Update all ticker windows
            for ticker in self.ticker_windows:
                if hasattr(ticker, 'show_update_countdown'):
                    ticker.show_update_countdown = not current_state

            # Print status
            status = "enabled" if not current_state else "disabled"
            print(f"[UPDATE COUNTDOWN] Update countdown overlay {status}")

    def toggle_pause(self):
        """Toggle pause/resume scrolling"""
        if hasattr(self.primary_ticker, 'paused'):
            # Toggle the pause state
            self.primary_ticker.paused = not self.primary_ticker.paused

            # Update the menu item checkmark
            self.pause_action.setChecked(self.primary_ticker.paused)

            # Update all ticker windows
            for ticker in self.ticker_windows:
                if hasattr(ticker, 'paused'):
                    ticker.paused = self.primary_ticker.paused

            # Print status
            status = "paused" if self.primary_ticker.paused else "resumed"
            colored_print(f"[PAUSE] Scrolling {status}")
    
    def fetch_prices_now(self):
        """Force an immediate fetch of stock prices"""
        if hasattr(self.primary_ticker, 'update_prices_inplace'):
            print("[FETCH NOW] User requested immediate price update")
            # Pass force=True to override any backoff period
            self.primary_ticker.update_prices_inplace(force=True)
            # Reset the countdown timer
            self.primary_ticker.last_api_update_time = time.time()
        else:
            print("[FETCH NOW] Error: primary_ticker does not have update_prices_inplace method")
    
    def toggle_effects(self):
        """Toggle visual effects on/off"""
        if hasattr(self.primary_ticker, 'gl_widget') and self.primary_ticker.gl_widget:
            # Toggle the effects
            current_state = self.primary_ticker.gl_widget.effects_enabled
            self.primary_ticker.gl_widget.effects_enabled = not current_state

            # Update the menu item checkmark
            self.effects_action.setChecked(not current_state)

            # Update all ticker windows
            for ticker in self.ticker_windows:
                if hasattr(ticker, 'gl_widget') and ticker.gl_widget:
                    ticker.gl_widget.effects_enabled = not current_state
            
            # Print status
            status = "enabled" if not current_state else "disabled"
            print(f"[EFFECTS] Visual effects {status}")

    def show_websocket_status(self):
        """Show detailed websocket connection status"""
        if not hasattr(self.primary_ticker, 'websocket_client') or not self.primary_ticker.websocket_client:
            QtWidgets.QMessageBox.information(
                self.primary_ticker,
                "WebSocket Status",
                "WebSocket client is not initialized.\n\n"
                "WebSockets are used for real-time data during market hours.\n"
                "Make sure you have a Finnhub API key configured."
            )
            return

        client = self.primary_ticker.websocket_client
        status = client.get_debug_status()

        market_open = getattr(self.primary_ticker, '_market_is_open', False)
        finnhub_count = len([s for s in self.primary_ticker.stocks if not s.startswith('^')])

        status_msg = "📊 WebSocket Connection Status\n\n"
        status_msg += f"Market Status: {'🕐 Open' if market_open else '🌙 Closed'}\n"
        status_msg += f"Connection: {'✅ Connected' if status['connected'] else '❌ Disconnected'}\n"
        status_msg += f"Subscribed Symbols: {status['subscribed_symbols']}\n"
        status_msg += f"Finnhub Stocks: {finnhub_count} (Free tier: 50 max)\n\n"

        if status['connected']:
            status_msg += "📈 Real-Time Activity:\n"
            status_msg += f"• Messages Received: {status['messages_received']}\n"
            status_msg += f"• Price Updates: {status['price_updates_processed']}\n"
            status_msg += f"• Connection Time: {status['connection_duration']:.1f}s\n"
            if status['time_since_last_message'] < 60:
                status_msg += f"• Last Message: {status['time_since_last_message']:.1f}s ago\n"
            else:
                status_msg += f"• Last Message: {status['time_since_last_message']/60:.1f}min ago ⚠️\n"
        else:
            status_msg += "📈 Session Totals:\n"
            status_msg += f"• Total Messages: {status['messages_received']}\n"
            status_msg += f"• Total Updates: {status['price_updates_processed']}\n"
            status_msg += f"• Reconnections: {status['reconnection_count']}\n"
            status_msg += f"• Total Connected Time: {status['total_connection_time']:.1f}s\n"

        if finnhub_count > 50:
            status_msg += "\n⚠️ WARNING: Exceeding free tier limits!\n"
            status_msg += "Consider upgrading to paid plan to avoid rate limiting."

        QtWidgets.QMessageBox.information(self.primary_ticker, "WebSocket Status", status_msg)

    def show_settings(self):
        # Reuse existing modeless settings dialog if it's already open
        if hasattr(self, '_settings_dialog') and self._settings_dialog and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return

        dlg = SettingsDialog(self.primary_ticker, tray_icon=self)
        dlg.setModal(False)
        dlg.setWindowModality(QtCore.Qt.NonModal)

        def _on_settings_accepted():
            # Only restart ticker if major changes were made
            if getattr(dlg, 'needs_restart', False):
                self._restart_tickers_from_settings()
            # If no major changes, the settings were already applied directly to the existing window

        def _clear_settings_dialog(_result):
            self._settings_dialog = None

        dlg.accepted.connect(_on_settings_accepted)
        dlg.finished.connect(_clear_settings_dialog)
        self._settings_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _create_new_window_after_cleanup(self, old_window):
        """Create new window after ensuring old appbar is properly cleaned up"""
        old_window.close()
        self._create_new_window_immediately()

    def _restart_tickers_from_settings(self):
        """Rebuild all ticker windows from settings to avoid stale window overlap/state."""
        existing_windows = list(getattr(self, 'ticker_windows', []))
        if not existing_windows and getattr(self, 'primary_ticker', None):
            existing_windows = [self.primary_ticker]

        # First pass: hide + remove appbar reservations
        for window in existing_windows:
            try:
                if not window:
                    continue
                window.hide()
                if sys.platform == "win32":
                    remove_appbar(int(window.winId()))
            except Exception:
                pass

        # Second pass: close windows and clear registry
        for window in existing_windows:
            try:
                if window:
                    window.close()
            except Exception:
                pass

        self.ticker_windows = []
        self.primary_ticker = None

        # Let Windows settle appbar/work-area changes before creating new windows
        delay_ms = 350 if sys.platform == "win32" else 0
        QtCore.QTimer.singleShot(delay_ms, self._create_new_window_immediately)

    def _create_new_window_immediately(self):
        """Create and configure the new ticker window"""
        settings = get_settings()
        new_window = TickerWindow()
        new_window.is_second_ticker = False
        new_window.set_transparency(settings.get("transparency", 100))
        new_window.scroll_speed = settings.get("speed", 2)
        new_window.ticker_height = settings.get("ticker_height", 60)
        new_window.setFixedHeight(new_window.ticker_height)
        new_window.update_font_and_label()
        new_window.build_ticker_pixmaps()
        new_window.gl_widget.setGeometry(0, 0, new_window.width(), new_window.ticker_height)
        new_window.gl_widget.update()
        new_window.update_timer.setInterval(settings.get("update_interval", 300) * 1000)

        # Restore overlay states from settings (they're already loaded in __init__ but update menu checkmarks)
        self.fps_overlay_action.setChecked(getattr(new_window, 'show_fps_overlay', False))
        self.update_countdown_action.setChecked(getattr(new_window, 'show_update_countdown', False))

        # Window should already be positioned correctly by setup_appbar_and_position
        # No need for additional ensure_top_position call

        # Register as primary in managed list before creating optional secondary
        self.add_ticker_window(new_window)
        self.primary_ticker = new_window
        self.primary_ticker.tray_icon = self

        # Handle second ticker creation/destruction based on current settings
        self._handle_second_ticker_restart(settings)

    def _handle_second_ticker_restart(self, settings):
        """Handle second ticker creation/destruction during restart based on settings"""
        enable_second_ticker = settings.get("enable_second_ticker", False)
        current_window_count = len(self.ticker_windows)

        # If we currently have multiple ticker windows (second ticker exists)
        if current_window_count > 1:
            if not enable_second_ticker:
                # Second ticker should be disabled - destroy extra windows
                print("[RESTART] Disabling second ticker - destroying extra windows")
                # Keep only the primary ticker (first one)
                windows_to_close = self.ticker_windows[1:]
                for window in windows_to_close:
                    window.close()
                    self.remove_ticker_window(window)
            # If second ticker should remain enabled, keep the existing windows
            return

        # If we don't have multiple windows but second ticker should be enabled
        if enable_second_ticker and current_window_count == 1:
            print("[RESTART] Enabling second ticker - creating new second window")
            try:
                # Create second ticker window
                second_ticker_window = TickerWindow()
                second_ticker_window.is_second_ticker = True  # Mark as second ticker

                # Stop the timer that was started in __init__ - secondary tickers don't run their own timers
                if hasattr(second_ticker_window, 'update_timer') and second_ticker_window.update_timer.isActive():
                    second_ticker_window.update_timer.stop()

                # Ensure critical attributes are initialized (defensive programming)
                if not hasattr(second_ticker_window, 'loading'):
                    second_ticker_window.loading = True
                if not hasattr(second_ticker_window, 'show_fps_overlay'):
                    second_ticker_window.show_fps_overlay = settings.get('show_fps_overlay', False)
                if not hasattr(second_ticker_window, 'show_update_countdown'):
                    second_ticker_window.show_update_countdown = settings.get('show_update_countdown', False)

                # Apply second ticker specific settings
                second_ticker_window.scroll_speed = float(max(1, settings.get("second_ticker_speed", 2)))

                # Load stocks from second ticker stock file if specified, otherwise use same as main
                stock_file = settings.get("second_ticker_stock_file", "").strip()
                if stock_file and os.path.exists(stock_file):
                    try:
                        with open(stock_file, "r") as f:
                            second_stocks = json.load(f)
                        second_ticker_window.stocks = [s[0] for s in second_stocks]
                        print(f"[RESTART] Loaded {len(second_ticker_window.stocks)} stocks from custom file")
                    except Exception as e:
                        print(f"[RESTART] Failed to load custom stock file: {e}, using main stocks")
                        second_ticker_window.stocks = self.primary_ticker.stocks.copy()
                else:
                    second_ticker_window.stocks = self.primary_ticker.stocks.copy()
                    print(f"[RESTART] Using same stocks as main ticker ({len(second_ticker_window.stocks)} stocks)")

                # Build ticker display
                second_ticker_window.build_ticker_pixmaps()
                second_ticker_window.build_ticker_text(reset_scroll=True)

                # Apply main ticker settings (except speed which is customized)
                second_ticker_window.set_transparency(settings.get("transparency", 100))
                second_ticker_window.ticker_height = settings.get("ticker_height", 60)
                second_ticker_window.setFixedHeight(second_ticker_window.ticker_height)
                second_ticker_window.update_font_and_label()

                # Connect to websocket if available (same as main ticker)
                if hasattr(self.primary_ticker, 'websocket_client') and self.primary_ticker.websocket_client:
                    second_ticker_window.websocket_client = self.primary_ticker.websocket_client
                    # Primary ticker will subscribe to all symbols from all tickers

                # Register the new window
                self.add_ticker_window(second_ticker_window)
                second_ticker_window.show()

                print("[RESTART] Second ticker created and shown successfully")

            except Exception as e:
                print(f"[RESTART] Failed to create second ticker: {e}")

    def show_manage_stocks(self):
        # Reuse existing modeless Manage Stocks dialog if it's already open
        if hasattr(self, '_manage_stocks_dialog') and self._manage_stocks_dialog and self._manage_stocks_dialog.isVisible():
            self._manage_stocks_dialog.raise_()
            self._manage_stocks_dialog.activateWindow()
            return

        dlg = ManageStocksDialog(self.primary_ticker)
        dlg.setModal(False)
        dlg.setWindowModality(QtCore.Qt.NonModal)

        def _on_manage_stocks_accepted():
            # Reload stocks from file and rebuild display with existing prices
            # Don't trigger immediate fetch to avoid 429 errors - let normal update cycle handle it
            import time as time_module
            self.primary_ticker.stocks = [s[0] for s in load_stocks()]
            self.primary_ticker.build_ticker_text(reset_scroll=True)
            # Reset the countdown timer so it doesn't get stuck at 0
            self.primary_ticker.last_api_update_time = time_module.time()

            # Update all ticker windows with new stock list
            for ticker in self.ticker_windows:
                if ticker != self.primary_ticker:
                    ticker.stocks = self.primary_ticker.stocks.copy()
                    ticker.build_ticker_text(reset_scroll=True)

            print("[MANAGE STOCKS] Stock list updated for all tickers - will fetch new prices on next scheduled update")

        def _clear_manage_stocks_dialog(_result):
            self._manage_stocks_dialog = None

        dlg.accepted.connect(_on_manage_stocks_accepted)
        dlg.finished.connect(_clear_manage_stocks_dialog)
        self._manage_stocks_dialog = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def show_about(self):
        # Reuse existing modeless About dialog if it's already open
        if hasattr(self, '_about_dialog') and self._about_dialog and self._about_dialog.isVisible():
            self._about_dialog.raise_()
            self._about_dialog.activateWindow()
            return

        # Modern About dialog
        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("ℹ️ About TCKR")
        dialog.setModal(False)
        dialog.setWindowModality(QtCore.Qt.NonModal)
        apply_modern_theme(dialog)
        dialog.setMinimumWidth(450)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)
        
        # Title with icon
        title = QtWidgets.QLabel("📈 TCKR")
        # Load SubwayTicker font if available and apply it
        font_path = resource_path("SubwayTicker.ttf")
        if os.path.exists(font_path):
            font_id = QtGui.QFontDatabase.addApplicationFont(font_path)
            families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
            if families:
                title_font = QtGui.QFont(families[0])
                title.setFont(title_font)
                title.setStyleSheet("font-size: 36px; font-weight: bold; color: #00b3ff; qproperty-alignment: AlignCenter;")
            else:
                title.setStyleSheet("font-family: Arial; font-size: 36px; font-weight: bold; color: #00b3ff; qproperty-alignment: AlignCenter;")
        else:
            title.setStyleSheet("font-family: Arial; font-size: 36px; font-weight: bold; color: #00b3ff; qproperty-alignment: AlignCenter;")
        layout.addWidget(title)
        
        # Version
        version = QtWidgets.QLabel("Version 1.0.2026.0212.1214")
        version.setStyleSheet("font-size: 12px; color: #b0b0b0; qproperty-alignment: AlignCenter;")
        layout.addWidget(version)
        
        # Description
        desc = QtWidgets.QLabel("A simple and powerful scrolling LED stock ticker application.")
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11px; color: #e0e0e0; qproperty-alignment: AlignCenter; margin: 8px 0;")
        layout.addWidget(desc)
        
        # Information group
        info_group = QtWidgets.QGroupBox("📋 Information")
        info_layout = QtWidgets.QVBoxLayout(info_group)
        info_layout.setSpacing(8)
        info_layout.setContentsMargins(16, 20, 16, 16)
        
        copyright_label = QtWidgets.QLabel("© 2026 Paul R. Charovkine. All rights reserved.")
        copyright_label.setStyleSheet("font-size: 10px; color: #b0b0b0;")
        info_layout.addWidget(copyright_label)
        
        license_label = QtWidgets.QLabel("Licensed under the AGPL-3.0 license.")
        license_label.setStyleSheet("font-size: 10px; color: #b0b0b0;")
        info_layout.addWidget(license_label)
        
        # Links
        links_label = QtWidgets.QLabel(
            '<a href="https://github.com/krypdoh/TCKR" style="color: #00b3ff;">GitHub Repository</a>'
        )
        links_label.setOpenExternalLinks(True)
        links_label.setStyleSheet("font-size: 11px; margin-top: 8px;")
        info_layout.addWidget(links_label)
        
        # Data providers
        providers_label = QtWidgets.QLabel(
            'Financial data powered by:<br>'
            '<a href="https://finnhub.io" style="color: #00b3ff;">Finnhub.io</a> • '
            '<a href="https://coingecko.com" style="color: #00b3ff;">CoinGecko</a>'
        )
        providers_label.setOpenExternalLinks(True)
        providers_label.setWordWrap(True)
        providers_label.setStyleSheet("font-size: 10px; color: #b0b0b0; margin-top: 8px;")
        info_layout.addWidget(providers_label)
        
        # Donation request
        donate_label = QtWidgets.QLabel(
            'Please consider <a href="https://paypal.me/paypaulc" style="color: #00b3ff;">Donating!</a>'
        )
        donate_label.setOpenExternalLinks(True)
        donate_label.setStyleSheet("font-size: 11px; color: #e0e0e0; margin-top: 12px; font-weight: 600;")
        info_layout.addWidget(donate_label)
        
        layout.addWidget(info_group)
        
        # Close button
        close_btn = QtWidgets.QPushButton("✓ Close")
        make_accent_button(close_btn)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        def _clear_about_dialog(_result):
            self._about_dialog = None

        dialog.finished.connect(_clear_about_dialog)
        self._about_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def safe_exit(self):
        """Safely exit the application with proper AppBar cleanup"""
        print("[EXIT] Safe exit initiated - cleaning up AppBar registration")

        # Close all ticker windows to trigger AppBar cleanup
        windows_closed = 0
        for ticker in list(self.ticker_windows):
            if ticker and not ticker.isHidden():
                ticker.close()
                windows_closed += 1

        if windows_closed > 0:
            # Give Windows a moment to process the AppBar removal
            # Use a timer to delay the actual quit to ensure cleanup completes
            QtCore.QTimer.singleShot(100, self.delayed_quit)
        else:
            # No ticker windows, just quit directly
            QtWidgets.qApp.quit()
    
    def delayed_quit(self):
        """Complete the application exit after AppBar cleanup"""
        print("[EXIT] AppBar cleanup completed, exiting application")
        QtWidgets.qApp.quit()

    def on_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            # Show the primary ticker if available, otherwise fall back to the first managed window
            target = getattr(self, 'primary_ticker', None)
            if not target and self.ticker_windows:
                target = self.ticker_windows[0]
            if target:
                target.showNormal()
                target.raise_()
                target.activateWindow()

class SplashScreen(QtWidgets.QWidget):
    """
    Loading splash screen displayed on program launch.
    Shows 'TCKR' in gold subway font with LED board background.
    """
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint | 
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        # Center splash screen on primary monitor
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        splash_width = 600
        splash_height = 200
        self.setGeometry(
            (screen.width() - splash_width) // 2,
            (screen.height() - splash_height) // 2,
            splash_width,
            splash_height
        )
        
        # Load subway font for TCKR text
        font_path = resource_path("SubwayTicker.ttf")
        if os.path.exists(font_path):
            font_id = QtGui.QFontDatabase.addApplicationFont(font_path)
            families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
            if families:
                self.splash_font = QtGui.QFont(families[0], 80)
                self.splash_font.setBold(True)
            else:
                self.splash_font = QtGui.QFont("Arial", 80, QtGui.QFont.Bold)
        else:
            self.splash_font = QtGui.QFont("Arial", 80, QtGui.QFont.Bold)
        
        self.start_time = time.time()
        
    def paintEvent(self, event):
        """Draw the splash screen with LED board background and gold TCKR text"""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        
        width = self.width()
        height = self.height()
        
        # Draw rounded rectangle background with LED board style
        rect = QtCore.QRectF(0, 0, width, height)
        
        # Create realistic LED board background with depth
        base_color = QtGui.QColor(8, 10, 12)
        painter.setBrush(QtGui.QBrush(base_color))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 20, 20)
        
        # Add subtle vertical gradient for depth
        depth_grad = QtGui.QLinearGradient(0, 0, 0, height)
        depth_grad.setColorAt(0, QtGui.QColor(15, 18, 22, 180))
        depth_grad.setColorAt(0.5, QtGui.QColor(12, 14, 18, 120))
        depth_grad.setColorAt(1, QtGui.QColor(8, 10, 14, 160))
        painter.setBrush(QtGui.QBrush(depth_grad))
        painter.drawRoundedRect(rect, 20, 20)
        
        # Add horizontal scanlines (LED matrix rows)
        painter.setClipRect(rect)
        scanline_color = QtGui.QColor(0, 0, 0, 80)
        scanline_highlight = QtGui.QColor(25, 30, 38, 40)
        for y in range(0, height, 4):
            painter.fillRect(0, y, width, 2, scanline_color)
            if y + 2 < height:
                painter.fillRect(0, y + 2, width, 1, scanline_highlight)
        
        # Add subtle LED pixel grid pattern
        pixel_grid_color = QtGui.QColor(18, 22, 28, 30)
        for x in range(0, width, 6):
            painter.fillRect(x, 0, 1, height, pixel_grid_color)
        
        painter.setClipping(False)
        
        # Draw "TCKR" text in gold
        painter.setFont(self.splash_font)
        text = "TCKR"
        
        # Calculate text position (centered)
        metrics = QtGui.QFontMetrics(self.splash_font)
        text_width = metrics.horizontalAdvance(text)
        text_height = metrics.height()
        text_x = (width - text_width) // 2
        text_y = (height + text_height) // 2 - metrics.descent()
        
        # Draw gold text (simple, no glow)
        painter.setPen(QtGui.QColor(255, 215, 0))  # Gold
        painter.drawText(text_x, text_y, text)

class TickerWindow(QtWidgets.QWidget):
    FLASH_DURATION_MS = 400
    _instance_counter = 0  # Class variable to track instance numbers
    sparkline_ready = QtCore.pyqtSignal(str, object, int, int, str)  # symbol, pixmap, w, h, period

    def __init__(self, is_secondary=False):
        super().__init__()
        settings = get_settings()
        
        # CRITICAL FIX: Force Windows system timer resolution to 1ms for smooth animation
        # Other apps (Chrome, games, etc.) can change timer resolution and not restore it
        # This causes persistent stuttering even after those apps close
        if sys.platform == "win32":
            try:
                import ctypes
                # timeBeginPeriod forces Windows to use 1ms timer resolution
                # This is critical for smooth 60 FPS animation
                winmm = ctypes.windll.winmm
                resolution = ctypes.c_uint(1)  # 1ms resolution
                result = winmm.timeBeginPeriod(resolution)
                if result == 0:  # TIMERR_NOERROR
                    colored_print(f"[PERF] Windows timer resolution set to 1ms for smooth animation")
                    self._timer_period_set = True
                else:
                    print(f"[PERF] Could not set timer resolution: {result}")
                    self._timer_period_set = False
            except Exception as e:
                print(f"[PERF] Could not set timer resolution: {e}")
                self._timer_period_set = False

            # --- Incremental pixmap rebuild queue (throttle across frames) ---
            # Pending symbols to rebuild (preserves order, prevents duplicates)
            self._pending_pixmap_list = []
            self._pending_pixmap_set = set()

            # Throttle parameters (defaults can be overridden via settings)
            settings = get_settings()
            self.incremental_rebuild_interval_ms = settings.get('websocket_incremental_interval_ms', 30)
            self.incremental_rebuild_max_per_tick = settings.get('websocket_incremental_max_per_tick', 6)

            # Timer that processes a small batch of symbol pixmap rebuilds per tick
            self.incremental_rebuild_timer = QtCore.QTimer(self)
            self.incremental_rebuild_timer.timeout.connect(self._process_incremental_rebuild_tick)
            self.incremental_rebuild_timer.setTimerType(QtCore.Qt.PreciseTimer)

            # Debug flags are OFF by default to avoid render-thread stutter from logging/overlays
            self._ghost_debug_visual = False
            self._ghost_debug_logging = False

            # Debug: optional test mode to force ghost pixmaps to a vivid, fully-opaque tint
            # Set to True to make ghost pixmaps visually obvious while debugging, then
            # set back to False to restore normal behavior once the issue is diagnosed
            self._ghost_debug_force_visible = False
            self._ghost_debug_force_tint = QtGui.QColor(255, 0, 255, 200)
        else:
            self._timer_period_set = False
        
        # Boost process priority to prevent stuttering when other apps are active
        if sys.platform == "win32":
            try:
                import psutil
                process = psutil.Process()
                # Set to ABOVE_NORMAL priority for smooth rendering
                process.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
                colored_print(f"[PERF] Process priority set to ABOVE_NORMAL for smooth rendering")
            except ImportError:
                print(f"[PERF] psutil not available - install with 'pip install psutil' for better priority")
            except Exception as e:
                print(f"[PERF] Could not set process priority: {e}")
            
            # CRITICAL: Disable Windows timer coalescing for this process
            # When other windows minimize/maximize, Windows coalesces timers to save power
            # This causes our animation timer to fire irregularly (stuttering)
            # Setting timer tolerances to 0 prevents coalescing
            try:
                import ctypes
                ntdll = ctypes.windll.ntdll
                # NtSetTimerResolution is already called via timeBeginPeriod
                # But we also need to disable timer coalescing tolerance
                kernel32 = ctypes.windll.kernel32
                
                # Get current process handle
                current_process = kernel32.GetCurrentProcess()
                
                # PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
                # PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION = 0x4
                # Disable power throttling to prevent timer coalescing
                
                # Use SetProcessInformation to disable power throttling (Windows 10+)
                # This prevents Windows from coalescing our timers when other apps are active
                PROCESS_INFORMATION_CLASS_PowerThrottling = 4
                
                class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
                    _fields_ = [
                        ('Version', ctypes.c_ulong),
                        ('ControlMask', ctypes.c_ulong),
                        ('StateMask', ctypes.c_ulong),
                    ]
                
                throttling = PROCESS_POWER_THROTTLING_STATE()
                throttling.Version = 1  # PROCESS_POWER_THROTTLING_CURRENT_VERSION
                throttling.ControlMask = 0x3  # Control execution speed and timer resolution
                throttling.StateMask = 0  # 0 = disable throttling
                
                # Try to call SetProcessInformation (Windows 10 1709+)
                try:
                    kernel32.SetProcessInformation(
                        current_process,
                        PROCESS_INFORMATION_CLASS_PowerThrottling,
                        ctypes.byref(throttling),
                        ctypes.sizeof(throttling)
                    )
                    colored_print(f"[PERF] Disabled Windows power throttling - timers won't be coalesced")
                except Exception as e:
                    # Older Windows version - not available
                    print(f"[PERF] Power throttling control not available (Windows 10 1709+ required)")
            except Exception as e:
                print(f"[PERF] Could not disable timer coalescing: {e}")
        
        # Enable VSync for smooth rendering (reduces tearing and stuttering)
        fmt = QtGui.QSurfaceFormat()
        fmt.setSwapInterval(1)  # 1 = VSync on, 0 = VSync off
        fmt.setSwapBehavior(QtGui.QSurfaceFormat.DoubleBuffer)
        QtGui.QSurfaceFormat.setDefaultFormat(fmt)
        colored_print(f"[PERF] VSync enabled for smooth rendering")
        
        # Assign unique instance ID and set window title for identification
        TickerWindow._instance_counter += 1
        self.instance_id = TickerWindow._instance_counter
        self.setWindowTitle(f"TCKR-{self.instance_id}")
        colored_print(f"[INIT] Creating ticker instance #{self.instance_id}")
        colored_print(f"[PERF] VSync enabled for smooth rendering")
        
        # Track when we last set the work area to ignore feedback notifications
        self._last_work_area_set_time = 0
        
        self.setContentsMargins(0, 0, 0, 0)
        self.ticker_height = get_settings().get("ticker_height", 60)
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |  # Keep on top to prevent overlap
            QtCore.Qt.WindowDoesNotAcceptFocus  # Don't steal focus - reduces compositor interference
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)  # Reduce compositor overhead
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)  # Optimization hint
        self.setFixedHeight(self.ticker_height)

        # Historical mini-sparklines (toggleable for performance)
        self.show_sparklines = bool(settings.get("show_sparklines", False))
        self.sparkline_period = settings.get("sparkline_period", "1d")
        self.sparkline_position = settings.get("sparkline_position", "left")
        self.sparkline_cache = {}  # key: (symbol, period, w, h) -> (timestamp, QPixmap)
        self.sparkline_inflight = set()  # keys currently being fetched
        self.sparkline_lock = threading.Lock()
        self.sparkline_rebuild_interval_ms = 350  # batch sparkline redraws to avoid stutter
        self.sparkline_rebuild_timer = QtCore.QTimer(self)
        self.sparkline_rebuild_timer.setSingleShot(True)
        self.sparkline_rebuild_timer.timeout.connect(self._process_sparkline_rebuild_tick)
        self._sparkline_logged_success = set()  # one-time success diagnostics
        self._sparkline_logged_failures = set()  # one-time failure diagnostics
        self.sparkline_ready.connect(self._on_sparkline_ready)

        self.icon_cache = {}
        self.icon_cache_limit = 100  # Limit cache size to prevent memory bloat
        self.icon_cache_hits = 0
        self.icon_cache_misses = 0
        self.current_icon_size = None  # Track current icon size for cache management
        
        # BLOOM CACHE: Cache the bloom layer to avoid redrawing gradients every frame
        self.bloom_cache = None  # Will store pre-rendered bloom pixmap
        self.bloom_cache_offset = 0.0  # Track scroll offset for cache invalidation
        self.bloom_cache_valid = False  # Flag to rebuild cache when needed
        
        # Initialize performance counters at startup to avoid hasattr checks in render loop
        self._fps_counter = 0
        self._fps_last_calc = 0
        self._current_fps = 0.0
        self._current_frame_time = 0.0
        self.ticker_click_areas = []
        
        # Cache time module to avoid import overhead in render loop
        import time as time_module
        self._time_module = time_module
        
        self.update_font_and_label()
        # Load stocks - load_stocks() already returns them sorted with ^ symbols first
        self.stocks = [s[0] for s in load_stocks()]
        colored_print(f"[INIT] Loaded stocks in order: {self.stocks}")
        self.prices = {}
        self.prev_prices = {}
        self.price_flash_times = {}
        self.pulse_effects = {}
        self.glow_baseline_prices = {}  # Track the price that triggered each glow
        self.glow_history = {}  # Track prev_close values that already triggered glows
        self.ticker_text = ""
        self.offset = 0.0  # Use float for sub-pixel smooth scrolling
        self.scroll_speed = float(max(1, get_settings().get("speed", 1)))  # Float for fractional speeds
        self.update_interval = get_settings().get("update_interval", 300) * 1000  # seconds to ms
        # Slightly reduce interval to account for system overhead when other apps active
        self.timer_interval = 15  # 15ms gives ~66 FPS, accounting for system overhead
        self.paused = False  # Pause scrolling via context menu
        self.is_paused = False  # Pause scrolling when mouse hovers (kept for backwards compatibility)
        
        # Frame timing for smooth animation (import time module to avoid shadowing later)
        import time as time_module
        self.last_frame_time = time_module.perf_counter()
        # target_frame_interval will be set after refresh rate detection
        self.ticker_pixmaps = []
        self.ticker_pixmap_widths = []
        self.gl_widget = TickerGLWidget(self)
        self.gl_widget.setGeometry(0, 0, self.width(), self.ticker_height)
        self.gl_widget.show()
        
        # Boost timer thread priority on Windows for smoother updates
        if sys.platform == "win32":
            try:
                import ctypes
                # Get current thread handle
                kernel32 = ctypes.windll.kernel32
                thread_handle = kernel32.GetCurrentThread()
                # Set thread priority to TIME_CRITICAL for animation timer
                # THREAD_PRIORITY_HIGHEST = 2, THREAD_PRIORITY_TIME_CRITICAL = 15
                kernel32.SetThreadPriority(thread_handle, 2)  # HIGHEST priority
                print(f"[PERF] Timer thread priority boosted for smooth animation")
            except Exception as e:
                print(f"[PERF] Could not boost thread priority: {e}")
        
        # Lock to 60 FPS for consistent, stutter-free scrolling
        # Auto-detection was causing jitter on variable refresh rate displays
        target_fps = 60
        frame_interval = 16  # 16ms = ~60 FPS
        print(f"[PERF] Locked to 60 FPS for consistent scrolling (interval: {frame_interval}ms)")
        
        # REMOVED: High-precision render thread - replaced with VSync continuous rendering
        # The render thread was fighting with VSync causing stutter
        # New approach: paintEvent() calls update() continuously, VSync throttles naturally
        # This is what TCKR.py uses and it scrolls smoothly
        
        # Store target FPS for frame time calculations (VSync will enforce this)
        self.target_fps = target_fps
        self.target_frame_interval = 1.0 / target_fps
        
        # Trigger initial render, then paintEvent keeps it going continuously
        self.gl_widget.update()
        print(f"[PERF] VSync continuous rendering enabled - bypasses timer issues")
        
        self.update_timer = QtCore.QTimer(self)
        self.update_timer.timeout.connect(self.update_prices_inplace)
        self.update_timer.start(self.update_interval)
        
        # Market status update timer - check every minute for market open/close changes
        self.market_status_timer = QtCore.QTimer(self)
        self.market_status_timer.timeout.connect(self.update_market_status)
        self.market_status_timer.start(60000)  # Check every 60 seconds
        
        # DISABLED: Memory cleanup timer - gc.collect() can cause frame drops
        # Memory will be managed by Python's automatic garbage collector
        # self.memory_cleanup_timer = QtCore.QTimer(self)
        # self.memory_cleanup_timer.timeout.connect(self.cleanup_memory_periodically)
        # self.memory_cleanup_timer.start(600000)  # 10 minutes
        
        # DISABLED: Glow cleanup timer was causing scroll stuttering every second
        # Glow effects will now persist until next price update (every 5 minutes)
        # This eliminates the periodic pixmap rebuilds that caused stuttering
        # self.glow_cleanup_timer = QtCore.QTimer(self)
        # self.glow_cleanup_timer.timeout.connect(self.cleanup_expired_glow_effects)
        # self.glow_cleanup_timer.start(1000)

        # Initialize websocket client for real-time data during market hours
        self.websocket_client = None
        self.last_websocket_check = 0
        self.websocket_enabled = WEBSOCKET_AVAILABLE
        colored_print(f"[WEBSOCKET] Websocket enabled: {self.websocket_enabled}")

        if self.websocket_enabled:
            api_key = ensure_finnhub_api_key(self)
            colored_print(f"[WEBSOCKET] API key available: {api_key is not None}")
            if api_key:
                self.websocket_client = FinnhubWebSocketClient(api_key, self)
                colored_print("[WEBSOCKET] ✅ Initialized websocket client for real-time data")
                
                # Create batch processing timer in main thread with LOW PRIORITY
                # This ensures rendering always takes precedence over WebSocket processing
                settings = get_settings()
                batch_interval = settings.get('websocket_batch_interval', 150)
                # ZERO-INTERRUPTION MODE: User choice - smooth vs real-time
                # Option 1: Never refresh visuals (perfectly smooth, but prices only update via API every 10min)
                # Option 2: Refresh every 15-30s (small stutter, but prices stay current)
                refresh_interval = settings.get('websocket_visual_refresh_seconds', 0)  # 0 = disabled
                
                if refresh_interval > 0:
                    self.websocket_visual_timer = QtCore.QTimer(self)
                    self.websocket_visual_timer.timeout.connect(self.refresh_websocket_visuals_deferred)
                    self.websocket_visual_timer.start(refresh_interval * 1000)
                    self.websocket_visual_timer.setTimerType(QtCore.Qt.VeryCoarseTimer)
                    colored_print(f"[WEBSOCKET] 🎨 Visual refresh enabled: every {refresh_interval}s (will cause brief stutter)")
                else:
                    colored_print("[WEBSOCKET] 🎨 Visual refresh DISABLED for zero interruption (prices update only via API fetch)")
                
                self.websocket_has_updates = False
                # Process only a small number of symbols per visual tick to protect frame pacing
                self._websocket_batch_size = int(settings.get('websocket_max_symbols_per_refresh', 4))
                # Delay between follow-up slices when buffer is still non-empty
                self._websocket_slice_delay_ms = int(settings.get('websocket_slice_delay_ms', 30))
                self._websocket_busy = False
                
                # Check for cost warnings after initialization
                QtCore.QTimer.singleShot(2000, self.check_websocket_cost_startup)
            else:
                colored_print("[WEBSOCKET] ❌ No API key available - websocket features disabled")

    # Batch processing removed - all processing happens during visual refresh
    # for zero interruption to scrolling
    
    def refresh_websocket_visuals(self):
        """Process WebSocket buffer AND rebuild ticker (zero-interruption mode)"""
        # Step 1: Check if processing is needed BEFORE we process
        if not hasattr(self, 'websocket_client') or not self.websocket_client:
            return
        
        # CRITICAL: Skip if we're currently busy rendering (smoothness first!)
        if getattr(self, '_websocket_busy', False):
            return  # Skip this update, try again next time
        
        # Check if buffer has data
        has_buffered_data = bool(self.websocket_client.price_buffer)
        if not has_buffered_data:
            return  # Nothing to process
        
        # Step 2: Process only a small batch each tick to avoid UI hitching
        batch_size = max(1, int(getattr(self, '_websocket_batch_size', 4)))
        if getattr(self, 'show_sparklines', False):
            # Full rebuilds are heavier with sparklines; use smaller slices
            batch_size = min(batch_size, 2)
        
        # Set busy flag to prevent concurrent updates
        self._websocket_busy = True
        try:
            updates_sent, updated_symbols = self.websocket_client.process_buffered_updates(max_symbols=batch_size)

            # Step 3: Rebuild visual display for only changed symbols
            if updates_sent > 0 and not self.loading and self.stocks:
                # Perform incremental pixmap rebuild for changed symbols across ALL ticker windows
                try:
                    targets = self.tray_icon.ticker_windows if hasattr(self, 'tray_icon') and self.tray_icon else [self]
                    for ticker in targets:
                        # Filter symbols to those the ticker actually displays
                        relevant = [s for s in updated_symbols if hasattr(ticker, 'stocks') and s in ticker.stocks]
                        if not relevant:
                            continue
                        try:
                            # Queue incremental rebuilds so we throttle work across frames
                            ticker.queue_incremental_pixmap_updates(relevant)
                        except Exception:
                            # Fall back to full rebuild for that ticker
                            ticker.build_ticker_text(reset_scroll=False)
                except Exception:
                    # Global fallback: rebuild primary ticker fully
                    self.build_ticker_text(reset_scroll=False)
                self.websocket_has_updates = False
                if hasattr(self, '_websocket_refresh_count'):
                    self._websocket_refresh_count += 1
                else:
                    self._websocket_refresh_count = 1

                # Keep console output light to protect frame pacing
                if self._websocket_refresh_count % 10 == 0:
                    colored_print(f"[WEBSOCKET] 🎨 Visual refresh #{self._websocket_refresh_count}: updated {updates_sent} symbols")

            # If there is still buffered data, process another small slice soon
            if self.websocket_client and self.websocket_client.price_buffer:
                delay_ms = max(10, int(getattr(self, '_websocket_slice_delay_ms', 30)))
                QtCore.QTimer.singleShot(delay_ms, self.refresh_websocket_visuals_deferred)
        finally:
            self._websocket_busy = False
    
    def refresh_websocket_visuals_deferred(self):
        """Deferred visual refresh - schedules rebuild for next idle period"""
        # Always check buffer and process if needed
        # Schedule rebuild with low priority (only runs when idle)
        QtCore.QTimer.singleShot(0, self.refresh_websocket_visuals)
    
    def check_websocket_cost_startup(self):
        """Check for websocket cost warnings on startup and connect if market is open"""
        if not WEBSOCKET_AVAILABLE or not self.websocket_client:
            return

        num_stocks = len(self.stocks)
        finnhub_stocks = len([s for s in self.stocks if not s.startswith('^')])

        # Free tier limits: 50 websocket symbols, 60 API calls/minute
        if finnhub_stocks > 50:
            colored_print(f"[WEBSOCKET] ⚠️ COST WARNING: You have {finnhub_stocks} stocks (free tier limit: 50)")
            colored_print("[WEBSOCKET] You may incur charges during market hours:")
            colored_print("[WEBSOCKET] • $0.01/minute connection time")
            colored_print("[WEBSOCKET] • $0.02 per 1,000 trade messages")
            colored_print("[WEBSOCKET] Consider upgrading to Finnhub paid plan or reducing stocks")
        elif finnhub_stocks > 40:
            colored_print(f"[WEBSOCKET] Note: You have {finnhub_stocks} stocks. Free tier supports up to 50 symbols.")

        # Force a market hours check at startup to ensure _market_is_open is set
        self.get_smart_update_interval()

        # Check if market is open and connect websocket if needed
        market_open = getattr(self, '_market_is_open', False)
        colored_print(f"[WEBSOCKET] Startup check: market_open={market_open}, websocket_connected={self.websocket_client.connected if self.websocket_client else 'no client'}")

        if market_open and self.websocket_client and not self.websocket_client.connected:
            colored_print("[WEBSOCKET] 🕐 Market detected as OPEN at startup - connecting to real-time data")
            if self.websocket_client.connect():
                # Subscribe to current stocks
                finnhub_symbols = [s for s in self.stocks if not s.startswith('^')]
                if finnhub_symbols:
                    colored_print(f"[WEBSOCKET] Subscribing to {len(finnhub_symbols)} symbols at startup: {finnhub_symbols[:5]}{'...' if len(finnhub_symbols) > 5 else ''}")
                    self.websocket_client.subscribe_symbols(finnhub_symbols)
                else:
                    colored_print("[WEBSOCKET] No Finnhub symbols to subscribe to at startup")
            else:
                colored_print("[WEBSOCKET] ❌ Failed to connect websocket at startup")
        elif not market_open:
            colored_print("[WEBSOCKET] 🌙 Market detected as CLOSED at startup - websockets will connect when market opens")
        elif self.websocket_client and self.websocket_client.connected:
            colored_print("[WEBSOCKET] ✅ Websocket already connected at startup")

        # PERF ENHANCEMENT 4: Register window instance for icon caching
        get_ticker_icon._window_instance = self
        
        # Show "TCKR: Loading" until first API batch completes
        self.loading = True
        
        # FPS overlay toggle (load from settings)
        settings = get_settings()
        self.show_fps_overlay = settings.get('show_fps_overlay', False)
        
        # Update countdown overlay toggle (load from settings)
        self.show_update_countdown = settings.get('show_update_countdown', False)
        import time as time_module
        self.last_api_update_time = time_module.time()  # Track when last API update occurred
        
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
            colored_print(f"[INIT] Total screens available: {len(screens)}, requested screen_index: {screen_index}")
            if 0 <= screen_index < len(screens):
                screen = screens[screen_index]
                colored_print(f"[INIT] Using screen at index {screen_index}")
            else:
                screen = app.primaryScreen()
                print(f"[INIT] Screen index out of range, using primary screen")
            
            rect = screen.geometry()
            colored_print(f"[INIT] Screen geometry: left={rect.left()}, top={rect.top()}, width={rect.width()}, height={rect.height()}")
            
            # Also check available geometry (excludes taskbars, etc.)
            avail_rect = screen.availableGeometry()
            colored_print(f"[INIT] Available geometry: left={avail_rect.left()}, top={avail_rect.top()}, width={avail_rect.width()}, height={avail_rect.height()}")
            
            colored_print(f"[INIT] Setting window geometry to: x={rect.left()}, y={rect.top()}, width={rect.width()}, height={self.ticker_height}")
            
            # Use setGeometry to set position and size together - more reliable than separate move/resize
            self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
            
            # Verify geometry after setGeometry
            geom = self.geometry()
            colored_print(f"[INIT] Window geometry after setGeometry(): x={geom.x()}, y={geom.y()}, width={geom.width()}, height={geom.height()}")
            
            # CRITICAL: Check for other tickers BEFORE showing this window
            # This prevents the brief moment where both tickers are at y=0 causing Windows to reposition things
            colored_print(f"[INIT] Checking for other tickers before showing window...")
            
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
                WS_EX_NOACTIVATE = 0x08000000  # Don't activate when clicked - CRITICAL for preventing DWM events
                
                # Get current extended style
                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                
                # Add our desired styles - INCLUDE WS_EX_NOACTIVATE to prevent focus stealing
                # This prevents Windows DWM from throttling our rendering when other windows are interacted with
                new_ex_style = ex_style | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
                
                # Set the new extended style
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
                colored_print(f"[INIT] Set extended window style: 0x{new_ex_style:08X}")
                
                # CRITICAL: Disable DWM throttling for this window
                # Windows throttles non-focused windows to ~10 FPS to save resources
                # This causes stuttering when other windows are minimized/maximized/focused
                try:
                    import ctypes.wintypes as wintypes
                    dwmapi = ctypes.windll.dwmapi
                    
                    # DWMWA_EXCLUDED_FROM_PEEK = 12 (exclude from Aero Peek)
                    # DWMWA_CLOAK = 13 (don't cloak/hide during animations)
                    # DWMWA_FREEZE_REPRESENTATION = 14 (don't freeze during animations)
                    
                    # Disable DWM clocking during window animations (prevents freezing/stuttering)
                    DWMWA_CLOAK = 13
                    cloak_value = ctypes.c_int(0)  # 0 = don't cloak
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        DWMWA_CLOAK,
                        ctypes.byref(cloak_value),
                        ctypes.sizeof(cloak_value)
                    )
                    
                    # Exclude from Aero Peek (prevents DWM from capturing/compositing during peek)
                    DWMWA_EXCLUDED_FROM_PEEK = 12
                    peek_value = ctypes.c_int(1)  # 1 = exclude
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        DWMWA_EXCLUDED_FROM_PEEK,
                        ctypes.byref(peek_value),
                        ctypes.sizeof(peek_value)
                    )
                    
                    # CRITICAL: Disable DWM render throttling (DWMWA_DISALLOW_PEEK = 11)
                    # This prevents Windows from throttling our FPS when other windows are active
                    DWMWA_DISALLOW_PEEK = 11
                    disallow_peek = ctypes.c_int(1)  # 1 = disallow
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        DWMWA_DISALLOW_PEEK,
                        ctypes.byref(disallow_peek),
                        ctypes.sizeof(disallow_peek)
                    )
                    
                    # NUCLEAR OPTION: Tell Windows this is a video/media window
                    # DWM will NOT throttle media windows even when not focused
                    # This uses undocumented DWMWA flags that video players use
                    try:
                        # DWMWA_HAS_ICONIC_BITMAP = 10 (tells DWM we handle our own thumbnails)
                        # This disables DWM's automatic thumbnail generation which causes throttling
                        DWMWA_HAS_ICONIC_BITMAP = 10
                        has_bitmap = ctypes.c_int(1)
                        dwmapi.DwmSetWindowAttribute(
                            hwnd,
                            DWMWA_HAS_ICONIC_BITMAP,
                            ctypes.byref(has_bitmap),
                            ctypes.sizeof(has_bitmap)
                        )
                        
                        # Force the window to be excluded from DWM composition throttling
                        # by marking it as "always compose at full rate"
                        DWMWA_FORCE_ICONIC_REPRESENTATION = 7
                        force_iconic = ctypes.c_int(0)  # 0 = don't use iconic representation
                        dwmapi.DwmSetWindowAttribute(
                            hwnd,
                            DWMWA_FORCE_ICONIC_REPRESENTATION,
                            ctypes.byref(force_iconic),
                            ctypes.sizeof(force_iconic)
                        )
                        colored_print(f"[PERF] Set media window flags - DWM will not throttle rendering")
                    except:
                        pass  # Older Windows might not support these
                    
                    colored_print(f"[PERF] DWM optimizations applied - disabled throttling and peek interference")
                except Exception as e:
                    print(f"[PERF] Could not apply DWM optimizations: {e}")
            
            # Force position again after show - sometimes Qt repositions on show()
            self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
            
            # Verify position after show
            pos = self.pos()
            geom = self.geometry()
            colored_print(f"[INIT] Window position after show(): x={pos.x()}, y={pos.y()}")
            colored_print(f"[INIT] Window geometry after show(): x={geom.x()}, y={geom.y()}, width={geom.width()}, height={geom.height()}")

            # Visibility probe: ensure window is actually visible; if not, try opaque fallback
            if not self.isVisible():
                colored_print("[INIT] Warning: Ticker window not visible after show(), applying opaque fallback")
                try:
                    self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
                    self.show()
                    QtWidgets.QApplication.processEvents()
                    pos2 = self.pos(); geom2 = self.geometry()
                    colored_print(f"[INIT] After fallback - visible={self.isVisible()}, pos={pos2.x()},{pos2.y()}, geom={geom2.x()},{geom2.y()},{geom2.width()},{geom2.height()}")
                except Exception as e:
                    colored_print(f"[INIT] Opaque fallback failed: {e}")
            
            colored_print("[TCKR] Initialized with comprehensive performance optimizations")  # Single startup message
            
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
        
        # Force at least one render to display "TCKR: Loading" before starting API calls
        colored_print("[TCKR] Displaying loading screen...")
        QtWidgets.QApplication.processEvents()  # Process pending events to ensure window is rendered
        self.gl_widget.update()  # Trigger immediate paint
        QtWidgets.QApplication.processEvents()  # Process the paint event
        
        # Start fetching real prices in the background AFTER loading screen is displayed
        colored_print("[TCKR] Starting progressive initialization...")
        
        # PERF ENHANCEMENT 8: Use progressive startup loading for faster initialization
        self.progressive_startup_init()
        
        # Remove immediate calls - now handled by progressive loading
        # QtCore.QTimer.singleShot(100, self.update_prices_full)
        # QtCore.QTimer.singleShot(2000, self.preload_icons_async)
        
        self.failed_fetch_counts = {}
        

    # ========== PERFORMANCE ENHANCEMENT FUNCTIONS ==========
    
    def manage_icon_cache_lru(self):
        """Manage icon cache with LRU eviction to prevent memory bloat"""
        if len(self.icon_cache) > self.icon_cache_limit:
            # Remove oldest 20% of cache entries
            items_to_remove = len(self.icon_cache) - int(self.icon_cache_limit * 0.8)
            oldest_keys = list(self.icon_cache.keys())[:items_to_remove]
            for key in oldest_keys:
                del self.icon_cache[key]
            print(f"[PERF] Icon cache evicted {items_to_remove} entries (total: {len(self.icon_cache)})")
    
    def get_cached_settings(self):
        """Return render settings from in-memory cache (no periodic disk I/O)."""
        if not hasattr(self, '_cached_settings'):
            self._cached_settings = get_settings()

        settings = self._cached_settings
        return {
            'show_bloom': settings.get('led_bloom_effect', True),
            'show_glow': settings.get('global_text_glow', True),
            'show_glass': settings.get('led_glass_glare', True),
            'bloom_intensity': settings.get('led_bloom_intensity', 60),
            'show_fps_overlay': settings.get('show_fps_overlay', False)
        }
    
    def get_smart_update_interval(self):
        """Dynamically adjust update intervals based on market hours and activity"""
        if not hasattr(self, '_last_market_check'):
            self._last_market_check = 0
            self._market_is_open = True
            
        import time
        current_time = time.time()
        
        # Check market status every 5 minutes
        if current_time - self._last_market_check > 300:
            try:
                import datetime
                import pytz

                # Get current time in Eastern Time (ET)
                et_tz = pytz.timezone('US/Eastern')
                now_et = datetime.datetime.now(et_tz)
                today_et = now_et.date()

                # Check if today is a market holiday
                is_holiday = False
                try:
                    import pandas_market_calendars as mcal
                    nyse = mcal.get_calendar('NYSE')
                    # Check if market is open today (not a holiday)
                    schedule = nyse.schedule(start_date=today_et, end_date=today_et)
                    is_holiday = schedule.empty
                except ImportError:
                    # pandas-market-calendars not available, skip holiday check
                    pass
                except Exception as e:
                    colored_print(f"[MARKET] Holiday check failed: {e}")

                # Market hours: 9:30 AM - 4:00 PM ET, weekdays, not holidays
                market_open = (now_et.weekday() < 5 and  # Monday-Friday
                              not is_holiday and  # Not a holiday
                              9.5 <= now_et.hour + now_et.minute/60 <= 16)  # 9:30 AM - 4:00 PM

                self._market_is_open = market_open

                status_parts = []
                if is_holiday:
                    status_parts.append("HOLIDAY")
                elif now_et.weekday() >= 5:
                    status_parts.append("WEEKEND")
                else:
                    status_parts.append(now_et.strftime('%H:%M %Z'))

                if market_open:
                    interval = self.update_interval  # Normal 5-minute updates during market hours
                    colored_print(f"[MARKET] 🕐 Market OPEN - {', '.join(status_parts)} (5min updates)")
                else:
                    interval = max(self.update_interval * 3, 900000)  # 15+ minute updates after hours
                    status_reason = "CLOSED" if not is_holiday and now_et.weekday() < 5 else "CLOSED"
                    colored_print(f"[MARKET] 🌙 Market {status_reason} - {', '.join(status_parts)} (15min updates)")

                self._last_market_check = current_time
                return interval
            except ImportError:
                # Fallback if pytz not available - use local time (less accurate)
                import datetime
                now = datetime.datetime.now()
                if now.weekday() < 5 and 9.5 <= now.hour + now.minute/60 <= 16:
                    self._market_is_open = True
                    interval = self.update_interval
                    colored_print(f"[MARKET] 🕐 Market OPEN - {now.strftime('%H:%M')} local time (5min updates)")
                else:
                    self._market_is_open = False
                    interval = max(self.update_interval * 3, 900000)
                    colored_print(f"[MARKET] 🌙 Market CLOSED - {now.strftime('%H:%M')} local time (15min updates)")

                colored_print("[MARKET] ⚠️ pytz not available - using local time for market hours")
                self._last_market_check = current_time
                return interval
            except Exception as e:
                colored_print(f"[MARKET] Error checking market hours: {e}")
                return self.update_interval
        
        return self.update_interval * 3 if not self._market_is_open else self.update_interval
    
    def preload_icons_async(self):
        """Asynchronously preload all stock icons to improve responsiveness"""
        import concurrent.futures
        import threading
        
        def load_icon_background(ticker, size):
            try:
                get_ticker_icon(ticker, size)
            except Exception as e:
                print(f"[PERF] Background icon loading failed for {ticker}: {e}")
        
        # Calculate the icon size we'll actually use
        if USE_OPT:
            icon_size = opt.calculate_icon_size(self.ticker_height, 0.85)
        else:
            icon_size = int(self.ticker_height * 0.85)
        
        # Use a separate thread for icon preloading to avoid blocking UI
        def preload_worker():
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # Preload icons only for the current display size
                futures = []
                for ticker in self.stocks:
                    future = executor.submit(load_icon_background, ticker, icon_size)
                    futures.append(future)
                
                # Wait for all preloading to complete
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result(timeout=1)
                    except Exception:
                        pass  # Ignore individual failures
            
            print(f"[PERF] Background icon preloading completed for {len(self.stocks)} stocks at size {icon_size}")
        
        # Start preloading in background
        threading.Thread(target=preload_worker, daemon=True).start()
    
    def cleanup_memory_periodically(self):
        """Periodic memory cleanup to prevent memory leaks"""
        # Clean up icon cache if it's getting too large
        self.manage_icon_cache_lru()
        
        # Clear old pixmap references
        import gc
        gc.collect()
        
        # Log memory usage if available
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            if memory_mb > 200:  # Alert if using over 200MB
                print(f"[PERF] Memory usage: {memory_mb:.1f}MB (icon cache: {len(self.icon_cache)} items)")
            
            # If memory usage is very high, force more aggressive cleanup
            if memory_mb > 500:
                # Clear half the icon cache
                items_to_remove = len(self.icon_cache) // 2
                oldest_keys = list(self.icon_cache.keys())[:items_to_remove]
                for key in oldest_keys:
                    del self.icon_cache[key]
                print(f"[PERF] Emergency memory cleanup: removed {items_to_remove} cached icons")
        except ImportError:
            pass  # psutil not available
    
    def progressive_startup_init(self):
        """Load components progressively to improve startup time"""
        # Phase 1: Essential UI (already done in constructor)
        print("[STARTUP] Phase 1: UI initialized")
        
        # Phase 2: Load settings and prepare rendering (100ms delay)
        QtCore.QTimer.singleShot(100, self.startup_phase2)
    
    def startup_phase2(self):
        """Startup phase 2: Prepare rendering components"""
        # Pre-cache settings
        self.get_cached_settings()
        print("[STARTUP] Phase 2: Settings cached")
        
        # Phase 3: Start API calls (500ms delay)
        QtCore.QTimer.singleShot(500, self.startup_phase3)
    
    def startup_phase3(self):
        """Startup phase 3: Begin API operations"""
        # Start initial price fetch (only for primary ticker)
        if not getattr(self, 'is_second_ticker', False):
            self.update_prices_full()
            print("[STARTUP] Phase 3: Initial price fetch started")
        else:
            print("[STARTUP] Phase 3: Secondary ticker - skipping initial fetch")
        
        # Phase 4: Background optimizations (2s delay)
        QtCore.QTimer.singleShot(2000, self.startup_phase4)
    
    def startup_phase4(self):
        """Startup phase 4: Background optimizations"""
        # Start icon preloading
        self.preload_icons_async()
        print("[STARTUP] Phase 4: Background optimizations started")


    def ensure_top_position(self):
        """Ensure the ticker is positioned correctly (top for primary, target position for secondary)"""
        screen_index = get_settings().get("screen_index", 0)
        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        if 0 <= screen_index < len(screens):
            screen = screens[screen_index]
        else:
            screen = app.primaryScreen()
        rect = screen.geometry()

        # Check if this is a secondary ticker with a target position
        if hasattr(self, 'is_secondary_ticker') and self.is_secondary_ticker and hasattr(self, 'target_position_y'):
            # Secondary ticker - position at target location
            self.move(rect.left(), self.target_position_y)
            self.resize(rect.width(), self.ticker_height)
            print(f"[ENSURE TOP] Secondary ticker positioned at y={self.target_position_y}")
            return

        # Primary ticker - force to top of screen
        self.move(rect.left(), rect.top())
        self.resize(rect.width(), self.ticker_height)

        # Use aggressive positioning on Windows
        if sys.platform == "win32":
            # Try multiple times to ensure we're at the top
            for attempt in range(5):
                final_top = force_window_to_top(int(self.winId()), rect, self.ticker_height)
                print(f"[ENSURE TOP] Attempt {attempt+1}: Target: {rect.top()}, Final: {final_top}")

                if final_top <= rect.top():
                    print(f"[ENSURE TOP] Successfully positioned at top on attempt {attempt+1}")
                    break

                # If not at top, wait a bit and try again
                if attempt < 4:  # Don't delay on the last attempt
                    QtCore.QTimer.singleShot(100, lambda: self.ensure_top_position())
                    break  # Exit the loop, the timer will retry

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
                colored_print(f"[INIT] No existing tickers found - will be primary")
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

                # Extract instance IDs from window titles to determine priority
                # TCKR-1, TCKR-2, etc. The lowest ID should be primary
                my_instance_id = self.instance_id
                other_instance_ids = []

                for ticker in ticker_windows:
                    title = ticker['title']
                    if title == "TCKR":
                        other_instance_ids.append(0)  # TCKR (no number) is instance 0
                    elif title.startswith("TCKR-") and title[5:].isdigit():
                        other_instance_ids.append(int(title[5:]))
                    else:
                        other_instance_ids.append(999)  # Fallback

                min_other_id = min(other_instance_ids) if other_instance_ids else 999

                print(f"[COORDINATE] My instance ID: {my_instance_id}, lowest other ID: {min_other_id}")

                if my_instance_id <= min_other_id:
                    # We have the lowest or equal ID - we should be primary
                    print(f"[COORDINATE] I have lowest/equal ID - positioning as primary at top")
                    return False  # Don't position as secondary
                else:
                    # There are tickers with lower IDs - we should be secondary
                    print(f"[COORDINATE] Other ticker has lower ID - positioning as secondary")
                    # Position right after the last ticker (sorted by position)
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
                # Position right after the last ticker
                new_top_physical = last_ticker['top'] + last_ticker['height']
                print(f"[COORDINATE] Last ticker at y={last_ticker['top']}, height={last_ticker['height']}")
                print(f"[COORDINATE] Positioning this ticker at physical y={new_top_physical}")

                # Convert physical pixels to logical pixels for Qt
                # Use the main ticker's position as reference since we know it's positioned correctly
                main_ticker_logical_y = 0  # Assume main ticker is at top
                main_ticker_logical_height = self.ticker_height

                # Position this ticker right below the main ticker
                new_top_logical = main_ticker_logical_y + main_ticker_logical_height
                print(f"[COORDINATE] Positioning at logical y={new_top_logical} (right below main ticker)")

                # IMPORTANT: Store the target position for use in setup_appbar_and_position
                self.target_position_y = new_top_logical

                # Move to the calculated position immediately (using logical pixels)
                self.move(screen_rect.left(), int(new_top_logical))
                
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
        import time
        start_time = time.time()
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
            if DEBUG_APPBAR: print(f"[APPBAR] Instance #{self.instance_id} is SECONDARY - no appbar operations")
            
            # Just ensure correct positioning (below other tickers)
            if hasattr(self, 'target_position_y'):
                self.setGeometry(rect.left(), self.target_position_y, rect.width(), self.ticker_height)
                if DEBUG_APPBAR: print(f"[APPBAR] Secondary ticker positioned at y={self.target_position_y}")
            return  # Exit early - no appbar operations for secondary tickers

        # Only reach here if we're the PRIMARY ticker
        if DEBUG_APPBAR: print(f"[APPBAR] Instance #{self.instance_id} is PRIMARY - setting up appbar")
        
        # Check if space is already reserved at the top (from a previous ticker)
        user32 = ctypes.windll.user32
        work_area = wintypes.RECT()
        user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0)  # SPI_GETWORKAREA
        existing_reservation = work_area.top - rect.top()
        
        if existing_reservation > 0:
            if DEBUG_APPBAR: print(f"[APPBAR] Space already reserved at top ({existing_reservation}px)")
            
            # CRITICAL: Get our actual physical window height for slot calculation
            # We need to use physical pixels, not logical pixels
            hwnd = int(self.winId())
            actual_window_rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(actual_window_rect))
            actual_window_height = actual_window_rect.bottom - actual_window_rect.top
            if DEBUG_APPBAR: print(f"[APPBAR] Our window: logical height={self.ticker_height}px, physical height={actual_window_height}px")
            
            # Calculate which slot we should be in using PHYSICAL height
            num_existing_slots = existing_reservation // actual_window_height
            if DEBUG_APPBAR: print(f"[APPBAR] Existing slots: {num_existing_slots} (using physical height {actual_window_height}px)")
            
            # We should be in the next slot
            our_slot = num_existing_slots
            target_y_physical = rect.top() + (our_slot * actual_window_height)
            
            # Convert physical pixels back to logical pixels for Qt
            # The ratio is: actual_window_height (physical) / self.ticker_height (logical)
            scale_factor = actual_window_height / self.ticker_height if self.ticker_height > 0 else 2.0
            target_y_logical = target_y_physical / scale_factor
            
            if DEBUG_APPBAR: print(f"[APPBAR] We are ticker #{our_slot + 1}, positioning at y={target_y_physical}px (physical) = {target_y_logical}px (logical)")
            
            # Position ourselves at the correct slot using LOGICAL pixels for Qt
            self.setGeometry(rect.left(), int(target_y_logical), rect.width(), self.ticker_height)
            
            # Mark as secondary (no AppBar registration to avoid conflicts)
            self.is_secondary_ticker = True
            self.target_position_y = int(target_y_logical)
            
            if DEBUG_APPBAR: print(f"[APPBAR] Secondary ticker positioned at y={target_y_logical} (no AppBar registration)")
            if DEBUG_APPBAR: print(f"[APPBAR] NOTE: This ticker will not reserve screen space - only primary ticker reserves space")
            
            # Keep our position stable
            def check_position():
                pos = self.pos()
                if pos.y() != int(target_y_logical):
                    if DEBUG_APPBAR: print(f"[APPBAR] Position drifted to y={pos.y()}, fixing to y={int(target_y_logical)}")
                    self.setGeometry(rect.left(), int(target_y_logical), rect.width(), self.ticker_height)
            
            QtCore.QTimer.singleShot(200, check_position)
            QtCore.QTimer.singleShot(500, check_position)
            QtCore.QTimer.singleShot(1000, check_position)
            return  # Exit - we've handled this case
        
        if DEBUG_APPBAR: print(f"[APPBAR] No existing reservation found - will register new AppBar")
        
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
                
                # Calculate the combined appbar height for all managed tickers on this screen.
                # Convert logical ticker heights to physical pixels using the screen's devicePixelRatio.
                device_scale = 1.0
                try:
                    device_scale = float(screen.devicePixelRatio())
                except Exception:
                    try:
                        device_scale = float(screen.devicePixelRatioF())
                    except Exception:
                        device_scale = 1.0

                # Gather all ticker windows managed by the tray (fallback to self)
                combined_logical = 0
                if hasattr(self, 'tray_icon') and hasattr(self.tray_icon, 'ticker_windows'):
                    for w in self.tray_icon.ticker_windows:
                        try:
                            # Use ticker_height if available, otherwise fallback to self.ticker_height
                            combined_logical += int(getattr(w, 'ticker_height', self.ticker_height))
                        except Exception:
                            combined_logical += int(self.ticker_height)
                else:
                    combined_logical = int(self.ticker_height)

                desired_physical_height = int(combined_logical * device_scale)
                if DEBUG_APPBAR: print(f"[APPBAR] Combined logical height={combined_logical}px, device_scale={device_scale}, desired_physical_height={desired_physical_height}px")

                if DEBUG_APPBAR: print(f"[APPBAR] Registering PRIMARY ticker as appbar: desired_physical_height={desired_physical_height}, screen={rect}")
                actual_top = set_appbar(int(self.winId()), desired_physical_height, rect)
                
                # Mark the time we set the work area to ignore feedback notifications
                import time as time_module
                self._last_work_area_set_time = time_module.time()
                if DEBUG_APPBAR: print(f"[APPBAR] Work area set time recorded: {self._last_work_area_set_time}")
                
                if DEBUG_APPBAR: print(f"[APPBAR] set_appbar returned actual_top={actual_top}")
                
                # Check position after appbar registration
                pos = self.pos()
                if DEBUG_APPBAR: print(f"[APPBAR] Position after set_appbar: x={pos.x()}, y={pos.y()}")
                
                # CRITICAL FIX: After appbar registration, Windows may have moved our window
                # Force it back to the absolute top (inside the reserved space, not below it)
                if DEBUG_APPBAR: print(f"[APPBAR] Forcing position back to absolute top: y={rect.top()}")
                self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
                
                # Verify the position was set
                pos = self.pos()
                if DEBUG_APPBAR: print(f"[APPBAR] Position after force-positioning: x={pos.x()}, y={pos.y()}")
                
                # If still not at top, keep trying
                if pos.y() != rect.top():
                    if DEBUG_APPBAR: print(f"[APPBAR] WARNING: Window not at top (y={pos.y()}), forcing again...")
                    for attempt in range(5):
                        self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
                        QtCore.QCoreApplication.processEvents()  # Let Qt process the move
                        pos = self.pos()
                        if DEBUG_APPBAR: print(f"[APPBAR] Attempt {attempt+1}: Position is now y={pos.y()}")
                        if pos.y() == rect.top():
                            break
                        time.sleep(0.05)
                
                # Window stays visible throughout
                
                # Force window to absolute top using Windows API too
                if DEBUG_APPBAR: print(f"[APPBAR] Calling force_window_to_top...")
                final_top = force_window_to_top(int(self.winId()), rect, self.ticker_height)

                # Additional positioning check for primary ticker at startup
                QtCore.QTimer.singleShot(300, lambda: self.ensure_top_position())
                
                if DEBUG_POSITIONING: print(f"[POSITIONING] Screen top: {rect.top()}, AppBar assigned: {actual_top}, Final position: {final_top}")
                
                # Check position after force_window_to_top
                pos = self.pos()
                if DEBUG_POSITIONING: print(f"[POSITIONING] Position after force_window_to_top: x={pos.x()}, y={pos.y()}")
                
                # LAST RESORT: If STILL not at top, use direct Windows API
                if pos.y() != rect.top():
                    if DEBUG_POSITIONING: print(f"[POSITIONING] STILL not at top! Using aggressive Windows API positioning...")
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
                        if DEBUG_POSITIONING: print(f"[POSITIONING] Aggressive attempt {attempt+1}: Window at y={window_rect.top}")
                        if window_rect.top == rect.top():
                            if DEBUG_POSITIONING: print(f"[POSITIONING] SUCCESS at attempt {attempt+1}")
                            break
                
                # Diagnose AppBar state to verify space reservation - use logical height
                reserved_space = diagnose_appbar_state(int(self.winId()), self.ticker_height)
                
                # CRITICAL FIX: After AppBar registration and broadcasts, Windows may reposition
                # our window to be BELOW the reserved space instead of IN it
                # Schedule aggressive repositioning after everything settles
                def final_position_fix():
                    if DEBUG_POSITIONING: print(f"[FINAL FIX] Checking final position...")
                    pos = self.pos()
                    if DEBUG_POSITIONING: print(f"[FINAL FIX] Current position: y={pos.y()}, expected: y={rect.top()}")
                    
                    if pos.y() != rect.top():
                        if DEBUG_POSITIONING: print(f"[FINAL FIX] Window at wrong position! Forcing to y={rect.top()}")
                        
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
                        if DEBUG_POSITIONING: print(f"[FINAL FIX] Position after fix: y={pos.y()}")
                        
                        # If still wrong, keep trying
                        if pos.y() != rect.top():
                            if DEBUG_POSITIONING: print(f"[FINAL FIX] Still wrong, scheduling another attempt...")
                            QtCore.QTimer.singleShot(100, final_position_fix)
                    else:
                        if DEBUG_POSITIONING: print(f"[FINAL FIX] Position correct at y={rect.top()} ✓")
                
                # Check position after delays to let Windows settle
                QtCore.QTimer.singleShot(200, final_position_fix)
                QtCore.QTimer.singleShot(500, final_position_fix)
                QtCore.QTimer.singleShot(1000, final_position_fix)
                
                # If AppBar didn't reserve proper space, try manual work area adjustment
                if reserved_space < self.ticker_height:
                    if DEBUG_APPBAR: print(f"[APPBAR] WARNING: Only {reserved_space}px reserved, expected {self.ticker_height}px")
                    if DEBUG_APPBAR: print(f"[APPBAR] Attempting manual work area adjustment...")
                    
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
                    if DEBUG_APPBAR: print(f"[APPBAR] Manual work area adjustment result: {result}")
                    
                    # Re-diagnose after manual adjustment
                    time.sleep(0.2)
                    diagnose_appbar_state(int(self.winId()), self.ticker_height)
                
                # DISABLED: Retry mechanism was causing problems when multiple tickers launched
                # The verify_and_fix callbacks would re-register appbar and cause position issues
                # def verify_and_fix():
                #     actual_pos = self.pos()
                #     if actual_pos.y() > rect.top():
                #         if DEBUG_POSITIONING: print(f"[POSITIONING] Window drifted to {actual_pos.y()}, forcing back to {rect.top()}")
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
        
        elapsed = (time.time() - start_time) * 1000
        print(f"[SETUP] AppBar setup completed in {elapsed:.1f}ms (plus 300ms+250ms timer delays)")
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
                
                # Re-register appbar on new screen (convert logical->physical)
                try:
                    dpr = screen.devicePixelRatioF()
                except Exception:
                    dpr = screen.devicePixelRatio()
                desired_physical_height = int(round(self.ticker_height * dpr))
                if DEBUG_APPBAR: print(f"[APPBAR] Re-registering on move: logical_height={self.ticker_height}, dpr={dpr}, desired_physical_height={desired_physical_height}")
                actual_top = set_appbar(int(self.winId()), desired_physical_height, rect)
                
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
        colored_print("[TCKR] update_prices_full() called - preparing to fetch stock prices")
        
        # Get all stocks/indices
        all_stocks = [s[0] for s in load_stocks()]
        yahoo_tickers = [t for t in all_stocks if t.startswith('^')]
        finnhub_tickers = [t for t in all_stocks if not t.startswith('^')]
        
        # Check if API key is available
        settings = get_settings()
        api_key = settings.get("finnhub_api_key", "").strip()
        
        if not api_key and finnhub_tickers:
            # No API key but user has stocks that need it
            # For first run, just use indices - don't block with dialog
            colored_print(f"[TCKR] No API key found - fetching only {len(yahoo_tickers)} Yahoo Finance indices")
            colored_print(f"[TCKR] {len(finnhub_tickers)} stocks will show as N/A until API key is configured in Settings")
            if yahoo_tickers:
                self.worker = PriceFetchWorker(yahoo_tickers, "", None)
                self.worker.prices_fetched.connect(self.on_prices_fetched)
                self.worker.start()
            else:
                colored_print("[TCKR] No API key and no indices selected - nothing to display")
                self.loading = False
                self.gl_widget.update()
            return
        
        # Have API key or only indices - fetch all stocks
        # Get second API key if configured
        api_key_2 = settings.get("finnhub_api_key_2", "").strip() or None
        if api_key and api_key_2:
            colored_print("[TCKR] Using dual API keys for load balancing")
        
        colored_print("[TCKR] Starting worker thread to fetch prices...")
        self.worker = PriceFetchWorker(all_stocks, api_key if api_key else "", api_key_2)
        self.worker.prices_fetched.connect(self.on_prices_fetched)
        self.worker.start()
    def on_prices_fetched(self, prices):
        colored_print(f"[TCKR] on_prices_fetched() called - received {len(prices)} prices")
        # Don't re-sort! load_stocks() already returns sorted list
        self.stocks = [s[0] for s in load_stocks()]
        self.prices = prices
        self.loading = False  # Hide loading screen, show ticker with real data
        self.bloom_cache_valid = False  # Invalidate bloom cache on price update
        import time as time_module
        self.last_api_update_time = time_module.time()  # Record API update time
        colored_print("[TCKR] Loading complete - building ticker display")
        self.build_ticker_text(reset_scroll=True)

        # If this is the primary ticker, update all other tickers with the same prices
        if (hasattr(self, 'tray_icon') and self.tray_icon and
            hasattr(self.tray_icon, 'primary_ticker') and self == self.tray_icon.primary_ticker):
            for ticker in self.tray_icon.ticker_windows:
                if ticker != self:  # Don't update self again
                    # Ensure the secondary ticker has the same normalized stock list
                    ticker.stocks = [s[0] for s in load_stocks()]
                    ticker.prices = prices.copy()
                    ticker.loading = False
                    ticker.bloom_cache_valid = False
                    ticker.last_api_update_time = self.last_api_update_time
                    ticker.build_ticker_text(reset_scroll=True)
                    print(f"[PRIMARY UPDATE] Updated secondary ticker with {len(prices)} prices")

    def _handle_coordinated_prices(self, prices, had_429, now):
        """Handle coordinated price fetching results and distribute to all tickers"""
        colored_print(f"[COORDINATED FETCH] Received {len(prices)} prices - distributing to all tickers")

        # Distribute prices to all tickers (they all have the same stocks)
        for ticker in self.tray_icon.ticker_windows:
            # Ensure each ticker has the normalized stocks list before rebuilding
            ticker.stocks = [s[0] for s in load_stocks()]
            ticker.prices = prices.copy()  # All tickers get all prices
            ticker.loading = False  # Hide loading screen
            ticker.bloom_cache_valid = False  # Invalidate bloom cache
            ticker.last_api_update_time = now

            # Update the ticker display
            ticker.build_ticker_text(reset_scroll=True)
            print(f"[COORDINATED FETCH] Updated ticker with {len(prices)} prices")

        # Handle backoff if there were 429 errors
        if had_429:
            import time as time_module
            # Apply backoff to all tickers
            backoff_duration = 300  # 5 minutes backoff
            TickerWindow.backoff_until = now + backoff_duration
            colored_print(f"[BACKOFF] Applied {backoff_duration}s backoff due to rate limiting")

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

    def get_triangle_rotation(self, change_percent):
        """
        Returns rotation angle for price change triangle based on magnitude.
        
        Args:
            change_percent: Price change as percentage
            
        Returns:
            Rotation angle in degrees:
            - 0° = pointing up (strong positive)
            - 45° = pointing up-right (small positive)
            - 90° = pointing right (no change)
            - 135° = pointing down-right (small negative)
            - 180° = pointing down (strong negative)
        """
        abs_change = abs(change_percent)
        
        if abs_change < 0.01:  # < 0.01% change
            return 90  # Point right (essentially no change)
        elif abs_change < 1.0:  # < 1% change
            return 45 if change_percent > 0 else 135  # Diagonal
        else:  # >= 1% change
            return 0 if change_percent > 0 else 180  # Full vertical

    def get_display_price_color(self, tkr, price, prev):
        """Price color with stale-data fade; gold only when value/change is unavailable."""
        if price is None or prev is None:
            return QtGui.QColor("#FFD700")

        if USE_OPT:
            r, g, b, a = opt.get_price_color_rgba(price, prev)
            base_color = QtGui.QColor(r, g, b, a)
        elif price > prev:
            base_color = QtGui.QColor("#00FF40")
        elif price < prev:
            base_color = QtGui.QColor("#FF5555")
        else:
            base_color = QtGui.QColor("#FFFFFF")

        return self.apply_fade_to_color(base_color, self.get_stale_fade_factor(tkr))

    def get_stale_fade_factor(self, tkr):
        """Return a dimming factor based on consecutive fetch failures for symbol."""
        fail_count = self.failed_fetch_counts.get(tkr, 0)
        if fail_count <= 1:
            return 1.0
        fade_step = min(10, fail_count - 1)
        return max(0.35, 1.0 - (fade_step * 0.08))

    def apply_fade_to_color(self, color, fade_factor):
        """Apply fade factor to a QColor while preserving alpha channel."""
        if color is None or fade_factor >= 0.999:
            return color
        faded_r = max(0, int(color.red() * fade_factor))
        faded_g = max(0, int(color.green() * fade_factor))
        faded_b = max(0, int(color.blue() * fade_factor))
        return QtGui.QColor(faded_r, faded_g, faded_b, color.alpha())

    def draw_rotated_triangle(self, painter, x, y, size, rotation_angle, color):
        """
        Draw a right-angle triangle rotated to the specified angle.
        The right-angle vertex is the directional point.
        
        Args:
            painter: QPainter object
            x, y: Center position for the triangle
            size: Size of the triangle
            rotation_angle: Rotation in degrees (0=up, 90=right, 180=down)
            color: QColor for the triangle
        """
        # Create a right-angle triangle where the right-angle vertex is the directional tip
        # (pointing up by default before rotation).
        half_size = size / 2
        tip_y = -int(half_size)
        leg_component = max(2, int(half_size * 0.9))
        triangle = QtGui.QPolygon([
            QtCore.QPoint(0, tip_y),                                  # Directional right-angle vertex
            QtCore.QPoint(leg_component, tip_y + leg_component),      # Leg endpoint 1
            QtCore.QPoint(-leg_component, tip_y + leg_component)      # Leg endpoint 2
        ])
        
        # Apply rotation transform
        transform = QtGui.QTransform()
        transform.translate(x, y)
        transform.rotate(rotation_angle)
        
        # Save current painter state
        painter.save()
        
        # Apply transform and draw
        painter.setTransform(transform, True)
        painter.setBrush(QtGui.QBrush(color))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPolygon(triangle)
        
        # Restore painter state
        painter.restore()

    def draw_rotated_arrow(self, painter, x, y, size, rotation_angle, color):
        """
        Draw an arrow rotated to the specified angle.
        
        Args:
            painter: QPainter object
            x, y: Center position for the arrow
            size: Size of the arrow
            rotation_angle: Rotation in degrees (0=up, 90=right, 180=down)
            color: QColor for the arrow
        """
        # Create arrow shape (pointing up by default)
        half_size = size / 2
        shaft_width = half_size * 0.35
        head_width = half_size * 0.75
        
        arrow = QtGui.QPolygon([
            # Arrow head (top triangle)
            QtCore.QPoint(0, -int(half_size)),      # Tip
            QtCore.QPoint(-int(head_width), -int(half_size * 0.3)),  # Left head
            QtCore.QPoint(-int(shaft_width), -int(half_size * 0.3)),  # Left shaft start
            # Arrow shaft (rectangle)
            QtCore.QPoint(-int(shaft_width), int(half_size * 0.5)),  # Left shaft bottom
            QtCore.QPoint(int(shaft_width), int(half_size * 0.5)),   # Right shaft bottom
            QtCore.QPoint(int(shaft_width), -int(half_size * 0.3)),  # Right shaft start
            QtCore.QPoint(int(head_width), -int(half_size * 0.3)),   # Right head
        ])
        
        # Apply rotation transform
        transform = QtGui.QTransform()
        transform.translate(x, y)
        transform.rotate(rotation_angle)
        
        # Save current painter state
        painter.save()
        
        # Apply transform and draw
        painter.setTransform(transform, True)
        painter.setBrush(QtGui.QBrush(color))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPolygon(arrow)
        
        # Restore painter state
        painter.restore()

    def draw_text_with_global_glow(self, painter, x, y, text, text_color, glow_color=None, settings=None):
        """
        Draw text with optional global glow effect.
        If glow_color is None and global_text_glow is enabled, uses a subtle white glow.
        Custom glow colors also respect the global_text_glow setting.
        """
        # Use provided settings or get from cache to avoid disk I/O
        if settings is None:
            settings = self._cached_settings if hasattr(self, '_cached_settings') else get_settings()
        
        # Apply global glow if enabled (subtle white glow for all text)
        if glow_color is None and settings.get("global_text_glow", True):
            # Much less intense than 5% glow (alpha 15 vs 50)
            glow_color = QtGui.QColor(255, 255, 255, 15)
        
        # If custom glow_color provided, only use it if global_text_glow is enabled
        if glow_color and not settings.get("global_text_glow", True):
            glow_color = None
        
        # Draw glow halo if we have a glow color
        if glow_color:
            painter.setPen(glow_color)
            if USE_OPT:
                for dx, dy in opt.get_subtle_glow_offsets():
                    painter.drawText(x + dx, y + dy, text)
            else:
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
                if USE_OPT:
                    change_percent = opt.calculate_abs_change_percent(price, prev_close)
                else:
                    change_percent = abs((price - prev_close) / prev_close) * 100
                # print(f"[GLOW DEBUG] {tkr}: price={price}, prev_close={prev_close}, change_percent={change_percent:.2f}%")  # Commented for less verbose output
                if change_percent >= 5.0:
                    # print(f"[GLOW DEBUG] Manually triggering glow effect for {tkr} with {change_percent:.2f}% change")  # Commented for less verbose output
                    self.pulse_effects[tkr] = time.time()
        
        if self.pulse_effects:
            self.build_ticker_text(reset_scroll=False)
        # else:
            # print("[GLOW DEBUG] No stocks found with >= 5% change to glow")  # Commented for less verbose output

    def update_prices_inplace(self, force=False):
        # PERF ENHANCEMENT 3: Use smart update intervals based on market hours
        smart_interval = self.get_smart_update_interval()
        if smart_interval != self.update_timer.interval():
            self.update_timer.setInterval(smart_interval)
            print(f"[PERF] Adjusted update interval to {smart_interval/1000}s for current market conditions")

        import time as time_module
        now = time_module.time()

        # Update countdown timer immediately when timer fires (even if we skip the actual fetch)
        # This prevents the countdown from getting stuck at 0:00
        self.last_api_update_time = now
        # If this is the primary ticker, propagate the API timer tick to all managed tickers
        if hasattr(self, 'tray_icon') and self.tray_icon and self == getattr(self.tray_icon, 'primary_ticker', None):
            try:
                for t in self.tray_icon.ticker_windows:
                    # Ensure secondary tickers show the same countdown time
                    t.last_api_update_time = now
            except Exception:
                pass

        # COORDINATED FETCHING: Only the primary ticker handles fetching for all tickers
        if hasattr(self, 'tray_icon') and self.tray_icon and self == self.tray_icon.primary_ticker:
            # This is the primary ticker - coordinate fetching for all tickers
            self._coordinate_price_fetching(force, now)
            return

        # Secondary tickers don't fetch independently - they wait for primary to update them

    def _coordinate_price_fetching(self, force, now):
        """Coordinate price fetching across all ticker windows"""
        import time as time_module
        # Collect all unique stocks from all ticker windows
        all_stocks = set()

        for ticker in self.tray_icon.ticker_windows:
            if hasattr(ticker, 'stocks') and ticker.stocks:
                all_stocks.update(ticker.stocks)

        combined_stocks = sorted(list(all_stocks))
        print(f"[COORDINATED FETCH] Fetching {len(combined_stocks)} unique stocks for {len(self.tray_icon.ticker_windows)} tickers")

        # Check if we should use websockets for real-time data during market hours
        market_is_open = self._market_is_open if hasattr(self, '_market_is_open') else False
        colored_print(f"[WEBSOCKET] Coordinated fetch: market_open={market_is_open}, has_websocket={self.websocket_client is not None}, force={force}")

        if self.websocket_client and market_is_open and not force:
            # During market hours, use websockets for real-time updates
            if not self.websocket_client.connected:
                colored_print("[WEBSOCKET] 🕐 Market is open - connecting to real-time data")
                if self.websocket_client.connect():
                    # Subscribe to all stocks from all tickers
                    finnhub_symbols = [s for s in combined_stocks if not s.startswith('^')]
                    if finnhub_symbols:
                        colored_print(f"[WEBSOCKET] Subscribing to {len(finnhub_symbols)} symbols: {finnhub_symbols[:10]}{'...' if len(finnhub_symbols) > 10 else ''}")
                        self.websocket_client.subscribe_symbols(finnhub_symbols)
            elif self.websocket_client.connected and not self.websocket_client.subscribed_symbols:
                # Already connected but not subscribed - subscribe now
                colored_print("[WEBSOCKET] 🕐 Websocket connected but not subscribed - subscribing to symbols")
                finnhub_symbols = [s for s in combined_stocks if not s.startswith('^')]
                if finnhub_symbols:
                    colored_print(f"[WEBSOCKET] Subscribing to {len(finnhub_symbols)} symbols: {finnhub_symbols[:10]}{'...' if len(finnhub_symbols) > 10 else ''}")
                    self.websocket_client.subscribe_symbols(finnhub_symbols)

            # If websockets are connected, skip polling during market hours
            real_time_available = self.websocket_client.is_real_time_available()
            colored_print(f"[WEBSOCKET] Real-time available: {real_time_available} (connected={self.websocket_client.connected}, subscribed={bool(self.websocket_client.subscribed_symbols)})")

            if real_time_available:
                # Log status periodically (every 10 price updates to avoid spam)
                if hasattr(self, '_last_websocket_status_log'):
                    if time_module.time() - self._last_websocket_status_log > 300:  # Every 5 minutes
                        self.websocket_client.log_status_summary()
                        self._last_websocket_status_log = time_module.time()
                else:
                    self._last_websocket_status_log = time_module.time()

                # Check cost warning for free tier
                finnhub_count = len([s for s in combined_stocks if not s.startswith('^')])
                if finnhub_count > 50:
                    colored_print(f"[WEBSOCKET] ⚠️ WARNING: You have {finnhub_count} Finnhub stocks - free tier supports 50 symbols. "
                          "Consider upgrading to paid plan to avoid rate limiting.")
                return

        # Respect backoff unless this fetch was forced by the user
        if not force and hasattr(TickerWindow, 'backoff_until') and now < TickerWindow.backoff_until:
            print(f"[UPDATE] Skipping fetch - in backoff until {time_module.strftime('%H:%M:%S', time_module.localtime(TickerWindow.backoff_until))}")
            return

        # Disconnect websockets after market hours to save costs
        if self.websocket_client and not market_is_open and self.websocket_client.connected:
            colored_print("[WEBSOCKET] 🌙 Market closed - disconnecting to save costs")
            self.websocket_client.log_status_summary()
            self.websocket_client.disconnect()

        api_key = ensure_finnhub_api_key(self)

        # Get all tickers to fetch
        all_tickers = combined_stocks
        yahoo_tickers = [t for t in all_tickers if t.startswith('^')]
        finnhub_tickers = [t for t in all_tickers if not t.startswith('^')]

        if not api_key:
            # No API key - only fetch Yahoo Finance indices (no key needed)
            if not yahoo_tickers:
                # print("[BACKOFF DEBUG] No API key and no indices, aborting fetch.")  # Commented for less verbose output
                return
            # Only fetch Yahoo indices
            tickers_to_fetch = yahoo_tickers
        else:
            # Have API key - fetch everything
            tickers_to_fetch = all_tickers

        # Get second API key if configured
        api_key_2 = get_settings().get("finnhub_api_key_2", "").strip() or None

        # Run fetch in a worker thread to avoid blocking the UI
        def fetch_and_handle():
            tickers = tickers_to_fetch
            prices, had_429 = fetch_all_stock_prices_with_429(tickers, api_key or "", api_key_2, force=force)
            # Use QTimer to call the handler in the main thread
            QtCore.QTimer.singleShot(0, lambda: self._handle_coordinated_prices(prices, had_429, now))

        # Start the fetch thread
        import threading
        fetch_thread = threading.Thread(target=fetch_and_handle, daemon=True)
        fetch_thread.start()


        # Check if we should use websockets for real-time data during market hours
        market_is_open = self._market_is_open if hasattr(self, '_market_is_open') else False

        # Log data source being used
        if market_is_open and self.websocket_client and self.websocket_client.is_real_time_available():
            # Using websockets
            colored_print("[UPDATE] 🕐 Market open - using WEBSOCKETS for real-time updates")
            pass  # Already logged in websocket status updates
        elif market_is_open:
            # Market open but websockets not available - falling back to polling
            colored_print("[UPDATE] 🕐 Market open - using POLLING (websockets unavailable)")
            colored_print(f"[WEBSOCKET] Debug: has_client={self.websocket_client is not None}, connected={self.websocket_client.connected if self.websocket_client else False}, subscribed={bool(self.websocket_client.subscribed_symbols) if self.websocket_client else False}")
        else:
            # Market closed - using extended polling
            colored_print("[UPDATE] 🌙 Market closed - using EXTENDED POLLING (15min intervals)")

        if self.websocket_client and market_is_open and not force:
            # During market hours, use websockets for real-time updates
            if not self.websocket_client.connected:
                colored_print("[WEBSOCKET] 🕐 Market is open - connecting to real-time data")
                if self.websocket_client.connect():
                    # Subscribe to current stocks
                    finnhub_symbols = [s for s in self.stocks if not s.startswith('^')]
                    if finnhub_symbols:
                        colored_print(f"[WEBSOCKET] Subscribing to {len(finnhub_symbols)} symbols: {finnhub_symbols[:10]}{'...' if len(finnhub_symbols) > 10 else ''}")
                        self.websocket_client.subscribe_symbols(finnhub_symbols)
            elif self.websocket_client.connected and not self.websocket_client.subscribed_symbols:
                # Already connected but not subscribed - subscribe now
                colored_print("[WEBSOCKET] 🕐 Websocket connected but not subscribed - subscribing to symbols")
                finnhub_symbols = [s for s in self.stocks if not s.startswith('^')]
                if finnhub_symbols:
                    colored_print(f"[WEBSOCKET] Subscribing to {len(finnhub_symbols)} symbols: {finnhub_symbols[:10]}{'...' if len(finnhub_symbols) > 10 else ''}")
                    self.websocket_client.subscribe_symbols(finnhub_symbols)

            # If websockets are connected, skip polling during market hours
            if self.websocket_client.is_real_time_available():
                # Log status periodically (every 10 price updates to avoid spam)
                if hasattr(self, '_last_websocket_status_log'):
                    import time
                    if time.time() - self._last_websocket_status_log > 300:  # Every 5 minutes
                        self.websocket_client.log_status_summary()
                        self._last_websocket_status_log = time.time()
                else:
                    self._last_websocket_status_log = time.time()

                # Check cost warning for free tier
                finnhub_count = len([s for s in self.stocks if not s.startswith('^')])
                if finnhub_count > 50:
                    colored_print(f"[WEBSOCKET] ⚠️ WARNING: You have {finnhub_count} Finnhub stocks - free tier supports 50 symbols. "
                          "Consider upgrading to paid plan to avoid rate limiting.")
                return

        # Respect backoff unless this fetch was forced by the user
        if not force and hasattr(TickerWindow, 'backoff_until') and now < TickerWindow.backoff_until:
            print(f"[UPDATE] Skipping fetch - in backoff until {time_module.strftime('%H:%M:%S', time_module.localtime(TickerWindow.backoff_until))}")
            return

        # Disconnect websockets after market hours to save costs
        if self.websocket_client and not market_is_open and self.websocket_client.connected:
            colored_print("[WEBSOCKET] 🌙 Market closed - disconnecting to save costs")
            self.websocket_client.log_status_summary()
            self.websocket_client.disconnect()

        api_key = ensure_finnhub_api_key(self)
        
        # Get all tickers
        all_tickers = self.stocks
        yahoo_tickers = [t for t in all_tickers if t.startswith('^')]
        finnhub_tickers = [t for t in all_tickers if not t.startswith('^')]
        
        if not api_key:
            # No API key - only fetch Yahoo Finance indices (no key needed)
            if not yahoo_tickers:
                # print("[BACKOFF DEBUG] No API key and no indices, aborting fetch.")  # Commented for less verbose output
                return
            # Only fetch Yahoo indices
            tickers_to_fetch = yahoo_tickers
        else:
            # Have API key - fetch everything
            tickers_to_fetch = all_tickers

        # Get second API key if configured
        api_key_2 = get_settings().get("finnhub_api_key_2", "").strip() or None

        # Run fetch in a worker thread to avoid blocking the UI
        def fetch_and_handle():
            tickers = tickers_to_fetch
            prices, had_429 = fetch_all_stock_prices_with_429(tickers, api_key or "", api_key_2, force=force)
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
        # Update last API update time for countdown overlay (moved to top of method)
        
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

        # Ensure coordinated distribution for inplace fetch path as well
        # If this instance is the primary ticker, propagate the raw prices
        # to secondary tickers so they run their deferred processing.
        try:
            if hasattr(self, 'tray_icon') and self.tray_icon and self == getattr(self.tray_icon, 'primary_ticker', None):
                for ticker in self.tray_icon.ticker_windows:
                    if ticker is self:
                        continue
                    try:
                        ticker._pending_price_update = prices.copy()
                        ticker.bloom_cache_valid = False
                        ticker.last_api_update_time = now
                        QtCore.QTimer.singleShot(0, ticker._process_price_update_deferred)
                        print(f"[PRIMARY UPDATE] Distributed inplace prices to secondary ticker")
                    except Exception:
                        pass
        except Exception:
            pass

        # Run garbage collection during idle time (after price updates) to prevent stutters during rendering
        import gc
        gc.collect(generation=0)  # Quick collection of youngest generation only

    @QtCore.pyqtSlot(str, float, float)
    def update_price_from_websocket(self, symbol, price, timestamp):
        """Handle real-time price updates from websocket - batched for performance"""
        # Distribute updates to all managed tickers so each shows its own list
        if not hasattr(self, 'tray_icon') or not self.tray_icon:
            return

        targets = self.tray_icon.ticker_windows if hasattr(self.tray_icon, 'ticker_windows') else [self]

        for ticker in targets:
            if not hasattr(ticker, 'stocks') or symbol not in ticker.stocks:
                continue

            old_price = ticker.prices.get(symbol, (None, None))[0]
            prev_close = ticker.prices.get(symbol, (None, None))[1]

            # Logging throttled per ticker
            should_log = False
            if old_price is None:
                should_log = True  # First price update
            elif hasattr(ticker, '_websocket_update_counter'):
                ticker._websocket_update_counter += 1
                # Only log every 50th update or significant changes
                if ticker._websocket_update_counter % 50 == 0:
                    should_log = True
                elif old_price and abs(price - old_price) / old_price > 0.005:  # >0.5% change
                    should_log = True
            else:
                ticker._websocket_update_counter = 1
                should_log = True

            if should_log:
                import time as time_module
                age_seconds = time_module.time() - timestamp
                colored_print(f"[WEBSOCKET] 📈 RT Update: {symbol} = ${price:.2f} ({age_seconds:.1f}s old)")

            # Update price dict immediately (fast - just updates data)
            ticker.prices[symbol] = (price, prev_close)
            ticker.bloom_cache_valid = False
            # DO NOT update last_api_update_time - that should only be set by full API fetches
            # Otherwise the periodic update timer keeps getting reset
            
            # Mark that we have updates ready for visual refresh
            ticker.websocket_has_updates = True

            # CRITICAL: DO NOT trigger visual rebuilds from WebSocket updates
            # Let the periodic visual refresh timer handle rebuilds (every 2 seconds)
            # This completely decouples real-time data from expensive rendering
            # Prices will appear updated within 2 seconds

    def _rebuild_ticker_deferred(self):
        """Rebuild ticker visuals - only called when batched updates are ready"""
        self._websocket_visual_count = 0
        # Don't rebuild if we're loading or have no stocks
        if not self.loading and self.stocks:
            # CRITICAL: Don't rebuild entire ticker - just invalidate bloom cache
            # The paint loop will pick up new prices from self.prices dict
            # This avoids expensive pixmap regeneration on every update
            self.bloom_cache_valid = False
            # Force a repaint to show updated prices
            self.ticker_widget.update()

    def on_prices_inplace_fetched(self, new_prices):
        # OPTIMIZATION: Minimal work on main thread - just update prices dict
        # Defer all heavy processing to avoid blocking render loop
        self._pending_price_update = new_prices
        QtCore.QTimer.singleShot(0, self._process_price_update_deferred)
    
    def _process_price_update_deferred(self):
        """Process price updates in deferred manner to avoid blocking render loop"""
        if not hasattr(self, '_pending_price_update'):
            return
        
        new_prices = self._pending_price_update
        del self._pending_price_update
        
        import time as time_module
        now = int(time_module.time() * 1000)
        price_changed = False
        
        # Optimize batch price processing with Numba if available
        if USE_OPT and len(new_prices) > 5:  # Use optimization for larger batches
            try:
                # Prepare arrays for batch processing
                tickers = []
                current_prices_list = []
                prev_closes_list = []
                old_prices_list = []
                
                for tkr, (price, prev_close) in new_prices.items():
                    old_price = self.prices.get(tkr, (None, None))[0]
                    old_prev_close = self.prices.get(tkr, (None, None))[1]
                    
                    # Handle glow history clearing first
                    if old_prev_close is not None and prev_close is not None and old_prev_close != prev_close:
                        if tkr in self.glow_history:
                            del self.glow_history[tkr]
                    
                    # Handle failed price fetches
                    if price is None:
                        self.failed_fetch_counts[tkr] = self.failed_fetch_counts.get(tkr, 0) + 1
                        if old_price is not None:
                            price = old_price
                            prev_close = old_prev_close
                    else:
                        self.failed_fetch_counts[tkr] = 0
                        if prev_close is None and old_prev_close is not None:
                            prev_close = old_prev_close
                    
                    # Only add valid prices to batch processing
                    if price is not None and prev_close is not None and price > 0 and prev_close > 0:
                        tickers.append(tkr)
                        current_prices_list.append([price, prev_close])
                        old_prices_list.append([old_price if old_price is not None else price, prev_close])
                
                if current_prices_list:
                    # Convert to numpy arrays for batch processing
                    import numpy as np
                    current_array = np.array(current_prices_list, dtype=np.float32)
                    old_array = np.array(old_prices_list, dtype=np.float32)
                    
                    # Batch calculate all price changes
                    results = opt.batch_calculate_price_changes_optimized(current_array, old_array)
                    
                    # Process results
                    for i, tkr in enumerate(tickers):
                        price = current_prices_list[i][0]
                        prev_close = current_prices_list[i][1]
                        old_price = old_prices_list[i][0]
                        
                        change = results[i, 0]
                        change_percent = results[i, 1]
                        direction = results[i, 2]
                        should_glow = results[i, 3] > 0
                        
                        # Check for price changes and update flash times
                        if old_price != price:
                            self.price_flash_times[tkr] = now
                            price_changed = True
                            
                            # Handle glow effects for significant changes
                            if should_glow and tkr not in self.pulse_effects:
                                already_glowed_for_this = (tkr in self.glow_history and 
                                                         self.glow_history[tkr] == prev_close)
                                if not already_glowed_for_this:
                                    self.pulse_effects[tkr] = time.time()
                                    self.glow_baseline_prices[tkr] = price
                                    self.glow_history[tkr] = prev_close
                        elif tkr in self.price_flash_times and price == old_price:
                            del self.price_flash_times[tkr]
                        
                        new_prices[tkr] = (price, prev_close)
                
            except Exception as e:
                # Fall back to original processing if batch optimization fails
                colored_print(f"[NUMBA] Batch optimization failed, falling back to original: {e}")
                USE_OPT_FALLBACK = False
        else:
            USE_OPT_FALLBACK = False
        
        # Original processing (fallback or small batches)
        if not USE_OPT or len(new_prices) <= 5 or 'USE_OPT_FALLBACK' in locals():
            for tkr, (price, prev_close) in new_prices.items():
                old_price = self.prices.get(tkr, (None, None))[0]
                old_prev_close = self.prices.get(tkr, (None, None))[1]
                
                # If prev_close changed (new trading day), clear glow history for this stock
                if old_prev_close is not None and prev_close is not None and old_prev_close != prev_close:
                    if tkr in self.glow_history:
                        del self.glow_history[tkr]
                
                if price is None:
                    self.failed_fetch_counts[tkr] = self.failed_fetch_counts.get(tkr, 0) + 1
                    if old_price is not None:
                        price = old_price
                else:
                    self.failed_fetch_counts[tkr] = 0
                    if prev_close is None and old_prev_close is not None:
                        prev_close = old_prev_close
                
                if price is not None and (old_price is None or price != old_price):
                    self.price_flash_times[tkr] = now
                    # Start pulse effect for significant price changes
                    if old_price is not None and prev_close and prev_close != 0:
                        # Only trigger glow if stock is not already glowing
                        if tkr not in self.pulse_effects:
                            # No current glow - check against prev_close
                            if USE_OPT:
                                change_percent = opt.calculate_abs_change_percent(price, prev_close)
                            else:
                                change_percent = abs((price - prev_close) / prev_close) * 100
                            # Check if we already showed glow for this prev_close value
                            already_glowed_for_this = (tkr in self.glow_history and 
                                                       self.glow_history[tkr] == prev_close)
                            if change_percent >= 5.0 and not already_glowed_for_this:
                                self.pulse_effects[tkr] = time.time()
                                self.glow_baseline_prices[tkr] = price
                                self.glow_history[tkr] = prev_close  # Remember this prev_close
                    price_changed = True
                elif tkr in self.price_flash_times and price == old_price:
                    del self.price_flash_times[tkr]
                new_prices[tkr] = (price, prev_close)
        self.prev_prices = self.prices.copy()
        self.prices = new_prices
        
        # Also check for existing significant changes (not just new price changes)
        # This runs at startup to catch stocks that already have big changes
        # Use parallel processing for large portfolios
        if USE_OPT and len(new_prices) > 10:
            try:
                # Prepare data for parallel glow detection
                import numpy as np
                valid_tickers = []
                prices_list = []
                prev_closes_list = []
                
                for tkr, (price, prev_close) in new_prices.items():
                    if (price is not None and prev_close is not None and prev_close != 0 and
                        tkr not in self.pulse_effects):
                        already_glowed = (tkr in self.glow_history and 
                                        self.glow_history[tkr] == prev_close)
                        recently_expired = (hasattr(self, 'recently_expired_effects') and 
                                          tkr in self.recently_expired_effects)
                        
                        if not already_glowed and not recently_expired:
                            valid_tickers.append(tkr)
                            prices_list.append(price)
                            prev_closes_list.append(prev_close)
                
                if valid_tickers:
                    # Use parallel glow detection
                    prices_array = np.array(prices_list, dtype=np.float32)
                    prev_closes_array = np.array(prev_closes_list, dtype=np.float32)
                    glow_flags = opt.parallel_glow_effect_detection(prices_array, prev_closes_array, 5.0)
                    
                    # Apply results
                    current_time = time.time()
                    for i, should_glow in enumerate(glow_flags):
                        if should_glow:
                            tkr = valid_tickers[i]
                            price = prices_list[i]
                            prev_close = prev_closes_list[i]
                            
                            self.pulse_effects[tkr] = current_time
                            self.glow_baseline_prices[tkr] = price
                            self.glow_history[tkr] = prev_close
                            
            except Exception as e:
                # Fall back to original sequential processing
                colored_print(f"[NUMBA] Parallel glow detection failed, using fallback: {e}")
                USE_PARALLEL_FALLBACK = True
        else:
            USE_PARALLEL_FALLBACK = True
            
        # Original sequential processing (fallback or small datasets)
        if not USE_OPT or len(new_prices) <= 10 or 'USE_PARALLEL_FALLBACK' in locals():
            for tkr, (price, prev_close) in new_prices.items():
                if price is not None and prev_close is not None and prev_close != 0:
                    if USE_OPT:
                        change_percent = opt.calculate_abs_change_percent(price, prev_close)
                    else:
                        change_percent = abs((price - prev_close) / prev_close) * 100
                    # Only glow if: 1) not currently glowing, 2) meets threshold, 3) haven't glowed for this prev_close before, 4) not recently expired
                    already_glowed_for_this = (tkr in self.glow_history and 
                                              self.glow_history[tkr] == prev_close)
                    recently_expired = (hasattr(self, 'recently_expired_effects') and 
                                      tkr in self.recently_expired_effects)
                    
                    if change_percent >= 5.0 and tkr not in self.pulse_effects and not already_glowed_for_this and not recently_expired:
                        self.pulse_effects[tkr] = time.time()
                        self.glow_baseline_prices[tkr] = price  # Set baseline for initial glow
                        self.glow_history[tkr] = prev_close  # Remember this prev_close
        
        # Rebuild pixmaps with updated prices
        self._rebuild_pixmaps_deferred()
        
        if price_changed:
            self.play_update_sound()
    
    def _rebuild_pixmaps_deferred(self):
        """Rebuild ticker pixmaps in deferred manner to avoid blocking render loop"""
        self.build_ticker_pixmaps()
        self.gl_widget.update()
    
    def set_transparency(self, percent):
        self.setWindowOpacity(percent / 100.0)
    def update_prices(self):
        api_key = ensure_finnhub_api_key(self)
        
        # Reload stocks from file (already sorted correctly by load_stocks)
        self.stocks = [s[0] for s in load_stocks()]
        yahoo_tickers = [t for t in self.stocks if t.startswith('^')]
        
        if not api_key:
            # No API key - only fetch Yahoo Finance indices
            if yahoo_tickers:
                print(f"[UPDATE] No API key - fetching only {len(yahoo_tickers)} Yahoo Finance indices")
                self.prices = fetch_all_stock_prices(yahoo_tickers, "", None)
            else:
                print("[UPDATE] No API key and no indices - nothing to update")
                return
        else:
            # Get second API key if configured
            api_key_2 = get_settings().get("finnhub_api_key_2", "").strip() or None
            print(f"[UPDATE] Stocks after loading: {self.stocks}")
            self.prices = fetch_all_stock_prices(self.stocks, api_key, api_key_2)
            
        self.build_ticker_text(reset_scroll=True)
    
    def update_market_status(self):
        """Update market status in the ticker display"""
        # Log websocket status periodically (every market status update = every minute)
        if self.websocket_client:
            market_open = getattr(self, '_market_is_open', False)
            if market_open and self.websocket_client.connected:
                # Log status during market hours when connected
                status = self.websocket_client.get_debug_status()
                if status['price_updates_processed'] > 0:  # Only log if we've received data
                    colored_print(f"[WEBSOCKET] 📊 Hourly status: {status['price_updates_processed']} updates, {status['messages_received']} msgs, {status['connection_duration']:.1f}s connected")

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
                    if USE_OPT:
                        change_percent = opt.calculate_abs_change_percent(price, prev_close)
                    else:
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
            # Use friendly display name for major indices
            display_name = INDEX_DISPLAY_NAMES.get(tkr, tkr)
            price, prev = self.prices.get(tkr, (None, None))
            if price is not None:
                items.append(f"{display_name}: {price:.2f}")
            else:
                items.append(f"{display_name}: N/A")
        
        self.ticker_text = "   ".join(items) + "   "
        metrics = QtGui.QFontMetrics(self.ticker_font)
        self.window_width = self.width()
        
        # Only reset scroll position when explicitly requested (initial load, stock list changes)
        # Start the ticker completely off-screen to the right for a smooth entrance
        if reset_scroll:
            # Position text well off the right edge of the screen for smooth scroll-in
            # Add extra padding (200px) to ensure first element is completely hidden
            self.offset = self.window_width + 200
            
        self.build_ticker_pixmaps()
    
    def build_ticker_pixmaps(self):
        self.ticker_pixmaps = []
        self.ticker_ghost_pixmaps = []  # Cached tinted versions for ghosting layers
        self.ticker_pixmap_widths = []
        self.ticker_area_templates = []
        
        # Invalidate bloom cache when ticker content changes
        self.bloom_cache_valid = False
        # Clear donate ghost pixmap placeholder
        self._donate_ghost_pixmap = None
        
        # Don't clear ghost_frames here - we're making deep copies so they remain valid
        
        # Get settings once for entire function to avoid disk I/O in tight loop
        settings = self._cached_settings if hasattr(self, '_cached_settings') else get_settings()

        
        metrics = QtGui.QFontMetrics(self.ticker_font)
        if USE_OPT:
            icon_size = opt.calculate_icon_size(self.ticker_height, 0.85)
        else:
            icon_size = int(self.ticker_height * 0.85)  # Icon a little larger than font size, leaves 15% padding
        
        # If icon size changed, clear cache to remove old sizes
        if self.current_icon_size != icon_size:
            print(f"[PERF] Icon size changed from {self.current_icon_size} to {icon_size}, clearing cache")
            self.icon_cache.clear()
            self.current_icon_size = icon_size
        
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
        
        # Use memory pool for market pixmap if available
        if USE_MEMORY_POOL:
            market_pixmap = get_pooled_pixmap(market_total_width, self.ticker_height)
        else:
            market_pixmap = QtGui.QPixmap(market_total_width, self.ticker_height)
        market_pixmap.fill(QtCore.Qt.transparent)
        market_painter = QtGui.QPainter(market_pixmap)
        market_painter.setFont(self.ticker_font)
        
        # Center text vertically
        text_y = (self.ticker_height + metrics.ascent() - metrics.descent()) // 2
        x = 10  # Small left padding
        
        # Draw "Market:" in blue with subtle glow (same intensity as ticker symbols)
        market_glow = QtGui.QColor(0, 179, 255, 15)  # Same as default global glow
        self.draw_text_with_global_glow(market_painter, x, text_y, market_text, market_color, glow_color=market_glow, settings=settings)
        x += market_text_width
        
        # Draw "Open" or "Closed" with subtle glow (same intensity as ticker symbols)
        if status_text == "Open":
            status_glow = QtGui.QColor(0, 255, 64, 15)  # Same as default global glow
        else:
            status_glow = QtGui.QColor(255, 85, 85, 15)  # Same as default global glow
        self.draw_text_with_global_glow(market_painter, x, text_y, status_text, status_color, glow_color=status_glow, settings=settings)
        
        market_painter.end()
        
        # Add market status pixmap to the beginning
        self.ticker_pixmaps.append(market_pixmap)
        self.ticker_pixmap_widths.append(market_total_width)
        # Create and cache a tinted ghost pixmap for market (used by ghosting layers)
        market_ghost = QtGui.QPixmap(market_pixmap.size())
        market_ghost.fill(QtCore.Qt.transparent)
        mgp = QtGui.QPainter(market_ghost)
        mgp.drawPixmap(0, 0, market_pixmap)
        mgp.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
        # Compute subdued tint from the market pixmap's dominant color
        galpha_pct = settings.get("led_ghost_tint_alpha", 45)
        dominant = calculate_pixmap_dominant_color(market_pixmap)
        # Amplify color using user-set color strength so ghosts reflect the item color
        color_strength = settings.get("led_ghost_color_strength", 140) / 100.0
        sub_r = int(min(255, dominant.red() * color_strength + 40))
        sub_g = int(min(255, dominant.green() * color_strength + 40))
        sub_b = int(min(255, dominant.blue() * color_strength + 40))
        market_tint = QtGui.QColor(sub_r, sub_g, sub_b)
        market_tint.setAlpha(int(galpha_pct * 2.55))

        # DEBUG OVERRIDE: force vivid tint if debug mode is enabled
        if getattr(self, '_ghost_debug_force_visible', False):
            market_tint = getattr(self, '_ghost_debug_force_tint', market_tint)

        mgp.fillRect(market_ghost.rect(), market_tint)
        mgp.end()

        if getattr(self, '_ghost_debug_logging', False):
            try:
                img = market_ghost.toImage()
                w = img.width(); h = img.height()
                cx, cy = w//2, h//2
                center_alpha = img.pixelColor(cx, cy).alpha()
                ssum = 0; scount = 0
                for sx in range(max(0, cx-1), min(w, cx+2)):
                    for sy in range(max(0, cy-1), min(h, cy+2)):
                        ssum += img.pixelColor(sx, sy).alpha()
                        scount += 1
                avg_alpha = ssum // scount if scount else 0
                print(f"[GHOST BUILD DEBUG] market_ghost center_alpha={center_alpha}, avg_center_alpha={avg_alpha}")
            except Exception:
                pass

        self.ticker_ghost_pixmaps.append(market_ghost)
        # Add click areas for Market Status so bloom/ghosting effects apply
        market_label_rect = QtCore.QRect(10, 0, market_text_width, self.ticker_height)
        status_rect = QtCore.QRect(10 + market_text_width, 0, status_text_width, self.ticker_height)
        self.ticker_area_templates.append([
            ('market_label', 'MARKET', market_label_rect),
            ('market_status', status_text.upper(), status_rect)
        ])
        
        # Now build stock ticker pixmaps
        for tkr in self.stocks:
            # Use friendly display name for major indices
            display_name = INDEX_DISPLAY_NAMES.get(tkr, tkr)
            
            price, prev = self.prices.get(tkr, (None, None))
            icon = get_ticker_icon(tkr, icon_size)
            tkr_width = metrics.horizontalAdvance(display_name + " ")
            sparkline_width = 50 if self.show_sparklines else 0
            sparkline_gap = 8 if self.show_sparklines else 0
            price_text = f"{price:.2f}" if price is not None else "N/A"
            price_width = metrics.horizontalAdvance(price_text)
            change_text = ""
            pct_text = ""
            change = 0
            pct = 0
            triangle_rotation = 90  # Default to right-pointing (no change)
            if price is not None and prev is not None:
                change = price - prev
                pct = (change / prev * 100) if prev else 0
                
                # Calculate rotation angle for triangle
                triangle_rotation = self.get_triangle_rotation(pct)
                
                if change > 0:
                    change_text = f"+{abs(change):.2f}"
                    pct_text = f"+{abs(pct):.2f}%"
                elif change < 0:
                    change_text = f"-{abs(change):.2f}"
                    pct_text = f"-{abs(pct):.2f}%"
                else:  # change == 0
                    change_text = f"{change:.2f}"
                    pct_text = f"{pct:.2f}%"
            change_width = max(small_metrics.horizontalAdvance(change_text), small_metrics.horizontalAdvance(pct_text)) if (change_text or pct_text) else 0
            
            # Reserve enough horizontal space for the indicator so following content
            # (e.g., right-side sparklines) never overlaps, regardless of digit count.
            if change_text or pct_text:
                indicator_style_for_width = settings.get("price_indicator_style", "triangles")
                if indicator_style_for_width == "thin_arrows":
                    triangle_width = 14
                else:
                    indicator_size_for_width = int(self.ticker_height * 0.42)
                    triangle_width = max(20, 13 + (indicator_size_for_width // 2) + 2)
            else:
                triangle_width = 0
            sep = "      "
            sep_width = metrics.horizontalAdvance(sep)
            total_width = icon_size + 8 + tkr_width + sparkline_width + sparkline_gap + price_width + (10 + change_width + triangle_width if change_width else 0) + sep_width + 20
            
            # Use memory pool for ticker pixmap if available
            if USE_MEMORY_POOL:
                pixmap = get_pooled_pixmap(total_width, self.ticker_height)
            else:
                pixmap = QtGui.QPixmap(total_width, self.ticker_height)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            x = 0
            # Center icon vertically
            if USE_OPT:
                icon_y = opt.calculate_icon_y_position(self.ticker_height, icon_size)
            else:
                icon_y = (self.ticker_height - icon_size) // 2
            painter.drawPixmap(x, icon_y, icon)
            x += icon_size + 8
            # Center text vertically
            if USE_OPT:
                tkr_y = opt.calculate_text_position(self.ticker_height, metrics.ascent(), metrics.descent())
            else:
                tkr_y = (self.ticker_height + metrics.ascent() - metrics.descent()) // 2
            symbol_rect = QtCore.QRect(x, 0, tkr_width, self.ticker_height)
            painter.setFont(self.ticker_font)
            self.draw_text_with_global_glow(painter, x, tkr_y, display_name, QtGui.QColor("#00B3FF"), settings=settings)
            x += tkr_width

            if self.show_sparklines and getattr(self, 'sparkline_position', 'left') == 'left':
                sparkline_height = max(12, int(self.ticker_height * 0.34))
                sparkline = self._get_sparkline_pixmap(tkr, 50, sparkline_height)
                sparkline_y = (self.ticker_height - sparkline.height()) // 2
                painter.drawPixmap(x, sparkline_y, sparkline)
                x += 50 + 8

            price_y = tkr_y
            price_color = self.get_display_price_color(tkr, price, prev)
            
            # Calculate change percentage for glow effect
            change_percent = 0
            if price is not None and prev is not None and prev != 0:
                if USE_OPT:
                    change_percent = opt.calculate_change_percent(price, prev)
                else:
                    change_percent = ((price - prev) / prev) * 100
            
            # Check for glow effect on big price changes
            glow_color = self.get_glow_effect(tkr, change_percent)
            
            price_rect = QtCore.QRect(x, 0, price_width, self.ticker_height)
            
            # Draw price text with appropriate glow
            painter.setFont(self.ticker_font)
            if glow_color:
                # Draw 5% glow effect (more intense, colored) - replaces global glow
                painter.setPen(glow_color)
                if USE_OPT:
                    for dx, dy in opt.get_glow_offsets():
                        painter.drawText(x + dx, price_y + dy, price_text)
                else:
                    for dx in [-2, -1, 0, 1, 2]:
                        for dy in [-2, -1, 0, 1, 2]:
                            if dx != 0 or dy != 0:
                                painter.drawText(x + dx, price_y + dy, price_text)
                # Draw main price text without global glow (5% glow is sufficient)
                painter.setPen(price_color)
                painter.drawText(x, price_y, price_text)
            else:
                # No 5% glow, use global glow if enabled
                self.draw_text_with_global_glow(painter, x, price_y, price_text, price_color, settings=settings)
            x += price_width
            change_rect = None  # Initialize change_rect
            if change_text or pct_text:
                painter.setFont(small_font)
                stacked_height = small_metrics.height() * 2 + 2
                stacked_top = (self.ticker_height - stacked_height) // 2 + small_metrics.ascent()
                # Determine color: green for positive, red for negative, white for zero
                if change > 0:
                    color = QtGui.QColor("#00FF40")  # Green
                elif change < 0:
                    color = QtGui.QColor("#FF5555")  # Red
                else:
                    color = QtGui.QColor("#FFFFFF")  # White for zero change

                stale_fade_factor = self.get_stale_fade_factor(tkr)
                color = self.apply_fade_to_color(color, stale_fade_factor)
                if glow_color:
                    glow_color = self.apply_fade_to_color(glow_color, stale_fade_factor)
                
                # Create rect for change area (for bloom effect) - now includes triangle
                change_rect = QtCore.QRect(x + 10, 0, change_width + triangle_width, self.ticker_height)
                
                painter.setFont(small_font)
                
                # Apply glow effect to change text if 5% glow is active
                if glow_color:
                    painter.setPen(glow_color)
                    if USE_OPT:
                        for dx, dy in opt.get_glow_offsets():
                            painter.drawText(x + 10 + dx, stacked_top + dy, change_text)
                            painter.drawText(x + 10 + dx, stacked_top + small_metrics.height() + 2 + dy, pct_text)
                    else:
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
                    self.draw_text_with_global_glow(painter, x + 10, stacked_top, change_text, color, settings=settings)
                    self.draw_text_with_global_glow(painter, x + 10, stacked_top + small_metrics.height() + 2, pct_text, color, settings=settings)
                
                # Draw rotated indicator (triangle, arrow, or thin arrow) to the right of the change_text (top line)
                change_text_width = small_metrics.horizontalAdvance(change_text)
                
                # Check which indicator style to use
                indicator_style = settings.get("price_indicator_style", "triangles")
                
                # Adjust spacing based on indicator style (thin arrows closer to text)
                if indicator_style == "thin_arrows":
                    indicator_x = x + 10 + change_text_width + 6  # 6px padding for thin arrows
                else:
                    indicator_x = x + 10 + change_text_width + 13  # Slightly tighter spacing for geometric shapes
                
                # Position indicator centered on the text line with rotation-based adjustment
                base_indicator_y = stacked_top - small_metrics.ascent() // 2
                # Adjust Y position based on rotation to keep visual center aligned
                if triangle_rotation == 0:  # Up
                    indicator_y = base_indicator_y + 2  # Move down slightly (top-heavy)
                elif triangle_rotation == 180:  # Down
                    indicator_y = base_indicator_y - 2  # Move up slightly (bottom-heavy)
                elif triangle_rotation in [45, 135]:  # Diagonal
                    indicator_y = base_indicator_y  # No adjustment needed
                else:  # 90 (right)
                    indicator_y = base_indicator_y  # No adjustment needed
                
                # Make indicator size dynamic based on ticker height (scales proportionally)
                indicator_size = int(self.ticker_height * 0.42)  # ~42% of ticker height
                
                if indicator_style == "thin_arrows":
                    # Use Unicode arrow symbols for thin arrows
                    arrow_map = {
                        0: "↑",     # Up
                        45: "↗",    # Up-right
                        90: "→",    # Right
                        135: "↘",   # Down-right
                        180: "↓"    # Down
                    }
                    arrow_symbol = arrow_map.get(triangle_rotation, "→")
                    
                    # Make arrows smaller
                    arrow_font = QtGui.QFont(small_font)
                    arrow_font.setPointSize(int(small_font.pointSize() * 0.7))  # Smaller arrows
                    
                    # Position arrows well above baseline to center them with the text height
                    arrow_metrics = QtGui.QFontMetrics(arrow_font)
                    arrow_y = stacked_top - arrow_metrics.ascent() // 2
                    
                    # Draw thin arrow with glow if 5% effect is active
                    if glow_color:
                        painter.setPen(glow_color)
                        painter.setFont(arrow_font)
                        for dx in [-1, 0, 1]:
                            for dy in [-1, 0, 1]:
                                if dx != 0 or dy != 0:
                                    painter.drawText(indicator_x + dx, arrow_y + dy, arrow_symbol)
                        # Draw main thin arrow
                        painter.setPen(color)
                        painter.drawText(indicator_x, arrow_y, arrow_symbol)
                    else:
                        # No glow, use global glow if enabled
                        painter.setFont(arrow_font)
                        painter.setPen(color)
                        painter.drawText(indicator_x, arrow_y, arrow_symbol)
                        painter.setFont(small_font)  # Restore small font
                else:
                    # Draw indicator with glow if 5% effect is active
                    if glow_color:
                        # Draw glow halos for indicator
                        for dx in [-1, 0, 1]:
                            for dy in [-1, 0, 1]:
                                if dx != 0 or dy != 0:
                                    if indicator_style == "arrows":
                                        self.draw_rotated_arrow(painter, indicator_x + dx, indicator_y + dy, 
                                                              indicator_size, triangle_rotation, glow_color)
                                    else:  # triangles
                                        self.draw_rotated_triangle(painter, indicator_x + dx, indicator_y + dy, 
                                                              indicator_size, triangle_rotation, glow_color)
                    
                    # Draw main indicator
                    if indicator_style == "arrows":
                        self.draw_rotated_arrow(painter, indicator_x, indicator_y, 
                                              indicator_size, triangle_rotation, color)
                    else:  # triangles
                        self.draw_rotated_triangle(painter, indicator_x, indicator_y, 
                                              indicator_size, triangle_rotation, color)
                
                painter.setFont(self.ticker_font)
                x += 10 + change_width + triangle_width

            if self.show_sparklines and getattr(self, 'sparkline_position', 'left') == 'right':
                sparkline_height = max(12, int(self.ticker_height * 0.34))
                sparkline = self._get_sparkline_pixmap(tkr, 50, sparkline_height)
                sparkline_y = (self.ticker_height - sparkline.height()) // 2
                painter.drawPixmap(x, sparkline_y, sparkline)
                x += 50 + 8
            painter.setFont(self.ticker_font)
            self.draw_text_with_global_glow(painter, x, tkr_y, sep, QtGui.QColor("#00B3FF"), settings=settings)
            painter.end()
            # Cache ghost (tinted) version for this pixmap for fast ghost rendering
            ghost_pixmap = QtGui.QPixmap(pixmap.size())
            ghost_pixmap.fill(QtCore.Qt.transparent)
            ggp = QtGui.QPainter(ghost_pixmap)
            ggp.drawPixmap(0, 0, pixmap)
            ggp.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
            # Compute ghost color strength and alpha from single intensity setting
            intensity = settings.get("led_ghost_intensity", 100)
            galpha_pct = int(intensity * 0.45)
            color_strength = intensity * 1.4 / 100.0
            dominant = calculate_pixmap_dominant_color(pixmap)
            sub_r = int(min(255, dominant.red() * color_strength + 40))
            sub_g = int(min(255, dominant.green() * color_strength + 40))
            sub_b = int(min(255, dominant.blue() * color_strength + 40))
            tint_color = QtGui.QColor(sub_r, sub_g, sub_b)
            tint_color.setAlpha(int(galpha_pct * 2.55))

            # DEBUG OVERRIDE: force vivid tint if debug mode enabled
            if getattr(self, '_ghost_debug_force_visible', False):
                tint_color = getattr(self, '_ghost_debug_force_tint', tint_color)

            ggp.fillRect(ghost_pixmap.rect(), tint_color)
            ggp.end()

            if getattr(self, '_ghost_debug_logging', False):
                try:
                    img = ghost_pixmap.toImage()
                    w = img.width(); h = img.height()
                    cx, cy = w//2, h//2
                    center_alpha = img.pixelColor(cx, cy).alpha()
                    ssum = 0; scount = 0
                    for sx in range(max(0, cx-1), min(w, cx+2)):
                        for sy in range(max(0, cy-1), min(h, cy+2)):
                            ssum += img.pixelColor(sx, sy).alpha()
                            scount += 1
                    avg_alpha = ssum // scount if scount else 0
                    print(f"[GHOST BUILD DEBUG] pixmap for {display_name} center_alpha={center_alpha}, avg_center_alpha={avg_alpha}, tint_alpha={tint_color.alpha()}")
                except Exception:
                    pass

            self.ticker_pixmaps.append(pixmap)
            self.ticker_ghost_pixmaps.append(ghost_pixmap)
            self.ticker_pixmap_widths.append(total_width)
            # Add change_rect to areas if it exists
            if change_rect:
                self.ticker_area_templates.append([
                    ('symbol', tkr, symbol_rect),
                    ('price', tkr, price_rect),
                    ('change', tkr, change_rect)
                ])
            else:
                self.ticker_area_templates.append([
                    ('symbol', tkr, symbol_rect),
                    ('price', tkr, price_rect)
                ])
        donate_text = "      Please Donate!          "
        donate_font = self.ticker_font
        metrics = QtGui.QFontMetrics(donate_font)
        donate_height = self.ticker_height
        donate_pixmap_width = metrics.horizontalAdvance(donate_text) + 40
        
        # Use memory pool for donate pixmap if available
        if USE_MEMORY_POOL:
            donate_pixmap = get_pooled_pixmap(donate_pixmap_width, donate_height)
        else:
            donate_pixmap = QtGui.QPixmap(donate_pixmap_width, donate_height)
        donate_pixmap.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(donate_pixmap)
        donate_y = donate_height // 2 + metrics.ascent() // 2
        
        # Use optimized rainbow color generation and positioning
        if USE_OPT:
            # Generate rainbow colors using Numba optimization
            rainbow_rgb = opt.generate_rainbow_colors(len(donate_text), 7)
            
            # Pre-calculate character widths for positioning
            import numpy as np
            char_widths = np.array([metrics.horizontalAdvance(char) for char in donate_text], dtype=np.int32)
            
            # Calculate optimized character positions
            positions = opt.calculate_character_positions(len(donate_text), char_widths, 20)
            
            # Render characters with pre-calculated positions and colors
            for i, char in enumerate(donate_text):
                x = positions[i]
                r, g, b = rainbow_rgb[i]
                color = QtGui.QColor(r, g, b)
                painter.setFont(donate_font)
                
                # Draw shadow (standard, same as before)
                painter.setPen(QtGui.QColor("black"))
                painter.drawText(x + 1, donate_y + 1, char)
                
                # Draw character with color-matched rainbow glow (same intensity as ticker symbols)
                rainbow_glow = QtGui.QColor(r, g, b, 15)  # Same as default global glow
                self.draw_text_with_global_glow(painter, x, donate_y, char, color, glow_color=rainbow_glow, settings=settings)
        else:
            # Fall back to original implementation
            rainbow_colors = [
                "#FF0000", "#FF7F00", "#FFFF00", "#00FF00", "#00B3FF", "#4B0082", "#9400D3"
            ]
            colors = [rainbow_colors[i % len(rainbow_colors)] for i in range(len(donate_text))]
            
            x = 20
            for i, char in enumerate(donate_text):
                color = QtGui.QColor(colors[i])
                painter.setFont(donate_font)
                
                # Draw shadow (standard, same as before)
                painter.setPen(QtGui.QColor("black"))
                painter.drawText(x + 1, donate_y + 1, char)
                
                # Draw character with color-matched rainbow glow (same intensity as ticker symbols)
                rainbow_glow = QtGui.QColor(color.red(), color.green(), color.blue(), 15)
                self.draw_text_with_global_glow(painter, x, donate_y, char, color, glow_color=rainbow_glow, settings=settings)
                x += metrics.horizontalAdvance(char)
                
        painter.end()
        # Cache tinted ghost for donate pixmap used by ghosting layers
        donate_ghost = QtGui.QPixmap(donate_pixmap.size())
        donate_ghost.fill(QtCore.Qt.transparent)
        dgp = QtGui.QPainter(donate_ghost)
        dgp.drawPixmap(0, 0, donate_pixmap)
        dgp.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
        # Compute ghost color strength and alpha from single intensity setting
        intensity = settings.get("led_ghost_intensity", 100)
        galpha_pct = int(intensity * 0.45)
        color_strength = intensity * 1.4 / 100.0
        dominant = calculate_pixmap_dominant_color(donate_pixmap)
        sub_r = int(min(255, dominant.red() * color_strength + 40))
        sub_g = int(min(255, dominant.green() * color_strength + 40))
        sub_b = int(min(255, dominant.blue() * color_strength + 40))
        donate_tint = QtGui.QColor(sub_r, sub_g, sub_b)
        donate_tint.setAlpha(int(galpha_pct * 2.55))
        dgp.fillRect(donate_ghost.rect(), donate_tint)
        dgp.end()

        self._donate_pixmap = donate_pixmap
        self._donate_ghost_pixmap = donate_ghost
        self._donate_pixmap_width = donate_pixmap_width
        self._donate_area_template = [('donate', 'DONATE', QtCore.QRect(0, 0, donate_pixmap_width, donate_height))]

    def build_ticker_pixmaps_for_symbols(self, symbols):
        """Incrementally rebuild pixmaps for the given list of symbols.
        This replaces only the affected pixmaps in-place to minimize stutter.
        """
        if not symbols:
            return

        # Ensure we have existing pixmaps; otherwise fall back to full rebuild
        if not hasattr(self, 'ticker_pixmaps') or not self.ticker_pixmaps:
            self.build_ticker_text(reset_scroll=False)
            return

        settings = self._cached_settings if hasattr(self, '_cached_settings') else get_settings()
        metrics = QtGui.QFontMetrics(self.ticker_font)
        if USE_OPT:
            icon_size = opt.calculate_icon_size(self.ticker_height, 0.85)
        else:
            icon_size = int(self.ticker_height * 0.85)

        small_font = QtGui.QFont(self.ticker_font)
        small_font.setPointSize(max(8, int(self.ticker_font.pointSize() * 0.5)))
        small_metrics = QtGui.QFontMetrics(small_font)

        # Invalidate bloom cache when content changes
        self.bloom_cache_valid = False

        updated_any = False
        for symbol in symbols:
            if symbol not in self.stocks:
                continue
            try:
                idx = self.stocks.index(symbol)
            except ValueError:
                continue

            # Build single stock pixmap (mirrors logic in build_ticker_pixmaps)
            tkr = symbol
            display_name = INDEX_DISPLAY_NAMES.get(tkr, tkr)
            price, prev = self.prices.get(tkr, (None, None))
            icon = get_ticker_icon(tkr, icon_size)
            tkr_width = metrics.horizontalAdvance(display_name + " ")
            sparkline_width = 50 if self.show_sparklines else 0
            sparkline_gap = 8 if self.show_sparklines else 0
            price_text = f"{price:.2f}" if price is not None else "N/A"
            price_width = metrics.horizontalAdvance(price_text)
            change_text = ""
            pct_text = ""
            change = 0
            pct = 0
            triangle_rotation = 90
            if price is not None and prev is not None:
                change = price - prev
                pct = (change / prev * 100) if prev else 0
                triangle_rotation = self.get_triangle_rotation(pct)
                if change > 0:
                    change_text = f"+{abs(change):.2f}"
                    pct_text = f"+{abs(pct):.2f}%"
                elif change < 0:
                    change_text = f"-{abs(change):.2f}"
                    pct_text = f"-{abs(pct):.2f}%"
                else:
                    change_text = f"{change:.2f}"
                    pct_text = f"{pct:.2f}%"

            change_width = max(small_metrics.horizontalAdvance(change_text), small_metrics.horizontalAdvance(pct_text)) if (change_text or pct_text) else 0
            if change_text or pct_text:
                indicator_style_for_width = settings.get("price_indicator_style", "triangles")
                if indicator_style_for_width == "thin_arrows":
                    triangle_width = 14
                else:
                    indicator_size_for_width = int(self.ticker_height * 0.42)
                    triangle_width = max(20, 13 + (indicator_size_for_width // 2) + 2)
            else:
                triangle_width = 0
            sep = "      "
            sep_width = metrics.horizontalAdvance(sep)
            total_width = icon_size + 8 + tkr_width + sparkline_width + sparkline_gap + price_width + (10 + change_width + triangle_width if change_width else 0) + sep_width + 20

            if USE_MEMORY_POOL:
                pixmap = get_pooled_pixmap(total_width, self.ticker_height)
            else:
                pixmap = QtGui.QPixmap(total_width, self.ticker_height)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            x = 0
            if USE_OPT:
                icon_y = opt.calculate_icon_y_position(self.ticker_height, icon_size)
            else:
                icon_y = (self.ticker_height - icon_size) // 2
            painter.drawPixmap(x, icon_y, icon)
            x += icon_size + 8

            if USE_OPT:
                tkr_y = opt.calculate_text_position(self.ticker_height, metrics.ascent(), metrics.descent())
            else:
                tkr_y = (self.ticker_height + metrics.ascent() - metrics.descent()) // 2
            symbol_rect = QtCore.QRect(x, 0, tkr_width, self.ticker_height)
            painter.setFont(self.ticker_font)
            self.draw_text_with_global_glow(painter, x, tkr_y, display_name, QtGui.QColor("#00B3FF"), settings=settings)
            x += tkr_width

            if self.show_sparklines and getattr(self, 'sparkline_position', 'left') == 'left':
                sparkline_height = max(12, int(self.ticker_height * 0.34))
                sparkline = self._get_sparkline_pixmap(tkr, 50, sparkline_height)
                sparkline_y = (self.ticker_height - sparkline.height()) // 2
                painter.drawPixmap(x, sparkline_y, sparkline)
                x += 50 + 8

            price_y = tkr_y

            price_color = self.get_display_price_color(tkr, price, prev)

            change_percent = 0
            if price is not None and prev is not None and prev != 0:
                if USE_OPT:
                    change_percent = opt.calculate_change_percent(price, prev)
                else:
                    change_percent = ((price - prev) / prev) * 100

            glow_color = self.get_glow_effect(tkr, change_percent)
            price_rect = QtCore.QRect(x, 0, price_width, self.ticker_height)

            painter.setFont(self.ticker_font)
            if glow_color:
                painter.setPen(glow_color)
                if USE_OPT:
                    for dx, dy in opt.get_glow_offsets():
                        painter.drawText(x + dx, price_y + dy, price_text)
                else:
                    for dx in [-2, -1, 0, 1, 2]:
                        for dy in [-2, -1, 0, 1, 2]:
                            if dx != 0 or dy != 0:
                                painter.drawText(x + dx, price_y + dy, price_text)
                painter.setPen(price_color)
                painter.drawText(x, price_y, price_text)
            else:
                self.draw_text_with_global_glow(painter, x, price_y, price_text, price_color, settings=settings)
            x += price_width

            change_rect = None
            if change_text or pct_text:
                painter.setFont(small_font)
                stacked_height = small_metrics.height() * 2 + 2
                stacked_top = (self.ticker_height - stacked_height) // 2 + small_metrics.ascent()
                if change > 0:
                    color = QtGui.QColor("#00FF40")
                elif change < 0:
                    color = QtGui.QColor("#FF5555")
                else:
                    color = QtGui.QColor("#FFFFFF")

                stale_fade_factor = self.get_stale_fade_factor(tkr)
                color = self.apply_fade_to_color(color, stale_fade_factor)
                if glow_color:
                    glow_color = self.apply_fade_to_color(glow_color, stale_fade_factor)

                change_rect = QtCore.QRect(x + 10, 0, change_width + triangle_width, self.ticker_height)
                painter.setFont(small_font)
                if glow_color:
                    painter.setPen(glow_color)
                    if USE_OPT:
                        for dx, dy in opt.get_glow_offsets():
                            painter.drawText(x + 10 + dx, stacked_top + dy, change_text)
                            painter.drawText(x + 10 + dx, stacked_top + small_metrics.height() + 2 + dy, pct_text)
                    else:
                        for dx in [-2, -1, 0, 1, 2]:
                            for dy in [-2, -1, 0, 1, 2]:
                                if dx != 0 or dy != 0:
                                    painter.drawText(x + 10 + dx, stacked_top + dy, change_text)
                                    painter.drawText(x + 10 + dx, stacked_top + small_metrics.height() + 2 + dy, pct_text)
                    painter.setPen(color)
                    painter.drawText(x + 10, stacked_top, change_text)
                    painter.drawText(x + 10, stacked_top + small_metrics.height() + 2, pct_text)
                else:
                    self.draw_text_with_global_glow(painter, x + 10, stacked_top, change_text, color, settings=settings)
                    self.draw_text_with_global_glow(painter, x + 10, stacked_top + small_metrics.height() + 2, pct_text, color, settings=settings)

                # Draw indicator (simplified positioning reused from main builder)
                change_text_width = small_metrics.horizontalAdvance(change_text)
                indicator_style = settings.get("price_indicator_style", "triangles")
                if indicator_style == "thin_arrows":
                    indicator_x = x + 10 + change_text_width + 6
                else:
                    indicator_x = x + 10 + change_text_width + 13
                base_indicator_y = stacked_top - small_metrics.ascent() // 2
                if triangle_rotation == 0:
                    indicator_y = base_indicator_y + 2
                elif triangle_rotation == 180:
                    indicator_y = base_indicator_y - 2
                else:
                    indicator_y = base_indicator_y
                indicator_size = int(self.ticker_height * 0.42)
                if indicator_style == "thin_arrows":
                    arrow_map = {0: "↑", 45: "↗", 90: "→", 135: "↘", 180: "↓"}
                    arrow_symbol = arrow_map.get(triangle_rotation, "→")
                    arrow_font = QtGui.QFont(small_font)
                    arrow_font.setPointSize(int(small_font.pointSize() * 0.7))
                    arrow_metrics = QtGui.QFontMetrics(arrow_font)
                    arrow_y = stacked_top - arrow_metrics.ascent() // 2
                    if glow_color:
                        painter.setPen(glow_color)
                        painter.setFont(arrow_font)
                        for dx in [-1, 0, 1]:
                            for dy in [-1, 0, 1]:
                                if dx != 0 or dy != 0:
                                    painter.drawText(indicator_x + dx, arrow_y + dy, arrow_symbol)
                        painter.setPen(color)
                        painter.drawText(indicator_x, arrow_y, arrow_symbol)
                    else:
                        painter.setFont(arrow_font)
                        painter.setPen(color)
                        painter.drawText(indicator_x, arrow_y, arrow_symbol)
                        painter.setFont(small_font)
                else:
                    if glow_color:
                        for dx in [-1, 0, 1]:
                            for dy in [-1, 0, 1]:
                                if dx != 0 or dy != 0:
                                    if indicator_style == "arrows":
                                        self.draw_rotated_arrow(painter, indicator_x + dx, indicator_y + dy, indicator_size, triangle_rotation, glow_color)
                                    else:
                                        self.draw_rotated_triangle(painter, indicator_x + dx, indicator_y + dy, indicator_size, triangle_rotation, glow_color)
                    if indicator_style == "arrows":
                        self.draw_rotated_arrow(painter, indicator_x, indicator_y, indicator_size, triangle_rotation, color)
                    else:
                        self.draw_rotated_triangle(painter, indicator_x, indicator_y, indicator_size, triangle_rotation, color)

                painter.setFont(self.ticker_font)
                x += 10 + change_width + triangle_width

            if self.show_sparklines and getattr(self, 'sparkline_position', 'left') == 'right':
                sparkline_height = max(12, int(self.ticker_height * 0.34))
                sparkline = self._get_sparkline_pixmap(tkr, 50, sparkline_height)
                sparkline_y = (self.ticker_height - sparkline.height()) // 2
                painter.drawPixmap(x, sparkline_y, sparkline)
                x += 50 + 8

            painter.setFont(self.ticker_font)
            self.draw_text_with_global_glow(painter, x, tkr_y, sep, QtGui.QColor("#00B3FF"), settings=settings)
            painter.end()

            # Replace existing pixmap entries (market pixmap is index 0)
            target_index = idx + 1
            # Ensure lists are long enough
            if target_index < len(self.ticker_pixmaps):
                    # Replace main pixmap
                    self.ticker_pixmaps[target_index] = pixmap
                    self.ticker_pixmap_widths[target_index] = total_width
                    # Create and replace tinted ghost version
                    ghost_pixmap = QtGui.QPixmap(pixmap.size())
                    ghost_pixmap.fill(QtCore.Qt.transparent)
                    ggp = QtGui.QPainter(ghost_pixmap)
                    ggp.drawPixmap(0, 0, pixmap)
                    ggp.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
                    intensity = settings.get("led_ghost_intensity", 100)
                    galpha_pct = int(intensity * 0.45)
                    color_strength = intensity * 1.4 / 100.0
                    dominant = calculate_pixmap_dominant_color(pixmap)
                    sub_r = int(min(255, dominant.red() * color_strength + 40))
                    sub_g = int(min(255, dominant.green() * color_strength + 40))
                    sub_b = int(min(255, dominant.blue() * color_strength + 40))
                    tint_color = QtGui.QColor(sub_r, sub_g, sub_b)
                    tint_color.setAlpha(int(galpha_pct * 2.55))
                    ggp.fillRect(ghost_pixmap.rect(), tint_color)
                    ggp.end()
                    if target_index < len(self.ticker_ghost_pixmaps):
                        self.ticker_ghost_pixmaps[target_index] = ghost_pixmap
                    else:
                        # Should not happen, but append to keep lists consistent
                        self.ticker_ghost_pixmaps.append(ghost_pixmap)

                    if change_rect:
                        self.ticker_area_templates[target_index] = [
                            ('symbol', tkr, symbol_rect),
                            ('price', tkr, price_rect),
                            ('change', tkr, change_rect)
                        ]
                    else:
                        self.ticker_area_templates[target_index] = [
                            ('symbol', tkr, symbol_rect),
                            ('price', tkr, price_rect)
                        ]
                    updated_any = True
        # If we changed any pixmaps, trigger repaint and re-calc cycle width
        if updated_any:
            # Recompute cycle width in case widths changed
            try:
                self._cycle_width = sum(self.ticker_pixmap_widths)
            except Exception:
                pass
            # Trigger repaint
            try:
                if hasattr(self, 'gl_widget') and self.gl_widget:
                    self.gl_widget.update()
                else:
                    self.update()
            except Exception:
                pass

    def get_cycle_width(self):
        return sum(self.ticker_pixmap_widths)

    @QtCore.pyqtSlot(str, object, int, int, str)
    def _on_sparkline_ready(self, symbol, pixmap, width, height, period):
        key = (symbol.upper(), period, int(width), int(height))
        self.sparkline_cache[key] = (time.time(), pixmap)
        with self.sparkline_lock:
            self.sparkline_inflight.discard(key)
        if symbol in self.stocks:
            self.queue_incremental_pixmap_updates([symbol])

    def _process_sparkline_rebuild_tick(self):
        """Batch rebuild sparkline visuals to reduce per-symbol stutter."""
        if not getattr(self, 'show_sparklines', False):
            return
        try:
            self.build_ticker_pixmaps()
            if hasattr(self, 'gl_widget') and self.gl_widget:
                self.gl_widget.update()
        except Exception:
            pass

    def _sparkline_placeholder(self, width, height):
        pm = QtGui.QPixmap(width, height)
        pm.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pm)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.setPen(QtGui.QPen(QtGui.QColor(110, 130, 150, 180), 1))
        y = height // 2
        painter.drawLine(0, y, width - 1, y)
        painter.end()
        return pm

    def _build_sparkline_pixmap(self, values, width, height):
        pm = QtGui.QPixmap(width, height)
        pm.fill(QtCore.Qt.transparent)
        if not values or len(values) < 2:
            return self._sparkline_placeholder(width, height)

        low = min(values)
        high = max(values)
        span = (high - low) if high != low else 1.0

        points = []
        count = len(values)
        for idx, value in enumerate(values):
            x = int(idx * (width - 1) / max(1, count - 1))
            y = int((1.0 - ((value - low) / span)) * (height - 1))
            points.append(QtCore.QPoint(x, y))

        up = values[-1] >= values[0]
        line_color = QtGui.QColor("#00FF40" if up else "#FF5555")

        painter = QtGui.QPainter(pm)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtGui.QPen(line_color, 1.6))
        for i in range(1, len(points)):
            painter.drawLine(points[i - 1], points[i])
        painter.end()
        return pm

    def _request_sparkline_async(self, symbol, width, height):
        period = self.sparkline_period
        key = (symbol.upper(), period, int(width), int(height))

        with self.sparkline_lock:
            if key in self.sparkline_inflight:
                return
            self.sparkline_inflight.add(key)

        def worker():
            try:
                interval = "5m" if period == "1d" else "30m"
                encoded_symbol = url_quote(symbol, safe='')
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range={period}&interval={interval}"

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

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }

                response = get_requests_session().get(
                    url,
                    headers=headers,
                    timeout=10,
                    proxies=proxies,
                    verify=verify
                )
                response.raise_for_status()
                data = response.json()

                values = []
                result = data.get("chart", {}).get("result", [])
                if result:
                    indicators = result[0].get("indicators", {})
                    quote_data = indicators.get("quote", [])
                    if quote_data:
                        closes = quote_data[0].get("close", [])
                        values = [float(v) for v in closes if v is not None]

                        # Fallback to open/high/low if close has insufficient points
                        if len(values) < 2:
                            for fallback_field in ("open", "high", "low"):
                                fallback_vals = [float(v) for v in quote_data[0].get(fallback_field, []) if v is not None]
                                if len(fallback_vals) >= 2:
                                    values = fallback_vals
                                    break

                    # Extra fallback: adjusted close series
                    if len(values) < 2:
                        adjclose_data = indicators.get("adjclose", [])
                        if adjclose_data:
                            adj_vals = [float(v) for v in adjclose_data[0].get("adjclose", []) if v is not None]
                            if len(adj_vals) >= 2:
                                values = adj_vals

                # One-time success diagnostic per symbol/period
                log_key = (symbol.upper(), period)
                if len(values) >= 2 and log_key not in self._sparkline_logged_success:
                    self._sparkline_logged_success.add(log_key)
                    colored_print(f"[SPARKLINE] {symbol} {period}: fetched {len(values)} points")

                sparkline_pixmap = self._build_sparkline_pixmap(values, width, height)
                self.sparkline_ready.emit(symbol, sparkline_pixmap, width, height, period)
            except Exception as e:
                log_key = (symbol.upper(), period)
                if log_key not in self._sparkline_logged_failures:
                    self._sparkline_logged_failures.add(log_key)
                    colored_print(f"[SPARKLINE] {symbol} {period}: fetch failed ({e})")
                placeholder = self._sparkline_placeholder(width, height)
                self.sparkline_ready.emit(symbol, placeholder, width, height, period)

        threading.Thread(target=worker, daemon=True).start()

    def _get_sparkline_pixmap(self, symbol, width=50, height=18):
        key = (symbol.upper(), self.sparkline_period, int(width), int(height))
        ttl_seconds = 600 if self.sparkline_period == "1d" else 1800
        cached = self.sparkline_cache.get(key)

        if cached:
            timestamp, cached_pixmap = cached
            if (time.time() - timestamp) < ttl_seconds:
                return cached_pixmap

        self._request_sparkline_async(symbol, width, height)
        return self._sparkline_placeholder(width, height)

    def queue_incremental_pixmap_updates(self, symbols):
        """Queue symbols for throttled incremental pixmap rebuilds.
        Symbols are deduplicated and processed in FIFO order across timer ticks.
        """
        if not symbols:
            return

        added = False
        for s in symbols:
            if s not in self._pending_pixmap_set:
                self._pending_pixmap_set.add(s)
                self._pending_pixmap_list.append(s)
                added = True
        if added and not self.incremental_rebuild_timer.isActive():
            self.incremental_rebuild_timer.start(self.incremental_rebuild_interval_ms)

    def _process_incremental_rebuild_tick(self):
        """Process a small batch of pending symbols per timer tick."""
        try:
            if not self._pending_pixmap_list:
                if self.incremental_rebuild_timer.isActive():
                    self.incremental_rebuild_timer.stop()
                return

            batch_count = min(self.incremental_rebuild_max_per_tick, len(self._pending_pixmap_list))
            batch = []
            for _ in range(batch_count):
                sym = self._pending_pixmap_list.pop(0)
                self._pending_pixmap_set.discard(sym)
                if hasattr(self, 'stocks') and sym in self.stocks:
                    batch.append(sym)

            if batch:
                try:
                    self.build_ticker_pixmaps_for_symbols(batch)
                except Exception:
                    # On error, fall back to full rebuild for this ticker
                    try:
                        self.build_ticker_text(reset_scroll=False)
                    except Exception:
                        pass

            # Stop timer if queue emptied
            if not self._pending_pixmap_list and self.incremental_rebuild_timer.isActive():
                self.incremental_rebuild_timer.stop()
        except Exception:
            # Defensive: ensure timer won't spin on errors
            if self.incremental_rebuild_timer.isActive():
                self.incremental_rebuild_timer.stop()

    def apply_led_flicker(self, painter, width, height, settings):
        """
        Apply realistic LED flickering effect.
        LEDs have subtle brightness variations that make them look more authentic.
        Uses time-based random variations for natural flicker patterns.
        OPTIMIZED WITH NUMBA for 3-5x faster calculations.
        """
        # Check if LED flicker effect is enabled in settings (using cached settings)
        if not settings.get("led_flicker_effect", True):
            return  # Skip flicker effect if disabled
        
        current_time = time.time()
        
        # Use optimized Numba function for flicker calculations
        if USE_OPT:
            variations = opt.calculate_flicker_brightness_variations(current_time, width, height, 15)
            
            # Apply flicker spots using pre-calculated variations
            for i in range(variations.shape[0]):
                fx = int(variations[i, 0])
                fy = int(variations[i, 1])
                flicker_width = int(variations[i, 2])
                flicker_height = int(variations[i, 3])
                brightness_delta = int(variations[i, 4])
                
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
            
            # Use optimized surge effect calculation
            has_surge, surge_intensity = opt.calculate_power_surge_effect(current_time)
            if has_surge:
                surge_color = QtGui.QColor(255, 255, 255, surge_intensity)
                painter.setBrush(QtGui.QBrush(surge_color))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRect(0, 0, width, height)
            
            # Use optimized scan line position calculation
            scan_y = opt.calculate_scan_line_position(current_time, height)
            scan_color = QtGui.QColor(255, 255, 255, 8)
            painter.fillRect(0, scan_y, width, 2, scan_color)
            
        else:
            # Fall back to original implementation if Numba not available
            import random
            
            flicker_seed = int(current_time * 60)  # Changes every ~16ms for 60fps
            random.seed(flicker_seed)
            
            # Create subtle random brightness variations across the display
            num_flicker_spots = 15  # Number of brightness variation areas
            
            for _ in range(num_flicker_spots):
                # Random position for flicker spot
                fx = random.randint(0, width)
                fy = random.randint(0, height)
                
                # Random size for flicker area (small spots)
                flicker_width = random.randint(20, 80)
                flicker_height = random.randint(10, 30)
                
                # Random brightness variation (very subtle)
                brightness_delta = random.randint(-15, 20)
                
                # Create semi-transparent overlay for flicker effect
                if brightness_delta > 0:
                    flicker_color = QtGui.QColor(255, 255, 255, brightness_delta)
                else:
                    flicker_color = QtGui.QColor(0, 0, 0, abs(brightness_delta))
                
                # Apply flicker with soft edges (ellipse for smooth transitions)
                painter.setBrush(QtGui.QBrush(flicker_color))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawEllipse(fx - flicker_width//2, fy - flicker_height//2, 
                                  flicker_width, flicker_height)
            
            # Add occasional "power surge" flicker
            surge_chance = random.random()
            if surge_chance < 0.05:  # 5% chance each frame
                surge_intensity = random.randint(5, 15)
                surge_color = QtGui.QColor(255, 255, 255, surge_intensity)
                painter.setBrush(QtGui.QBrush(surge_color))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRect(0, 0, width, height)
            
            # Add subtle horizontal scan line flicker
            scan_y = int((current_time * 200) % height)
            scan_color = QtGui.QColor(255, 255, 255, 8)
            painter.fillRect(0, scan_y, width, 2, scan_color)

    def apply_bloom_effect(self, painter, width, height, settings):
        """
        Apply bloom/glow effect around bright colors.
        DIRECT RENDERING: No caching to avoid rebuild flashing.
        Draws bloom halos directly each frame.
        """
        # Check if bloom effect is enabled
        if not settings.get("led_bloom_effect", True):
            return
        
        # Compute nonlinear bloom intensity factor from user setting (0-100)
        bloom_intensity_pct = settings.get("led_bloom_intensity", 100)
        bloom_intensity = calculate_bloom_factor(bloom_intensity_pct)
        
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        painter.setPen(QtCore.Qt.NoPen)
        
        # If ticker_click_areas is empty (e.g., effects called before main draw), estimate positions
        if not self.ticker_click_areas:
            try:
                base_cycle_width = self.get_cycle_width()
                donate_cycle_width = self._donate_pixmap_width + base_cycle_width
                if USE_OPT:
                    cycle_positions_array = opt.calculate_cycle_positions(self.offset, width, base_cycle_width, donate_cycle_width, 20)
                    cycle_iter = ((float(cycle_positions_array[i, 0]), cycle_positions_array[i, 1] == 1)
                                  for i in range(cycle_positions_array.shape[0]))
                else:
                    cycle_iter = []
                    x = self.offset
                    est_cycles = (width // min(base_cycle_width, donate_cycle_width)) + 6
                    for i in range(est_cycles):
                        if i % 3 == 0:
                            cycle_iter.append((float(x), True))
                            x += donate_cycle_width
                        else:
                            cycle_iter.append((float(x), False))
                            x += base_cycle_width
                # Build temporary click area list
                tmp_clicks = []
                for x_pos, is_donate in cycle_iter:
                    draw_x = x_pos
                    for pixmap_widths, area_tpls in zip(self.ticker_pixmap_widths, self.ticker_area_templates):
                        # iterate through areas, translating rects
                        for area_type, tkr, rect in area_tpls:
                            offset_rect = QtCore.QRect(rect)
                            offset_rect.translate(int(draw_x), 0)
                            tmp_clicks.append((area_type, tkr, offset_rect))
                        draw_x += pixmap_widths
                    if is_donate:
                        for area_type, tkr, rect in self._donate_area_template:
                            offset_rect = QtCore.QRect(rect)
                            offset_rect.translate(int(draw_x), 0)
                            tmp_clicks.append((area_type, tkr, offset_rect))
                self.ticker_click_areas = tmp_clicks
            except Exception:
                # If estimation fails, proceed (no bloom will be drawn)
                pass

        # Draw bloom halos directly for each visible element
        for area_type, tkr, rect in self.ticker_click_areas:
            if area_type == 'icon':
                continue
            
            # Only draw bloom for elements visible on screen
            if rect.right() < 0 or rect.left() > width:
                continue
            
            bloom_radius = max(rect.width(), rect.height()) * 0.6
            center_x = rect.center().x()
            center_y = rect.center().y()
            
            gradient = QtGui.QRadialGradient(center_x, center_y, bloom_radius)
            
            # Set bloom color based on area type (increased alpha for stronger bloom)
            if area_type == 'price' or area_type == 'change':
                price, prev = self.prices.get(tkr, (None, None))
                if price is not None and prev is not None:
                    if price > prev:
                        gradient.setColorAt(0, QtGui.QColor(0, 255, 64, int(60 * bloom_intensity)))
                    elif price < prev:
                        gradient.setColorAt(0, QtGui.QColor(255, 85, 85, int(60 * bloom_intensity)))
                    else:
                        gradient.setColorAt(0, QtGui.QColor(255, 255, 255, int(45 * bloom_intensity)))
                else:
                    gradient.setColorAt(0, QtGui.QColor(255, 215, 0, int(45 * bloom_intensity)))
            elif area_type == 'symbol' or area_type == 'market_label':
                gradient.setColorAt(0, QtGui.QColor(0, 179, 255, int(55 * bloom_intensity)))
            elif area_type == 'market_status':
                if tkr == 'OPEN':
                    gradient.setColorAt(0, QtGui.QColor(0, 255, 64, int(60 * bloom_intensity)))
                else:
                    gradient.setColorAt(0, QtGui.QColor(255, 85, 85, int(60 * bloom_intensity)))
            elif area_type == 'donate':
                gradient.setColorAt(0, QtGui.QColor(255, 200, 255, int(55 * bloom_intensity)))
            else:
                gradient.setColorAt(0, QtGui.QColor(200, 220, 255, int(30 * bloom_intensity)))
            
            gradient.setColorAt(1, QtGui.QColor(0, 0, 0, 0))
            painter.setBrush(QtGui.QBrush(gradient))
            painter.drawEllipse(int(center_x - bloom_radius), int(center_y - bloom_radius), 
                               int(bloom_radius * 2), int(bloom_radius * 2))
        
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

    def apply_bloom_to_rect(self, painter, rect, width, height, settings=None, bloom_color=None):
        """
        Apply bloom effect to a specific rectangular area.
        Used for loading screen and other special cases.
        bloom_color: Optional QColor for the bloom (defaults to white if not specified)
        """
        # Get bloom intensity setting
        if settings:
            bloom_intensity_pct = settings.get("led_bloom_intensity", 100)
            bloom_intensity = calculate_bloom_factor(bloom_intensity_pct)
        else:
            bloom_intensity = 1.0
        
        # Use specified bloom color or default to white
        if bloom_color is None:
            bloom_color = QtGui.QColor(255, 255, 255)
            
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        
        # Create radial gradient bloom centered on the rectangle
        center_x = rect.center().x()
        center_y = rect.center().y()
        bloom_radius = max(rect.width(), rect.height()) * 0.8
        
        gradient = QtGui.QRadialGradient(center_x, center_y, bloom_radius)
        
        # Apply intensity to alpha values
        center_alpha = int(39 * bloom_intensity)
        mid_alpha = int(17 * bloom_intensity)
        
        # Use the bloom color with calculated alpha values
        bloom_center = QtGui.QColor(bloom_color.red(), bloom_color.green(), bloom_color.blue(), center_alpha)
        bloom_mid = QtGui.QColor(bloom_color.red(), bloom_color.green(), bloom_color.blue(), mid_alpha)
        bloom_edge = QtGui.QColor(bloom_color.red(), bloom_color.green(), bloom_color.blue(), 0)
        
        gradient.setColorAt(0, bloom_center)
        gradient.setColorAt(0.5, bloom_mid)
        gradient.setColorAt(1, bloom_edge)
        
        painter.setBrush(QtGui.QBrush(gradient))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(int(center_x - bloom_radius), int(center_y - bloom_radius), 
                          int(bloom_radius * 2), int(bloom_radius * 2))
        
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

    def apply_ghosting_effect(self, painter, width, height, settings, behind_main=False):
        """
        Apply motion blur/ghosting effect by drawing trailing layers of the ticker
        at small positive offsets (previous positions). Draw multiple layers with
        decreasing opacity. If behind_main is True, draw the ghosts after the
        background but before the main content so they appear between background
        and main pixmaps. Otherwise draw as an overlay (fallback).
        """
        # Check if ghosting effect is enabled (using cached settings)
        if not settings.get("led_ghosting_effect", True):
            return

        if getattr(self, '_ghost_debug_logging', False):
            try:
                import time as _time_mod
                now = _time_mod.time()
                last = getattr(self, '_ghost_debug_last', 0)
                if now - last > 1.0:
                    self._ghost_debug_last = now
                    ghost_count = len(getattr(self, 'ticker_ghost_pixmaps', [])) if hasattr(self, 'ticker_ghost_pixmaps') else 0
                    last_scroll = getattr(self, '_last_actual_scroll', None)
                    intensity = settings.get('led_ghost_intensity', None)
                    print(f"[GHOST DEBUG] enabled=True, ghost_count={ghost_count}, intensity={intensity}, last_scroll={last_scroll}")
            except Exception:
                pass

        base_cycle_width = self.get_cycle_width()
        donate_cycle_width = self._donate_pixmap_width + base_cycle_width

        # Use optimized ghosting position calculations
        if USE_OPT:
            ghost_offsets = opt.calculate_ghosting_positions(self.scroll_speed, 4)
            # convert to Python list
            ghost_offsets = [int(o) for o in ghost_offsets]
        else:
            base_offset = max(2, int(self.scroll_speed * 1.5))
            ghost_offsets = [base_offset + (i * 2) for i in range(4)]

        # Draw ghost layers: choose composition/placement based on 'behind_main'
        painter.save()
        # When drawing between background and main content, SourceOver is correct
        # (we'll call this before the main pixmap draw pass). If drawing as an
        # overlay (after everything), SourceOver with reduced opacity is used.
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

        # Draw farthest ghost first (lowest opacity), then closer ones
        # Use small, speed-relative offsets so ghosts trail closely to the main text
        num_layers = 3
        # Compute offsets relative to per-frame scroll for visually consistent trailing
        last_scroll = getattr(self, '_last_actual_scroll', None)
        if last_scroll is None or last_scroll <= 0:
            last_scroll = 1.0

        # Scale factors: near->far multipliers (in pixels relative to last_scroll)
        # These produce sensible distances at low and high speeds
        factors = [0.6, 1.2, 1.8][:num_layers]
        # Add a very small rightward bias so ghosts sit subtly to the right of the main text
        # Bias scales slightly with speed but stays tiny at low speeds to keep the effect subtle
        bias = max(0.6, min(2.0, last_scroll * 0.12))
        offsets = [max(1.0, min(40.0, last_scroll * f + bias)) for f in factors]

        total_draws_this_pass = 0
        for layer_idx, ghost_offset in enumerate(reversed(offsets)):
            # Ensure nearer layers are more visible. layer_idx iterates far->near so we map
            # the enumerated index to a factor where far layers get small factors and near
            # layers get larger factors (makes near layers more prominent).
            intensity = settings.get("led_ghost_intensity", 100) / 100.0
            layer_factor = (layer_idx + 1) / float(num_layers)  # far->near maps to small->large
            # Map factor toOpacity range [~0.12, 0.9] scaled by intensity to ensure visibility
            opacity = max(0.12, 0.9 * layer_factor) * intensity
            painter.setOpacity(opacity)

            if getattr(self, '_ghost_debug_logging', False):
                try:
                    import time as _time_mod
                    now = _time_mod.time()
                    last = getattr(self, '_ghost_opacity_log_last', 0)
                    if now - last > 1.0:
                        self._ghost_opacity_log_last = now
                        sample_alpha = None
                        if hasattr(self, 'ticker_ghost_pixmaps') and len(self.ticker_ghost_pixmaps) > 0:
                            try:
                                img = self.ticker_ghost_pixmaps[0].toImage()
                                sample_alpha = img.pixelColor(1, 1).alpha()
                            except Exception:
                                sample_alpha = None
                        print(f"[GHOST OPACITY DEBUG] layer_idx={layer_idx}, opacity={opacity:.3f}, sample_pixmap_alpha={sample_alpha}")
                except Exception:
                    pass

            # Calculate cycle positions for this ghost offset (use fractional offset)
            cycle_iter = []
            x = self.offset + ghost_offset
            est_cycles = (width // min(base_cycle_width, donate_cycle_width)) + 6
            for i in range(est_cycles):
                if i % 3 == 0:
                    cycle_iter.append((float(x), True))
                    x += donate_cycle_width
                else:
                    cycle_iter.append((float(x), False))
                    x += base_cycle_width

            # Draw the ghost cycle for this layer using pre-tinted ghost pixmaps
            draws_this_layer = 0
            for x_pos, is_donate in cycle_iter:
                draw_x = x_pos
                # Draw stock tickers first (use cached ghost pixmaps if available)
                if hasattr(self, 'ticker_ghost_pixmaps') and hasattr(self, 'ticker_pixmap_widths'):
                    for pixmap, w in zip(self.ticker_ghost_pixmaps, self.ticker_pixmap_widths):
                        if pixmap and not pixmap.isNull() and draw_x + w > 0 and draw_x < width:
                            painter.drawPixmap(QtCore.QPointF(draw_x, 0.0), pixmap)
                            draws_this_layer += 1
                            total_draws_this_pass += 1
                        draw_x += w
                # Then draw donate message at the end (if this cycle includes it)
                if is_donate and hasattr(self, '_donate_ghost_pixmap') and self._donate_ghost_pixmap and not self._donate_ghost_pixmap.isNull():
                    if draw_x + self._donate_ghost_pixmap.width() > 0 and draw_x < width:
                        painter.drawPixmap(QtCore.QPointF(draw_x, 0.0), self._donate_ghost_pixmap)
                        draws_this_layer += 1
                        total_draws_this_pass += 1

            if getattr(self, '_ghost_debug_logging', False):
                try:
                    import time as _time_mod
                    now = _time_mod.time()
                    last = getattr(self, '_ghost_draw_log_last', 0)
                    if now - last > 1.0:
                        self._ghost_draw_log_last = now
                        print(f"[GHOST DRAW DEBUG] layer_idx={layer_idx}, draws_this_layer={draws_this_layer}")
                except Exception:
                    pass

        if getattr(self, '_ghost_debug_logging', False):
            try:
                import time as _time_mod
                now = _time_mod.time()
                last = getattr(self, '_ghost_draw_summary_last', 0)
                if now - last > 1.0:
                    self._ghost_draw_summary_last = now
                    print(f"[GHOST DRAW SUMMARY] total_draws={total_draws_this_pass}")
                    if total_draws_this_pass > 0 and getattr(self, '_ghost_debug_visual', False):
                        painter.setOpacity(0.9)
                        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
                        painter.fillRect(4, 4, 20, height - 8, QtGui.QColor(255, 0, 255, 180))
            except Exception:
                pass

        painter.restore()
        painter.setOpacity(1.0)


    def apply_glass_glare_effect(self, painter, width, height, settings):
        """
        Apply glass cover with reflections and glare effect.
        Simulates protective glass/plastic cover over LED display.
        OPTIMIZED WITH NUMBA for faster gradient and geometric calculations.
        """
        # Check if glass glare effect is enabled (using cached settings)
        if not settings.get("led_glass_glare", True):
            return
        
        # Create horizontal glare bands (simulating light reflections on glass)
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        
        # Use optimized gradient calculations
        if USE_OPT:
            gradient_stops = opt.calculate_glass_glare_gradient_stops(height, 5)
            corner_params = opt.calculate_corner_highlight_params(width, height)
            
            # Main horizontal glare band (top 1/3 area) with optimized stops
            glare_gradient_1 = QtGui.QLinearGradient(0, 0, 0, height * 0.33)
            for i in range(gradient_stops.shape[0] - 1):  # Skip end marker
                position = gradient_stops[i, 0]
                alpha = int(gradient_stops[i, 1])
                glare_gradient_1.setColorAt(position, QtGui.QColor(255, 255, 255, alpha))
            
            painter.setBrush(QtGui.QBrush(glare_gradient_1))
            painter.setPen(QtCore.Qt.NoPen)
            # Draw horizontal band across top 1/3
            painter.drawRect(0, 0, width, int(height * 0.33))
            
            # Secondary horizontal glare (within top 1/3, slightly angled) - optimized colors
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
            
            # Use optimized corner parameters
            tl_radius, tl_alpha_center, tl_alpha_mid, br_radius, br_alpha_center, br_alpha_mid = corner_params
            
            # Top-left corner with optimized parameters
            corner_gradient = QtGui.QRadialGradient(0, 0, tl_radius)
            corner_gradient.setColorAt(0, QtGui.QColor(255, 255, 255, int(tl_alpha_center)))
            corner_gradient.setColorAt(0.5, QtGui.QColor(255, 255, 255, int(tl_alpha_mid)))
            corner_gradient.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
            painter.setBrush(QtGui.QBrush(corner_gradient))
            painter.drawRect(0, 0, int(width * 0.3), int(height * 0.33))
            
            # Bottom-right corner with optimized parameters
            corner_gradient_2 = QtGui.QRadialGradient(width, height, br_radius)
            corner_gradient_2.setColorAt(0, QtGui.QColor(255, 255, 255, int(br_alpha_center)))
            corner_gradient_2.setColorAt(0.7, QtGui.QColor(255, 255, 255, int(br_alpha_mid)))
            corner_gradient_2.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
            painter.setBrush(QtGui.QBrush(corner_gradient_2))
            painter.drawRect(int(width * 0.7), int(height * 0.6), int(width * 0.3), int(height * 0.4))
            
        else:
            # Fall back to original implementation
            # Main horizontal glare band (top 1/3 area)
            glare_gradient_1 = QtGui.QLinearGradient(0, 0, 0, height * 0.33)
            glare_gradient_1.setColorAt(0, QtGui.QColor(255, 255, 255, 45))
            glare_gradient_1.setColorAt(0.4, QtGui.QColor(255, 255, 255, 20))
            glare_gradient_1.setColorAt(0.7, QtGui.QColor(255, 255, 255, 8))
            glare_gradient_1.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
            
            painter.setBrush(QtGui.QBrush(glare_gradient_1))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(0, 0, width, int(height * 0.33))
            
            # Secondary horizontal glare
            glare_gradient_2 = QtGui.QLinearGradient(0, height * 0.15, width * 0.2, height * 0.33)
            glare_gradient_2.setColorAt(0, QtGui.QColor(200, 220, 255, 25))
            glare_gradient_2.setColorAt(0.4, QtGui.QColor(200, 220, 255, 12))
            glare_gradient_2.setColorAt(0.8, QtGui.QColor(200, 220, 255, 4))
            glare_gradient_2.setColorAt(1, QtGui.QColor(200, 220, 255, 0))
            
            painter.setBrush(QtGui.QBrush(glare_gradient_2))
            glare_polygon_2 = QtGui.QPolygon([
                QtCore.QPoint(0, int(height * 0.15)),
                QtCore.QPoint(width, int(height * 0.18)),
                QtCore.QPoint(width, int(height * 0.33)),
                QtCore.QPoint(0, int(height * 0.30))
            ])
            painter.drawPolygon(glare_polygon_2)
            
            # Corner highlights
            corner_gradient = QtGui.QRadialGradient(0, 0, min(width, height) * 0.35)
            corner_gradient.setColorAt(0, QtGui.QColor(255, 255, 255, 30))
            corner_gradient.setColorAt(0.5, QtGui.QColor(255, 255, 255, 10))
            corner_gradient.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
            painter.setBrush(QtGui.QBrush(corner_gradient))
            painter.drawRect(0, 0, int(width * 0.3), int(height * 0.33))
            
            corner_gradient_2 = QtGui.QRadialGradient(width, height, min(width, height) * 0.2)
            corner_gradient_2.setColorAt(0, QtGui.QColor(255, 255, 255, 10))
            corner_gradient_2.setColorAt(0.7, QtGui.QColor(255, 255, 255, 2))
            corner_gradient_2.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
            painter.setBrush(QtGui.QBrush(corner_gradient_2))
            painter.drawRect(int(width * 0.7), int(height * 0.6), int(width * 0.3), int(height * 0.4))
        
        # Add subtle glass texture (horizontal lines simulating glass surface)
        # More prominent in top 1/3
        glass_texture_color = QtGui.QColor(255, 255, 255, 5)
        for y in range(0, int(height * 0.33), 15):
            painter.fillRect(0, y, width, 1, glass_texture_color)
        # Lighter texture for rest of display
        glass_texture_color_light = QtGui.QColor(255, 255, 255, 2)
        for y in range(int(height * 0.33), height, 25):
            painter.fillRect(0, y, width, 1, glass_texture_color_light)
        
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)

    def paint_ticker(self, widget):
        # Skip rendering during DWM composition events (when other windows minimize/maximize)
        # This prevents the brief stutter when Windows redraws the desktop
        if not self.isVisible() or self.isMinimized():
            return
        
        # FPS counter for diagnostic purposes (time-based to avoid refresh-rate dependent stutters)
        self._fps_counter += 1
        
        # PERF ENHANCEMENT 2: Use cached settings to avoid repeated file I/O
        cached_settings = self.get_cached_settings()
        bloom_enabled = cached_settings.get('show_bloom', True)
        
        # Update click areas when bloom is enabled (needed for bloom positioning)
        update_click_areas = bloom_enabled or self.gl_widget.underMouse()
        
        if update_click_areas:
            self.ticker_click_areas = []
        
        painter = QtGui.QPainter(widget)
        # Disable all expensive render hints for maximum performance
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, False)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, False)
        painter.setRenderHint(QtGui.QPainter.HighQualityAntialiasing, False)
        width = widget.width()
        height = self.ticker_height
        
        # Cache background rendering to eliminate stutter from repeated drawing
        # This prevents repeated fillRect calls for scanlines/grid every frame
        if not hasattr(self, '_cached_background_pixmap') or self._cached_background_pixmap.size() != QtCore.QSize(width, height):
            # Create background pixmap with all static elements
            self._cached_background_pixmap = QtGui.QPixmap(width, height)
            bg_painter = QtGui.QPainter(self._cached_background_pixmap)
            
            # Base dark background (LED board substrate)
            base_color = QtGui.QColor(8, 10, 12)
            bg_painter.fillRect(0, 0, width, height, base_color)
            
            # Add subtle vertical gradient for depth
            depth_grad = QtGui.QLinearGradient(0, 0, 0, height)
            depth_grad.setColorAt(0, QtGui.QColor(15, 18, 22, 180))
            depth_grad.setColorAt(0.5, QtGui.QColor(12, 14, 18, 120))
            depth_grad.setColorAt(1, QtGui.QColor(8, 10, 14, 160))
            bg_painter.fillRect(0, 0, width, height, depth_grad)
            
            # Add horizontal scanlines (LED matrix rows)
            scanline_color = QtGui.QColor(0, 0, 0, 80)
            scanline_highlight = QtGui.QColor(25, 30, 38, 40)
            for y in range(0, height, 4):  # Every 4 pixels
                # Dark scanline
                bg_painter.fillRect(0, y, width, 2, scanline_color)
                # Subtle highlight line
                if y + 2 < height:
                    bg_painter.fillRect(0, y + 2, width, 1, scanline_highlight)
            
            # Add subtle LED pixel grid pattern
            pixel_grid_color = QtGui.QColor(18, 22, 28, 30)
            for x in range(0, width, 6):  # Vertical lines every 6 pixels
                bg_painter.fillRect(x, 0, 1, height, pixel_grid_color)
            
            bg_painter.end()
            print(f"[PERF] Cached background pixmap created ({width}x{height})")
        
        # Draw cached background - single fast blit operation instead of hundreds of fillRect calls
        painter.drawPixmap(0, 0, self._cached_background_pixmap)

        # --- Early ghosting pass: draw ghost layers BETWEEN background and main content ---
        # This ensures tinted ghost pixmaps are visible behind main pixmaps but above the background
        try:
            # Don't draw early ghosts while loading; show only the loading text
            if self.gl_widget and self.gl_widget.effects_enabled and not getattr(self, 'loading', False):
                # Prefer cached effect settings if available (keeps toggle behavior responsive)
                if hasattr(self, '_cached_effect_settings'):
                    early_ghosting = self._cached_effect_settings.get('ghosting', True)
                else:
                    s = get_settings()
                    early_ghosting = s.get('led_ghosting_effect', True)

                if early_ghosting and hasattr(self, 'ticker_pixmaps') and self.ticker_pixmaps:
                    settings_for_effects = self._cached_settings if hasattr(self, '_cached_settings') else get_settings()
                    self.apply_ghosting_effect(painter, width, height, settings_for_effects, behind_main=True)
        except Exception:
            # Be conservative: ignore any issues in this non-critical early effects pass
            pass
        
        if getattr(self, 'loading', False):
            painter.setFont(self.ticker_font)
            text = "TCKR: Loading"
            metrics = QtGui.QFontMetrics(self.ticker_font)
            text_width = metrics.horizontalAdvance(text)
            x = (width - text_width) // 2
            y = (height + metrics.ascent()) // 2
            # Use cached settings for loading text (no need to pass settings since it's only called during startup)
            self.draw_text_with_global_glow(painter, x, y, text, QtGui.QColor("#FFD700"))
            
            # Apply visual effects to loading screen (same as normal ticker)
            if self.gl_widget and self.gl_widget.effects_enabled:
                # Get settings for effects
                cached_settings = self.get_cached_settings()
                
                # Initialize effect settings cache if needed
                if not hasattr(self, '_cached_effect_settings'):
                    settings = get_settings()
                    self._cached_effect_settings = {
                        'bloom': settings.get("led_bloom_effect", True),
                        'ghosting': settings.get("led_ghosting_effect", True),
                        'glass': settings.get("led_glass_glare", True)
                    }
                
                bloom_enabled = self._cached_effect_settings.get('bloom', True)
                glass_enabled = self._cached_effect_settings.get('glass', True)
                
                # Apply effects to loading screen (skip ghosting - it's a motion effect and requires pixmaps)
                if bloom_enabled:
                    # Add a gold bloom effect around the loading text to match the text color
                    text_rect = QtCore.QRect(x - 20, y - metrics.ascent() - 10, text_width + 40, metrics.height() + 20)
                    gold_color = QtGui.QColor(255, 215, 0)  # #FFD700
                    self.apply_bloom_to_rect(painter, text_rect, width, height, cached_settings, bloom_color=gold_color)
                
                if glass_enabled:
                    self.apply_glass_glare_effect(painter, width, height, cached_settings)
            
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

        # Use optimized cycle position calculation for main rendering
        if USE_OPT:
            cycle_positions_array = opt.calculate_cycle_positions(
                self.offset, width, base_cycle_width, donate_cycle_width, 20
            )
            
            # Process optimized positions
            for i in range(cycle_positions_array.shape[0]):
                x = cycle_positions_array[i, 0]
                is_donate = cycle_positions_array[i, 1] == 1
                
                draw_x = x
                # Draw stock tickers first
                for pixmap, w, area_tpls in zip(self.ticker_pixmaps, self.ticker_pixmap_widths, self.ticker_area_templates):
                    # Use sub-pixel rendering with QPointF for smoother scrolling
                    # QPainter supports fractional coordinates for anti-aliased positioning
                    painter.drawPixmap(QtCore.QPointF(draw_x, 0.0), pixmap)
                    if update_click_areas:
                        for area_type, tkr, rect in area_tpls:
                            offset_rect = QtCore.QRect(rect)
                            offset_rect.translate(int(draw_x), 0)
                            self.ticker_click_areas.append((area_type, tkr, offset_rect))
                    draw_x += w
                # Then draw donate message at the end (if this cycle includes it)
                if is_donate:
                    # Use sub-pixel rendering for donate pixmap too
                    painter.drawPixmap(QtCore.QPointF(draw_x, 0.0), self._donate_pixmap)
                    if update_click_areas:
                        for area_type, tkr, rect in self._donate_area_template:
                            offset_rect = QtCore.QRect(rect)
                            offset_rect.translate(int(draw_x), 0)
                            self.ticker_click_areas.append((area_type, tkr, offset_rect))
                    draw_x += self._donate_pixmap_width
        else:
            # Fall back to original cycle position calculation
            for x, is_donate in cycle_positions:
                draw_x = x
                # Draw stock tickers first
                for pixmap, w, area_tpls in zip(self.ticker_pixmaps, self.ticker_pixmap_widths, self.ticker_area_templates):
                    # Use sub-pixel rendering with QPointF for smoother scrolling
                    painter.drawPixmap(QtCore.QPointF(draw_x, 0.0), pixmap)
                    if update_click_areas:
                        for area_type, tkr, rect in area_tpls:
                            offset_rect = QtCore.QRect(rect)
                            offset_rect.translate(int(draw_x), 0)
                            self.ticker_click_areas.append((area_type, tkr, offset_rect))
                    draw_x += w
                # Then draw donate message at the end (if this cycle includes it)
                if is_donate:
                    # Use sub-pixel rendering for donate pixmap
                    painter.drawPixmap(QtCore.QPointF(draw_x, 0.0), self._donate_pixmap)
                    if update_click_areas:
                        for area_type, tkr, rect in self._donate_area_template:
                            offset_rect = QtCore.QRect(rect)
                            offset_rect.translate(int(draw_x), 0)
                            self.ticker_click_areas.append((area_type, tkr, offset_rect))
                    draw_x += self._donate_pixmap_width

        supercycle_width = donate_cycle_width + 2 * base_cycle_width

        # Calculate frame time delta for smooth frame-independent animation
        current_time = self._time_module.perf_counter()
        delta_time = current_time - self.last_frame_time
        self.last_frame_time = current_time
        
        # Cap delta_time to prevent huge jumps on first frame or after long pauses
        # Maximum 50ms (20 FPS equivalent) to avoid text "rushing" onto screen
        delta_time = min(delta_time, 0.050)
        
        # Frame time debug logging disabled - printing causes micro-stutters
        
        # FPS counter - calculate once per second (time-based, not frame-based)
        # Simplified to avoid any periodic operations that could cause stuttering
        if current_time - self._fps_last_calc >= 1.0:
            if self._fps_last_calc > 0:
                elapsed = current_time - self._fps_last_calc
                fps = self._fps_counter / elapsed
                
                # Store FPS values for overlay display
                self._current_fps = fps
                self._current_frame_time = (elapsed / self._fps_counter) * 1000
                
                # Only print to console if overlay is disabled
                if not self.show_fps_overlay:
                    print(f"[FPS] Current: {fps:.1f} FPS | Frame time: {self._current_frame_time:.1f}ms avg")
            
            # Reset counter and timer for next measurement period
            self._fps_last_calc = current_time
            self._fps_counter = 0
        
        # Only scroll if not paused (mouse not hovering)
        if not self.is_paused:
            # Time-based scrolling: pixels per second, not per frame
            # This keeps speed consistent regardless of frame rate
            actual_scroll = self.scroll_speed * delta_time * 60.0  # Multiply by 60 to maintain same numeric scale
            # Remember last_actual_scroll so ghost offsets can be computed relative to frame movement
            self._last_actual_scroll = actual_scroll

            # Only update scroll position if not paused
            if not self.paused:
                # Use optimized scroll position update with sub-pixel precision
                if USE_OPT:
                    # Update: keep offset as float for smooth sub-pixel scrolling
                    self.offset -= actual_scroll
                    if self.offset <= -supercycle_width:
                        self.offset += supercycle_width
                else:
                    # Original scroll update logic (also updated for sub-pixel)
                    self.offset -= actual_scroll
                    if self.offset <= -supercycle_width:
                        self.offset += supercycle_width
        
        # Apply visual effects if enabled (user can toggle with Effects button)
        # Check if any effects are actually enabled to avoid unnecessary function calls and settings lookups
        if self.gl_widget and self.gl_widget.effects_enabled:
            # Cache settings to avoid reading JSON file every frame (CRITICAL for performance)
            if not hasattr(self, '_cached_effect_settings') or not hasattr(self, '_settings_cache_time'):
                self._settings_cache_time = 0
                # Initialize cache immediately with defaults on first run
                settings = get_settings()
                self._cached_effect_settings = {
                    'bloom': settings.get("led_bloom_effect", True),
                    'ghosting': settings.get("led_ghosting_effect", True),
                    'glass': settings.get("led_glass_glare", True)
                }
                self._cached_settings = settings  # Also initialize _cached_settings immediately
                print(f"[EFFECTS INIT] Cache initialized - bloom={self._cached_effect_settings['bloom']}, "
                      f"ghosting={self._cached_effect_settings['ghosting']}, glass={self._cached_effect_settings['glass']}")
            
            # REMOVED: Periodic settings refresh - causes 5-second glitch
            # Settings are now only loaded on startup and when explicitly changed via settings dialog
            # This eliminates periodic frame drops every 5 seconds
            
            # Use cached settings
            cached_settings = self._cached_settings if hasattr(self, '_cached_settings') else get_settings()
            bloom_enabled = self._cached_effect_settings.get('bloom', True)
            # Respect user's ghosting preference even when paused so effects remain visible while paused
            ghosting_enabled = self._cached_effect_settings.get('ghosting', True)
            # Glass glare preference
            glass_enabled = self._cached_effect_settings.get('glass', True)
            if not hasattr(self, '_effects_debug_logged'):
                self._effects_debug_logged = True
                print(f"[EFFECTS] Applying effects - bloom={bloom_enabled}, ghosting={ghosting_enabled}, glass={glass_enabled}")
            
            # Only call effect functions if their individual settings are enabled
            if bloom_enabled:
                # Apply bloom/glow effect (light bleeding from bright LEDs)
                self.apply_bloom_effect(painter, width, height, cached_settings)
            
            if ghosting_enabled:
                # Ghosting is applied earlier (between background and main content)
                # No further ghost draw here to avoid double-drawing and layering issues
                pass
            
            if glass_enabled:
                # Apply glass cover with reflections/glare (final layer on top of everything)
                self.apply_glass_glare_effect(painter, width, height, cached_settings)
        else:
            # Debug why effects are disabled
            if not hasattr(self, '_effects_disabled_logged'):
                self._effects_disabled_logged = True
                has_gl = self.gl_widget is not None
                enabled = self.gl_widget.effects_enabled if has_gl else False
                print(f"[EFFECTS] NOT applying - gl_widget exists={has_gl}, effects_enabled={enabled}")
        
        # Draw FPS overlay if enabled
        if self.show_fps_overlay and hasattr(self, '_current_fps'):
            # Draw semi-transparent background for readability
            overlay_height = 35
            overlay_width = 110  # Reduced from 200 to fit content better
            overlay_x = width - overlay_width - 1  # Aligned to right edge with 2px left margin
            overlay_y = 0  # Aligned to top edge (no margin)
            
            # Dark background with transparency
            bg_color = QtGui.QColor(0, 0, 0, 180)
            painter.fillRect(overlay_x, overlay_y, overlay_width, overlay_height, bg_color)
            
            # Border for visual separation
            border_color = QtGui.QColor(60, 60, 60, 200)
            painter.setPen(QtGui.QPen(border_color, 1))
            painter.drawRect(overlay_x, overlay_y, overlay_width, overlay_height)
            
            # FPS text with color coding
            fps_value = self._current_fps
            if fps_value >= 59:
                fps_color = QtGui.QColor(0, 255, 64)  # Green for good FPS
            elif fps_value >= 30:
                fps_color = QtGui.QColor(255, 215, 0)  # Yellow/gold for medium FPS
            else:
                fps_color = QtGui.QColor(255, 85, 85)  # Red for low FPS
            
            # Create smaller font for overlay
            overlay_font = QtGui.QFont("Consolas", 9)
            overlay_font.setBold(True)
            painter.setFont(overlay_font)
            painter.setPen(fps_color)
            
            # Draw FPS value
            fps_text = f"FPS: {fps_value:.1f}"
            painter.drawText(overlay_x + 10, overlay_y + 15, fps_text)
            
            # Draw frame time in smaller, dimmer text
            frame_time_text = f"Frame: {self._current_frame_time:.2f}ms"
            painter.setPen(QtGui.QColor(160, 160, 160))
            overlay_font.setPointSize(7)
            painter.setFont(overlay_font)
            painter.drawText(overlay_x + 10, overlay_y + 28, frame_time_text)
        
        # Draw update countdown overlay if enabled (on far left)
        if self.show_update_countdown and hasattr(self, 'last_api_update_time'):
            # Calculate time until next update
            import time as time_module
            current_time = time_module.time()
            time_since_update = current_time - self.last_api_update_time
            # Use the primary ticker's timer interval for all tickers (they share the same schedule)
            if hasattr(self, 'tray_icon') and self.tray_icon and self.tray_icon.primary_ticker:
                primary_interval = self.tray_icon.primary_ticker.update_timer.interval()
            else:
                primary_interval = self.update_timer.interval()
            update_interval_seconds = primary_interval / 1000  # Convert ms to seconds
            time_until_next = max(0, update_interval_seconds - time_since_update)
            
            # Check if we're in backoff mode
            if hasattr(TickerWindow, 'backoff_until') and current_time < TickerWindow.backoff_until:
                time_until_next = TickerWindow.backoff_until - current_time
                countdown_color = QtGui.QColor(255, 165, 0)  # Orange for backoff
            else:
                countdown_color = QtGui.QColor(0, 179, 255)  # Cyan for normal updates
            
            # Draw semi-transparent background for readability (compact size)
            overlay_height = 35
            overlay_width = 110
            overlay_x = 0  # Far left edge
            overlay_y = 0  # Top edge
            
            # Dark background with transparency
            bg_color = QtGui.QColor(0, 0, 0, 180)
            painter.fillRect(overlay_x, overlay_y, overlay_width, overlay_height, bg_color)
            
            # Border for visual separation
            border_color = QtGui.QColor(60, 60, 60, 200)
            painter.setPen(QtGui.QPen(border_color, 1))
            painter.drawRect(overlay_x, overlay_y, overlay_width, overlay_height)
            
            # Create smaller font for overlay
            overlay_font = QtGui.QFont("Consolas", 9)
            overlay_font.setBold(True)
            painter.setFont(overlay_font)
            painter.setPen(countdown_color)
            
            # Format time as MM:SS and draw
            minutes = int(time_until_next // 60)
            seconds = int(time_until_next % 60)
            countdown_text = f"Next: {minutes:02d}:{seconds:02d}"
            painter.drawText(overlay_x + 10, overlay_y + 15, countdown_text)
            
            # Draw interval info in smaller, dimmer text
            if update_interval_seconds < 60:
                interval_text = f"Every {int(update_interval_seconds)}sec"
            else:
                interval_minutes = int(update_interval_seconds // 60)
                interval_text = f"Every {interval_minutes}min"
            painter.setPen(QtGui.QColor(160, 160, 160))
            overlay_font.setPointSize(7)
            painter.setFont(overlay_font)
            painter.drawText(overlay_x + 10, overlay_y + 28, interval_text)
        
        painter.end()
    def ticker_mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            pos = event.pos()
            for area_type, tkr, rect in self.ticker_click_areas:
                if rect.contains(pos):
                    if area_type == 'donate':
                        webbrowser.open("https://paypal.me/paypaulc")
                    elif area_type in ('market', 'market_label', 'market_status'):
                        webbrowser.open("https://www.tradinghours.com/markets/nyse")
                    else:
                        # Strip special characters like ^ from ticker symbol for URL
                        clean_ticker = tkr.lstrip('^')
                        # Special case for S&P 500 index
                        if clean_ticker == 'GSPC':
                            url = "https://www.tradingview.com/symbols/SPX/"
                        else:
                            url = f"https://www.tradingview.com/symbols/{clean_ticker}/"
                        webbrowser.open(url)
                    break
    def contextMenuEvent(self, event):
        tray = getattr(self, 'tray_icon', None)
        if tray:
            tray.contextMenu().exec_(event.globalPos())
    def closeEvent(self, event):
        # Stop render thread
        if hasattr(self, '_render_thread_active'):
            self._render_thread_active = False
            if hasattr(self, '_render_thread_obj'):
                try:
                    self._render_thread_obj.join(timeout=1.0)
                except:
                    pass
        
        # Stop continuous rendering
        if hasattr(self, 'gl_widget') and hasattr(self.gl_widget, 'continuous_rendering'):
            self.gl_widget.continuous_rendering = False
        
        # Stop all timers immediately to prevent further processing
        if hasattr(self, 'render_timer') and self.render_timer.isActive():
            self.render_timer.stop()
        if hasattr(self, 'update_timer') and self.update_timer.isActive():
            self.update_timer.stop()
        if hasattr(self, 'market_status_timer') and self.market_status_timer.isActive():
            self.market_status_timer.stop()
        if hasattr(self, 'position_check_timer') and self.position_check_timer.isActive():
            self.position_check_timer.stop()
        
        # Clear any pending API fetch tasks in the thread pool
        QtCore.QThreadPool.globalInstance().clear()
        
        # Restore Windows timer resolution
        if sys.platform == "win32" and hasattr(self, '_timer_period_set') and self._timer_period_set:
            try:
                import ctypes
                winmm = ctypes.windll.winmm
                resolution = ctypes.c_uint(1)
                winmm.timeEndPeriod(resolution)
                print(f"[PERF] Windows timer resolution restored")
            except Exception as e:
                print(f"[PERF] Could not restore timer resolution: {e}")
        
        # Remove appbar quickly
        if sys.platform == "win32":
            remove_appbar(int(self.winId()))

        # Keep tray window registry synchronized
        try:
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.remove_ticker_window(self)
        except Exception:
            pass
        
        super().closeEvent(event)
    def enterEvent(self, event):
        # Pause scrolling when mouse enters
        self.is_paused = True
        event.accept()
        
    def leaveEvent(self, event):
        # Resume scrolling when mouse leaves
        self.is_paused = False
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
            # DISABLED: This was causing stuttering every time other windows minimize/maximize
            # The constant position reaffirmation was interrupting smooth scrolling
            # We already have WS_EX_TOPMOST and AppBar registration, so we don't need this
            # print(f"[APPBAR EVENT] Received notification: {notification}")
            
            # ABN_POSCHANGED (1) - Another appbar changed position/size
            if notification == ABN_POSCHANGED:
                # CRITICAL FIX: Ignore ABN_POSCHANGED to prevent stuttering
                # When other windows minimize/maximize, Windows sends this event
                # Responding to it causes position reaffirmation which stutters the scroll
                # Our window stays in place thanks to AppBar + WS_EX_TOPMOST
                # print(f"[APPBAR EVENT] ABN_POSCHANGED ignored - prevents scroll stuttering")
                return True, 0  # Acknowledge but don't process
                
                # OLD CODE (causes stuttering):
                # print(f"[APPBAR EVENT] ABN_POSCHANGED - Another appbar changed, reaffirming our position")
                # 
                # # Prevent infinite loop - ignore notifications that occur shortly after we set the work area
                # # This prevents our own work area changes from triggering a feedback loop
                # import time as time_module
                # current_time = time_module.time()
                # time_since_last_set = current_time - self._last_work_area_set_time
                # 
                # if time_since_last_set < 2.0:  # Ignore notifications within 2 seconds of our work area change
                #     print(f"[APPBAR EVENT] Ignoring ABN_POSCHANGED ({time_since_last_set:.2f}s after work area change)")
                #     return True, 0
                # 
                # # Reaffirm our position when other appbars change (e.g., when an app docks)
                # screen_index = get_settings().get("screen_index", 0)
                # app = QtWidgets.QApplication.instance()
                # screens = app.screens()
                # if 0 <= screen_index < len(screens):
                #     screen = screens[screen_index]
                # else:
                #     screen = app.primaryScreen()
                # rect = screen.geometry()
                
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
        self.setWindowTitle("📊 Manage Stocks")
        self.stocks = load_stocks()
        self.sort_and_refresh()
        
        # Apply modern theme
        apply_modern_theme(self)
        self.setMinimumWidth(450)
        self.setMinimumHeight(400)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title label
        title = QtWidgets.QLabel("Manage Your Stock Tickers")
        title.setStyleSheet("font-size: 14px; font-weight: 600; color: #00b3ff; margin-bottom: 8px;")
        layout.addWidget(title)
        
        # Stock list
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: #1a1d23;
                border: 1px solid #3a3f4a;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
                color: #ffffff;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
                margin: 2px 0;
            }
            QListWidget::item:hover {
                background: #2a2f38;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00b3ff, stop:1 #0088cc);
                color: #ffffff;
            }
        """)
        layout.addWidget(self.list_widget)
        self.refresh_list_widget()
        
        # Add stock input (compact inline)
        add_layout = QtWidgets.QHBoxLayout()
        add_layout.setSpacing(8)
        self.ticker_entry = QtWidgets.QLineEdit()
        self.ticker_entry.setPlaceholderText("Enter ticker symbol (e.g. AAPL)")
        add_btn = QtWidgets.QPushButton("➕ Add")
        make_success_button(add_btn)
        add_btn.clicked.connect(self.add_stock)
        add_layout.addWidget(self.ticker_entry, 1)
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)
        
        # Remove button
        remove_btn = QtWidgets.QPushButton("🗑️ Remove Selected")
        make_danger_button(remove_btn)
        remove_btn.clicked.connect(self.remove_selected)
        layout.addWidget(remove_btn)
        
        # Load/Save buttons (inline)
        file_layout = QtWidgets.QHBoxLayout()
        file_layout.setSpacing(8)
        
        load_btn = QtWidgets.QPushButton("📂 Load from File...")
        load_btn.setStyleSheet("""
            QPushButton {
                background: #2a2d35;
                border: 1px solid #3a3d45;
                border-radius: 6px;
                color: #ffffff;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #3a3d45;
                border: 1px solid #00b3ff;
            }
        """)
        load_btn.clicked.connect(self.load_from_file)
        
        save_file_btn = QtWidgets.QPushButton("💾 Save to File...")
        save_file_btn.setStyleSheet("""
            QPushButton {
                background: #2a2d35;
                border: 1px solid #3a3d45;
                border-radius: 6px;
                color: #ffffff;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #3a3d45;
                border: 1px solid #00b3ff;
            }
        """)
        save_file_btn.clicked.connect(self.save_to_file)
        
        file_layout.addWidget(load_btn)
        file_layout.addWidget(save_file_btn)
        layout.addLayout(file_layout)
        
        # Separator
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setStyleSheet("background: #3a3f4a; margin: 8px 0;")
        layout.addWidget(separator)
        
        # Major indices section
        indices_label = QtWidgets.QLabel("📈 Major Market Indices (via Yahoo Finance)")
        indices_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #00b3ff; margin-bottom: 4px;")
        layout.addWidget(indices_label)
        
        indices_layout = QtWidgets.QVBoxLayout()
        indices_layout.setSpacing(6)
        
        self.dji_checkbox = QtWidgets.QCheckBox("Dow Jones Industrial Average (^DJI)")
        self.sp500_checkbox = QtWidgets.QCheckBox("S&P 500 (^GSPC)")
        self.nasdaq_checkbox = QtWidgets.QCheckBox("NASDAQ Composite (^IXIC)")
        
        for checkbox in [self.sp500_checkbox, self.nasdaq_checkbox, self.dji_checkbox]:
            checkbox.setStyleSheet("""
                QCheckBox {
                    color: #ffffff;
                    font-size: 11px;
                    spacing: 8px;
                }
                QCheckBox::indicator {
                    width: 16px;
                    height: 16px;
                    border: 2px solid #3a3f4a;
                    border-radius: 3px;
                    background: #1a1d23;
                }
                QCheckBox::indicator:hover {
                    border-color: #00b3ff;
                }
                QCheckBox::indicator:checked {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #00b3ff, stop:1 #0088cc);
                    border-color: #00b3ff;
                }
            """)
            indices_layout.addWidget(checkbox)
        
        layout.addLayout(indices_layout)
        
        # Check which indices are already in the stocks list
        stock_symbols = [s[0] for s in self.stocks]
        self.sp500_checkbox.setChecked('^GSPC' in stock_symbols)
        self.nasdaq_checkbox.setChecked('^IXIC' in stock_symbols)
        self.dji_checkbox.setChecked('^DJI' in stock_symbols)
        
        # Dialog buttons
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.save_and_close)
        btns.rejected.connect(self.reject)
        
        # Style OK/Save button
        ok_button = btns.button(QtWidgets.QDialogButtonBox.Ok)
        ok_button.setText("💾 Save")
        make_accent_button(ok_button)
        
        layout.addWidget(btns)

    def sort_and_refresh(self):
        # Sort with special characters (like ^) first, then alphanumeric
        # Custom key: non-alphanumeric first (using space), then the symbol
        self.stocks.sort(key=lambda s: ('~' if s[0][0].isalnum() else ' ') + s[0].upper())

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
            self.check_websocket_cost_warning()

    def check_websocket_cost_warning(self):
        """Warn users about potential websocket costs when exceeding free tier limits"""
        if not WEBSOCKET_AVAILABLE:
            return

        num_stocks = len(self.stocks)
        finnhub_stocks = len([s for s in self.stocks if not s[0].startswith('^')])

        # Free tier limits: 50 websocket symbols, 60 API calls/minute
        if finnhub_stocks > 50:
            warning_msg = (
                f"⚠️ Cost Warning: You have {finnhub_stocks} stocks (Finnhub limit: 50 free).\n\n"
                "With websockets enabled, you may incur charges:\n"
                "• $0.01/minute connection time during market hours\n"
                "• $0.02 per 1,000 trade messages\n\n"
                "Consider upgrading to Finnhub paid plan or reduce stocks to stay in free tier."
            )
            QtWidgets.QMessageBox.warning(
                self,
                "Finnhub Cost Warning",
                warning_msg
            )
        elif finnhub_stocks > 40:  # Warning before hitting limit
            colored_print(f"[WEBSOCKET] Note: You have {finnhub_stocks} stocks. Free tier supports 50 symbols.")

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            idx = self.list_widget.row(item)
            self.list_widget.takeItem(idx)
            del self.stocks[idx]
        self.sort_and_refresh()
        self.refresh_list_widget()

    def load_from_file(self):
        """Load stocks list from a JSON file"""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load Stocks from File",
            APPDATA_DIR,
            "JSON Files (*.json);;All Files (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    loaded_stocks = json.load(f)
                
                # Validate the loaded data
                if isinstance(loaded_stocks, list):
                    self.stocks = loaded_stocks
                    self.sort_and_refresh()
                    self.refresh_list_widget()
                    
                    # Update checkboxes for major indices
                    stock_symbols = [s[0] for s in self.stocks]
                    self.sp500_checkbox.setChecked('^GSPC' in stock_symbols)
                    self.nasdaq_checkbox.setChecked('^IXIC' in stock_symbols)
                    self.dji_checkbox.setChecked('^DJI' in stock_symbols)
                    
                    QtWidgets.QMessageBox.information(
                        self,
                        "Success",
                        f"Successfully loaded {len(self.stocks)} stocks from:\n{file_path}"
                    )
                    self.check_websocket_cost_warning()
                else:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Invalid Format",
                        "The selected file does not contain a valid stocks list."
                    )
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Error Loading File",
                    f"Failed to load stocks from file:\n{str(e)}"
                )

    def save_to_file(self):
        """Save current stocks list to a JSON file"""
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Stocks to File",
            os.path.join(APPDATA_DIR, "TCKR.Tickers.json"),
            "JSON Files (*.json);;All Files (*.*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.stocks, f, indent=2)
                
                QtWidgets.QMessageBox.information(
                    self,
                    "Success",
                    f"Successfully saved {len(self.stocks)} stocks to:\n{file_path}"
                )
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Error Saving File",
                    f"Failed to save stocks to file:\n{str(e)}"
                )

    def save_and_close(self):
        # Handle major indices checkboxes
        indices_map = {
            '^GSPC': self.sp500_checkbox.isChecked(),
            '^IXIC': self.nasdaq_checkbox.isChecked(),
            '^DJI': self.dji_checkbox.isChecked()
        }
        
        # Remove unchecked indices
        self.stocks = [s for s in self.stocks if s[0] not in indices_map or indices_map[s[0]]]
        
        # Add checked indices that aren't already in the list
        stock_symbols = [s[0] for s in self.stocks]
        for symbol, checked in indices_map.items():
            if checked and symbol not in stock_symbols:
                self.stocks.append([symbol, f"{symbol}.png"])
        
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
    parser.add_argument("-n", "--no-splash", dest="no_splash", action="store_true", help="Disable splash screen on startup")
    
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
    
    # Create QApplication IMMEDIATELY to show splash screen
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    # Use Desktop OpenGL for better performance (don't set both OpenGLES and DesktopOpenGL!)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseDesktopOpenGL)

    app = QtWidgets.QApplication(sys.argv)
    icon_path = resource_path("TCKR.ico")
    app.setWindowIcon(QtGui.QIcon(icon_path))
    app.setQuitOnLastWindowClosed(False)
    
    # Parse arguments early so command-line options can affect startup
    args = parse_args()
    apply_command_line_settings(args)

    # Show splash screen IMMEDIATELY before any other initialization (unless disabled)
    splash = None
    if not getattr(args, 'no_splash', False):
        splash = SplashScreen()
        splash.show()
        app.processEvents()  # Force splash to display immediately
        # Quick visibility probe and fallback: some systems fail to show translucent tool windows.
        visible = bool(splash.isVisible())
        colored_print(f"[SPLASH] Shown: visible={visible}, geom={splash.geometry()}")
        try:
            splash.raise_()
            splash.activateWindow()
            app.processEvents()
        except Exception:
            pass
        if not splash.isVisible():
            colored_print("[SPLASH] Warning: splash not visible after initial show(), trying opaque fallback")
            try:
                splash.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
                splash.show()
                app.processEvents()
                colored_print(f"[SPLASH] Fallback shown: visible={splash.isVisible()}, geom={splash.geometry()}")
            except Exception as e:
                colored_print(f"[SPLASH] Fallback failed: {e}")
    
    # Now do all the slow initialization while splash is visible
    # Load heavy performance modules (Numba JIT takes 3+ seconds)
    load_performance_modules()
    
    # (args already parsed above)
    
    # Tune Python garbage collector to prevent periodic stutters
    # Disable automatic GC and run it manually during idle periods
    import gc
    gc.disable()  # Disable automatic collection
    gc.set_threshold(5000, 10, 10)  # Much higher thresholds for gen0, gen1, gen2
    colored_print(f"[PERF] Python GC tuned for smooth rendering (disabled automatic collection)")
    
    splash_start_time = time.time()
    
    # Store ticker_window reference for emergency cleanup
    ticker_window = None
    
    def finish_initialization():
        """Complete initialization after splash screen timer"""
        nonlocal ticker_window
        
        # Cleanup any orphaned appbar registrations from previous instances
        cleanup_orphaned_appbars()
        
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
        
        # Set global reference for emergency cleanup
        global _global_tray
        _global_tray = tray
        
        tray.show()

        # Check if second ticker is enabled
        settings = get_settings()
        if settings.get("enable_second_ticker", False):
            colored_print("[SECOND TICKER] Creating second ticker window below the main one")
            try:
                # Create second ticker window
                second_ticker_window = TickerWindow()
                second_ticker_window.is_second_ticker = True  # Mark as second ticker

                # Stop the timer that was started in __init__ - we'll restart it after setup
                if hasattr(second_ticker_window, 'update_timer') and second_ticker_window.update_timer.isActive():
                    second_ticker_window.update_timer.stop()

                # Apply second ticker specific settings
                second_ticker_window.scroll_speed = float(max(1, settings.get("second_ticker_speed", 2)))

                # Load stocks from second ticker stock file if specified, otherwise use same as main
                stock_file = settings.get("second_ticker_stock_file", "").strip()
                if stock_file and os.path.exists(stock_file):
                    try:
                        with open(stock_file, "r") as f:
                            second_stocks = json.load(f)
                        second_ticker_window.stocks = [s[0] for s in second_stocks]
                        colored_print(f"[SECOND TICKER] Loaded {len(second_ticker_window.stocks)} stocks from custom file")
                    except Exception as e:
                        colored_print(f"[SECOND TICKER] Failed to load custom stock file: {e}, using main stocks")
                        second_ticker_window.stocks = ticker_window.stocks.copy()
                else:
                    second_ticker_window.stocks = ticker_window.stocks.copy()
                    colored_print(f"[SECOND TICKER] Using same stocks as main ticker ({len(second_ticker_window.stocks)} stocks)")

                # Build ticker display
                second_ticker_window.build_ticker_pixmaps()
                second_ticker_window.build_ticker_text(reset_scroll=True)

                # Apply main ticker settings (except speed which is customized)
                second_ticker_window.set_transparency(settings.get("transparency", 100))
                second_ticker_window.ticker_height = settings.get("ticker_height", 60)
                second_ticker_window.setFixedHeight(second_ticker_window.ticker_height)
                second_ticker_window.update_font_and_label()

                # Connect to websocket if available (same as main ticker)
                if hasattr(ticker_window, 'websocket_client') and ticker_window.websocket_client:
                    second_ticker_window.websocket_client = ticker_window.websocket_client
                    # Primary ticker will subscribe to all symbols from all tickers

                # Register with tray icon (no timer for secondary tickers - they get updates from primary)
                tray.add_ticker_window(second_ticker_window)

                colored_print("[SECOND TICKER] Second ticker created successfully")

            except Exception as e:
                colored_print(f"[SECOND TICKER] Failed to create second ticker: {e}")

        # Final positioning check for all tickers
        QtCore.QTimer.singleShot(500, lambda: [ticker.ensure_top_position() for ticker in tray.ticker_windows])

        # Add application exit handler for additional safety (after tray is created)
        def emergency_cleanup():
            """Emergency cleanup function called when application is about to exit"""
            global _cleanup_in_progress, _global_tray

            # Prevent recursive cleanup
            if _cleanup_in_progress:
                return
            _cleanup_in_progress = True

            print("[EXIT] Emergency cleanup - ensuring AppBar is removed")
            # Clean up appbar for all ticker windows
            if _global_tray and hasattr(_global_tray, 'ticker_windows'):
                for ticker in _global_tray.ticker_windows:
                    if sys.platform == "win32" and ticker and hasattr(ticker, 'winId'):
                        try:
                            remove_appbar(int(ticker.winId()))
                        except Exception as e:
                            print(f"[EXIT] Emergency cleanup failed for ticker: {e}")
        
        app.aboutToQuit.connect(emergency_cleanup)

        # Close splash screen (if shown) and show ticker
        if splash is not None:
            splash.close()
    
    # Show splash screen for exactly 3 seconds, then initialize ticker
    QtCore.QTimer.singleShot(3000, finish_initialization)
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
