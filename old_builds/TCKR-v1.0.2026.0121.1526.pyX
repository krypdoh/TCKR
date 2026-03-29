"""
Author: Paul R. Charovkine
Program: TCKR.py
Date: 2026.01.21
Version: 1.0.2026.0121.1526
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
from urllib.parse import quote as url_quote
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtMultimedia import QSoundEffect
import webbrowser
import ctypes
import subprocess
from ctypes import wintypes
import concurrent.futures
import threading
import argparse
import shutil
import signal
from modern_gui_styles import *  # Modern dark theme styling


def _is_pid_running(pid):
    """Return True if PID is running on Windows, False otherwise."""
    try:
        if sys.platform != 'win32':
            try:
                os.kill(pid, 0)
                return True
            except Exception:
                return False
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        try:
            exit_code = wintypes.DWORD()
            res = kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
            if not res:
                return False
            # STILL_ACTIVE == 259
            return int(exit_code.value) == 259
        finally:
            try:
                kernel32.CloseHandle(h)
            except Exception:
                pass
    except Exception:
        return False


def _wait_for_pid_exit(pid, timeout=30.0):
    """Wait until `pid` is no longer running or timeout (seconds) expires. Returns True if exited."""
    try:
        start = time.time()
        while time.time() - start < float(timeout):
            if not _is_pid_running(pid):
                return True
            time.sleep(0.05)
        return not _is_pid_running(pid)
    except Exception:
        return False


def _terminate_window_process(hwnd):
    """Obtain the PID for `hwnd` and attempt to terminate its process. Returns True if terminated."""
    try:
        if sys.platform != 'win32':
            return False
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        if not pid.value:
            return False
        # Always log mapping from HWND to PID for diagnostics
        try:
            colored_print(f"[APPBAR] Found PID={pid.value} for HWND={hwnd} - verifying executable before termination")
        except Exception:
            pass
        # Be conservative: only terminate if the process executable matches this Python interpreter
        try:
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            hproc_q = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid.value))
            exe_path = None
            if hproc_q:
                try:
                    # QueryFullProcessImageNameW
                    buf_size = wintypes.DWORD(260)
                    buf = ctypes.create_unicode_buffer(260)
                    if kernel32.QueryFullProcessImageNameW(hproc_q, 0, buf, ctypes.byref(buf_size)):
                        exe_path = buf.value
                except Exception:
                    exe_path = None
                finally:
                    try:
                        kernel32.CloseHandle(hproc_q)
                    except Exception:
                        pass

            if exe_path:
                try:
                    # Be conservative: require the remote process executable to match
                    # the current process more strictly. Previously we allowed any
                    # executable containing 'python' which could match unrelated
                    # Python processes and result in unsafe terminations.
                    myexe_basename = os.path.basename(sys.executable).lower()
                    remoteexe_basename = os.path.basename(exe_path).lower()
                    myexe_abs = os.path.abspath(sys.executable).lower()
                    remoteexe_abs = os.path.abspath(exe_path).lower()

                    # Accept only when the absolute executable path matches exactly
                    # or when the basenames are identical (covers frozen exe names).
                    if remoteexe_abs != myexe_abs and remoteexe_basename != myexe_basename:
                        try:
                            colored_print(f"[APPBAR] Refusing to terminate PID={pid.value} - exe mismatch ({remoteexe_basename})")
                        except Exception:
                            pass
                        return False
                except Exception:
                    pass

        except Exception:
            pass

        PROCESS_TERMINATE = 0x0001
        PROCESS_QUERY_INFORMATION = 0x0400
        # Try opening with terminate rights; include query info to improve success chance
        hproc = kernel32.OpenProcess(PROCESS_TERMINATE | PROCESS_QUERY_INFORMATION, False, int(pid.value))
        if not hproc:
            err = kernel32.GetLastError()
            try:
                colored_print(f"[APPBAR] OpenProcess failed for PID={pid.value} (GetLastError={err})")
            except Exception:
                pass
            return False
        try:
            res = kernel32.TerminateProcess(hproc, 1)
            if not res:
                err = kernel32.GetLastError()
                try:
                    colored_print(f"[APPBAR] TerminateProcess failed for PID={pid.value} (GetLastError={err})")
                except Exception:
                    pass
                return False
            try:
                colored_print(f"[APPBAR] Successfully terminated PID={pid.value}")
            except Exception:
                pass
            return True
        finally:
            try:
                kernel32.CloseHandle(hproc)
            except Exception:
                pass
    except Exception:
        return False

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
# Enable AppBar debug to capture detailed set/remove/keeper diagnostics during reproducer
DEBUG_APPBAR = True  # AppBar registration/removal debug messages (temporarily enabled)
DEBUG_POSITIONING = False  # Window positioning debug messages
# Temporary debug override to allow forced termination during repro (use only for debugging)
# Set to True to allow TerminateProcess attempts even if user setting is False
DEBUG_ALLOW_FORCED_TERMINATION = False  # Disabled by default (enable only for explicit debugging)

# AppBar coordination primitives (serialize remove/register and record last reservation)
import threading as _threading
_appbar_lock = _threading.Lock()
_last_reserved_height = 0
_last_reserved_by = None
_last_reserved_by_hwnd = None
_last_reserved_ts = 0.0
# Per-screen AppBar support cache: { screen_key: bool }
_appbar_supported = {}  # Set to False when a screen consistently returns reserved==0 (no AppBar support)
_reservation_keeper = None  # Holds ReservationKeeper instance that keeps combined AppBar reservation
# Guard to indicate a ReservationKeeper creation is currently in-flight
_keeper_creation_in_progress = False
# Guard to indicate a ReservationKeeper removal is currently in-progress
_keeper_removal_in_progress = False
# Track created ticker HWNDs so we can forcibly close them by handle during teardown
_created_ticker_hwnds = set()
# Guard to prevent duplicate restarts/handoffs from spawning multiple children
_restart_in_progress = False
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
    global _appbar_lock, _last_reserved_height, _last_reserved_by, _last_reserved_by_hwnd, _last_reserved_ts

    # Instrumentation: serialize AppBar operations and timestamp them
    caller = _threading.current_thread().name
    start_ts = time.perf_counter()
    acquired = _appbar_lock.acquire(timeout=2)
    colored_print(f"[APPBAR] [{start_ts:.6f}] set_appbar start by {caller}, requested_height={height}")

    try:
        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        # Ensure DPI awareness
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

        # If configured, verify this HWND is actually on the target screen; skip AppBar ops otherwise
        try:
            target_idx = get_settings().get('screen_index', None)
            if target_idx is not None and not _is_hwnd_on_target_screen(hwnd, target_idx):
                colored_print(f"[APPBAR] Skipping set_appbar for hwnd={hwnd} - not on target screen index={target_idx}")
                _trace_appbar_event('set_skip', hwnd, screen_index=target_idx, monitor=_get_monitor_info_for_hwnd(hwnd), result='skipped', reason='not_on_target')
                return None
        except Exception:
            pass

        # Get the ACTUAL physical window rect (Windows coordinates)
        actual_window_rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(actual_window_rect))
        actual_window_height = actual_window_rect.bottom - actual_window_rect.top
        actual_window_width = actual_window_rect.right - actual_window_rect.left

        # Determine device pixel ratio from Qt (fallback to 1.0)
        dpr = 1.0
        try:
            app = QtWidgets.QApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen and hasattr(screen, 'devicePixelRatioF'):
                    dpr = float(screen.devicePixelRatioF())
                elif screen and hasattr(screen, 'devicePixelRatio'):
                    # devicePixelRatio may be a method in some Qt versions
                    try:
                        dpr = float(screen.devicePixelRatio())
                    except Exception:
                        dpr = float(getattr(screen, 'devicePixelRatio', 1.0))
        except Exception:
            dpr = 1.0

        # Prefer the HWND's actual physical height as the authoritative reservation amount
        # to avoid logical→physical double-scaling mistakes.
        if actual_window_height and actual_window_height > 0:
            appbar_height_phys = actual_window_height
        else:
            appbar_height_phys = int(height * dpr) if height and height > 0 else 0

        # Debug: log DPR and values being used for reservation
        if DEBUG_APPBAR:
            colored_print(f"[APPBAR DIAGNOSTICS] DPR={dpr}, requested_logical={height}, actual_window_height={actual_window_height}, appbar_height_phys={appbar_height_phys}")

        msg_id = user32.RegisterWindowMessageW("TCKR_APPBAR_MESSAGE")
        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = hwnd
        abd.uCallbackMessage = msg_id
        abd.uEdge = ABE_TOP

        # Use the actual window rect for physical coordinates
        phys_left = actual_window_rect.left
        phys_top = actual_window_rect.top
        phys_right = actual_window_rect.right
        phys_width = actual_window_width

        # Set desired rectangle (physical pixels) using HWND rect
        abd.rc.left = phys_left
        abd.rc.top = phys_top
        abd.rc.right = phys_right
        abd.rc.bottom = phys_top + appbar_height_phys

        # Register and set position
        shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
        shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
        abd.rc.left = phys_left
        abd.rc.top = phys_top
        abd.rc.right = phys_right
        abd.rc.bottom = phys_top + appbar_height_phys
        shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
        shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))

        actual_reserved_height = abd.rc.bottom - abd.rc.top
        if DEBUG_APPBAR:
            colored_print(f"[APPBAR DIAGNOSTICS] After SETPOS QUERYPOS: top={abd.rc.top}, bottom={abd.rc.bottom}, reserved={actual_reserved_height}")

        if actual_reserved_height < appbar_height_phys:
            colored_print(f"[APPBAR WARNING] Windows only reserved {actual_reserved_height}px instead of {appbar_height_phys}px")
            abd.rc.top = phys_top
            abd.rc.bottom = phys_top + appbar_height_phys
            shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
            time.sleep(0.05)
            shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))

        # Verify and, if needed, manually set work area for primary monitor
        work_area_check = wintypes.RECT()
        user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area_check), 0)
        # If our work area top hasn't been advanced to account for our physical reservation, set it
        if work_area_check.top < (phys_top + appbar_height_phys):
            new_work_area = wintypes.RECT()
            new_work_area.left = work_area_check.left
            new_work_area.top = phys_top + appbar_height_phys
            new_work_area.right = work_area_check.right
            new_work_area.bottom = work_area_check.bottom
            SPI_SETWORKAREA = 47
            SPIF_SENDCHANGE = 0x0002
            user32.SystemParametersInfoW(SPI_SETWORKAREA, 0, ctypes.byref(new_work_area), SPIF_SENDCHANGE)
            time.sleep(0.08)

        # Force window position using SetWindowPos with physical values
        HWND_TOPMOST = -1
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(hwnd, HWND_TOPMOST, phys_left, phys_top, phys_width, int(appbar_height_phys), SWP_SHOWWINDOW | SWP_NOACTIVATE)

        # Instrumentation: record actual reserved height and who requested it
        actual_top = abd.rc.top
        end_ts = time.perf_counter()
        colored_print(f"[APPBAR] [{end_ts:.6f}] set_appbar end by {caller}, actual_top={actual_top}, reserved={actual_reserved_height}")
        _last_reserved_height = actual_reserved_height
        _last_reserved_by = caller
        try:
            _last_reserved_by_hwnd = int(hwnd)
        except Exception:
            _last_reserved_by_hwnd = None
        try:
            _last_reserved_ts = time.time()
        except Exception:
            _last_reserved_ts = 0.0
        # Trace appbar success with monitor info
        try:
            mon = _get_monitor_info_for_hwnd(hwnd)
            _trace_appbar_event('set', hwnd, screen_index=get_settings().get('screen_index', None), monitor=mon, result=actual_reserved_height)
        except Exception:
            pass

        return actual_top
    finally:
        try:
            if acquired:
                _appbar_lock.release()
        except Exception:
            pass

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


def _trace_visibility_event(hwnd, title, rect_tuple, is_visible, cloaked, style, ex_style, screen_index=None):
    """Append a compact JSON visibility trace record for offline analysis.
    This avoids heavy logging during runtime but gives a persistent record to inspect.

    NOTE: In some runtime contexts (__file__ may not be defined or writable),
    fallback to current working directory and emit a debug print when DEBUG_APPBAR
    is enabled so the developer can locate the file quickly.
    """
    try:
        # Prefer the script directory but fall back to CWD when needed
        try:
            base_dir = os.path.dirname(__file__) or os.getcwd()
        except Exception:
            base_dir = os.getcwd()
        path = os.path.join(base_dir, 'tckr_visibility.log')

        # Normalize hwnd safely - support ints, ctypes values, bytes
        hwnd_val = None
        try:
            hwnd_val = int(hwnd)
        except Exception:
            try:
                v = getattr(hwnd, 'value', None)
                if v is not None:
                    hwnd_val = int(v)
                elif isinstance(hwnd, (bytes, bytearray)):
                    # Interpret raw bytes as little-endian integer if provided
                    try:
                        hwnd_val = int.from_bytes(hwnd, 'little')
                    except Exception:
                        hwnd_val = None
            except Exception:
                hwnd_val = None

        # Gather extra native window diagnostics when possible
        extra = {}
        try:
            user32 = ctypes.windll.user32

            # Window long styles (signed/unsigned normalized)
            try:
                gwl_style = user32.GetWindowLongW(hwnd, -16)
                gwl_ex = user32.GetWindowLongW(hwnd, -20)
                extra['ws_visible'] = bool(gwl_style & 0x10000000)
                extra['ws_minimized'] = bool(gwl_style & 0x20000000)
                extra['gwl_style'] = f"0x{gwl_style & 0xFFFFFFFF:08X}"
                extra['gwl_exstyle'] = f"0x{gwl_ex & 0xFFFFFFFF:08X}"
            except Exception:
                pass

            # GetWindowPlacement -> showCmd
            try:
                class WINDOWPLACEMENT(ctypes.Structure):
                    _fields_ = [('length', wintypes.UINT), ('flags', wintypes.UINT), ('showCmd', wintypes.UINT), ('ptMinPosition', wintypes.POINT), ('ptMaxPosition', wintypes.POINT), ('rcNormalPosition', wintypes.RECT)]
                wp = WINDOWPLACEMENT()
                wp.length = ctypes.sizeof(WINDOWPLACEMENT)
                if user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
                    extra['showCmd'] = int(wp.showCmd)
            except Exception:
                pass

            # Layered window alpha
            try:
                crKey = wintypes.COLORREF()
                bAlpha = ctypes.c_byte()
                dwFlags = wintypes.DWORD()
                if user32.GetLayeredWindowAttributes(hwnd, ctypes.byref(crKey), ctypes.byref(bAlpha), ctypes.byref(dwFlags)):
                    extra['layered_alpha'] = int(bAlpha.value)
                extra['is_layered'] = bool(gwl_ex & 0x00080000)  # WS_EX_LAYERED
            except Exception:
                # Capture last error in case layered query fails
                try:
                    extra['last_error_layered'] = int(ctypes.get_last_error())
                except Exception:
                    pass

            # Optional: additional low-volume fields for deep diagnostics
            try:
                if get_settings().get('debug_extra_visibility_fields', False):
                    # Process id and executable if retrievable
                    try:
                        pid = wintypes.DWORD()
                        tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        extra['pid'] = int(pid.value) if pid.value else None
                    except Exception:
                        extra['pid'] = None

                    # Try psutil first (if available), fall back to QueryFullProcessImageName
                    try:
                        if extra.get('pid'):
                            try:
                                import psutil
                                p = psutil.Process(extra['pid'])
                                extra['proc_name'] = p.name()
                                try:
                                    extra['proc_exe'] = p.exe()
                                except Exception:
                                    extra['proc_exe'] = None
                            except Exception:
                                # Fallback using QueryFullProcessImageNameW
                                try:
                                    kernel32 = ctypes.windll.kernel32
                                    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                                    hProcess = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, extra['pid'])
                                    if hProcess:
                                        buff = ctypes.create_unicode_buffer(260)
                                        size = wintypes.DWORD(260)
                                        if kernel32.QueryFullProcessImageNameW(hProcess, 0, buff, ctypes.byref(size)):
                                            extra['proc_exe'] = buff.value
                                        kernel32.CloseHandle(hProcess)
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    # Owner/ancestor windows
                    try:
                        GW_OWNER = 4
                        owner_hwnd = user32.GetWindow(hwnd, GW_OWNER)
                        extra['owner_hwnd'] = int(owner_hwnd) if owner_hwnd else None
                    except Exception:
                        extra['owner_hwnd'] = None

                    # Window health flags
                    try:
                        extra['is_enabled'] = bool(user32.IsWindowEnabled(hwnd))
                    except Exception:
                        extra['is_enabled'] = None
                    try:
                        extra['is_minimized'] = bool(user32.IsIconic(hwnd))
                    except Exception:
                        extra['is_minimized'] = None
                    try:
                        extra['is_hung'] = bool(user32.IsHungAppWindow(hwnd))
                    except Exception:
                        extra['is_hung'] = None

                    # Window placement.showCmd mapping
                    try:
                        sc = extra.get('showCmd', None)
                        if sc is not None:
                            sc_map = {1: 'SW_SHOWNORMAL', 2: 'SW_SHOWMINIMIZED', 3: 'SW_SHOWMAXIMIZED', 4: 'SW_SHOWNOACTIVATE', 5: 'SW_SHOW', 6: 'SW_MINIMIZE', 7: 'SW_SHOWMINNOACTIVE', 8: 'SW_SHOWNA', 9: 'SW_RESTORE'}
                            extra['showCmd_name'] = sc_map.get(int(sc), str(sc))
                    except Exception:
                        pass

                    # Last error snapshot for diagnostics
                    try:
                        extra['last_error'] = int(ctypes.get_last_error())
                    except Exception:
                        pass
            except Exception:
                # Protect tracing from any unexpected failures
                try:
                    extra['debug_extra_error'] = str(sys.exc_info()[1])
                except Exception:
                    pass
        except Exception:
            pass

        rec = {
            'ts': time.time(),
            'hwnd': hwnd_val,
            'hwnd_raw': repr(hwnd),
            'title': title,
            'rect': rect_tuple,
            'visible': bool(is_visible),
            'cloaked': cloaked,
            'style': style,
            'ex_style': ex_style,
            'screen_index': screen_index,
            'extra': extra
        }
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec) + "\n")
            if DEBUG_APPBAR:
                colored_print(f"[TRACE] Wrote visibility trace to: {path}")
        except Exception as e:
            if DEBUG_APPBAR:
                colored_print(f"[TRACE] Failed to write visibility trace to {path}: {e}")
    except Exception as e:
        if DEBUG_APPBAR:
            colored_print(f"[TRACE] _trace_visibility_event failed: {e}")


def _trace_ticker_state_event(instance, state, info=None):
    """Append a compact JSON ticker-state trace record for offline analysis.
    Records instance id, window title, prices_count and HWND where possible."""
    try:
        try:
            base_dir = os.path.dirname(__file__) or os.getcwd()
        except Exception:
            base_dir = os.getcwd()
        path = os.path.join(base_dir, 'tckr_visibility.log')

        inst_id = id(instance)
        title = None
        try:
            title = instance.windowTitle()
        except Exception:
            try:
                title = getattr(instance, 'title', None)
            except Exception:
                title = None

        prices_count = 0
        try:
            prices_count = len(getattr(instance, 'prices', {}) or {})
        except Exception:
            prices_count = 0

        hwnd_val = None
        try:
            hwnd_val = int(instance.winId())
        except Exception:
            try:
                v = getattr(instance, 'winId', None)
                hwnd_val = int(v) if isinstance(v, int) else None
            except Exception:
                hwnd_val = None

        rec = {
            'ts': time.time(),
            'kind': 'ticker_state',
            'instance_id': inst_id,
            'title': title,
            'state': state,
            'prices_count': prices_count,
            'hwnd': hwnd_val,
            'info': info
        }
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec) + "\n")
            if DEBUG_APPBAR:
                colored_print(f"[TRACE] Wrote ticker-state trace to: {path} ({state})")
        except Exception as e:
            if DEBUG_APPBAR:
                colored_print(f"[TRACE] Failed to write ticker-state trace to {path}: {e}")
    except Exception as e:
        if DEBUG_APPBAR:
            colored_print(f"[TRACE] _trace_ticker_state_event failed: {e}")


def _trace_repair_attempt_event(hwnd, context, attempt, visible, last_error=None, screen_index=None):
    """Write a compact JSON 'repair_attempt' record to the visibility log."""
    try:
        try:
            base_dir = os.path.dirname(__file__) or os.getcwd()
        except Exception:
            base_dir = os.getcwd()
        path = os.path.join(base_dir, 'tckr_visibility.log')

        rec = {
            'ts': time.time(),
            'kind': 'repair_attempt',
            'context': context,
            'attempt': int(attempt),
            'hwnd': int(hwnd) if hwnd else None,
            'visible': bool(visible),
            'last_error': int(last_error) if last_error is not None else None,
            'screen_index': screen_index
        }
        try:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec) + "\n")
            if DEBUG_APPBAR:
                colored_print(f"[TRACE] Wrote repair-attempt trace to: {path} ({context} attempt={attempt})")
        except Exception as e:
            if DEBUG_APPBAR:
                colored_print(f"[TRACE] Failed to write repair-attempt trace to {path}: {e}")
    except Exception as e:
        if DEBUG_APPBAR:
            colored_print(f"[TRACE] _trace_repair_attempt_event failed: {e}")


# --- Massive monitor tracing helpers ---
def _get_monitor_device_from_hmon(hmon):
    try:
        if not hmon:
            return None
        user32 = ctypes.windll.user32
        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ('cbSize', wintypes.DWORD),
                ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT),
                ('dwFlags', wintypes.DWORD),
                ('szDevice', ctypes.c_wchar * 32)
            ]
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            dev = mi.szDevice
            rect = (mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right, mi.rcMonitor.bottom)
            work = (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
            return {'hmon': int(hmon), 'device': dev, 'rect': rect, 'work': work, 'flags': int(mi.dwFlags)}
    except Exception:
        return None


def _get_monitor_info_for_hwnd(hwnd):
    try:
        user32 = ctypes.windll.user32
        if not hwnd:
            return None
        MONITOR_DEFAULTTONULL = 0
        hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONULL)
        if not hmon:
            # Try by window rect center
            rect = wintypes.RECT()
            try:
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                pt = wintypes.POINT((rect.left + rect.right)//2, (rect.top + rect.bottom)//2)
                hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONULL)
            except Exception:
                return None
        return _get_monitor_device_from_hmon(hmon)
    except Exception:
        return None


def _is_hwnd_on_target_screen(hwnd, screen_index=None):
    """Return True if HWND maps to screen at screen_index. screen_index None -> True (no constraint)."""
    try:
        if screen_index is None:
            return True
        mon = _get_monitor_info_for_hwnd(hwnd)
        if not mon:
            return False
        try:
            screens = QtGui.QGuiApplication.screens()
            if 0 <= int(screen_index) < len(screens):
                sc = screens[int(screen_index)]
                # Prefer device name comparison
                if mon.get('device') and sc.name() and mon.get('device') == sc.name():
                    return True
                # Fallback to rect compare
                rect = mon.get('rect')
                if rect and sc.geometry():
                    return rect == (sc.geometry().left(), sc.geometry().top(), sc.geometry().right(), sc.geometry().bottom())
        except Exception:
            pass
        return False
    except Exception:
        return False


def _trace_appbar_event(action, hwnd, screen_index=None, monitor=None, result=None, reason=None):
    try:
        base_dir = os.path.dirname(__file__) or os.getcwd()
    except Exception:
        base_dir = os.getcwd()
    path = os.path.join(base_dir, 'tckr_visibility.log')
    # gather lightweight owner/process and stack diagnostics for investigation
    owner_pid = None
    owner_exe = None
    call_stack = None
    try:
        if hwnd:
            try:
                pid_holder = ctypes.c_ulong(0)
                ctypes.windll.user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(pid_holder))
                owner_pid = int(pid_holder.value)
            except Exception:
                owner_pid = None
            if owner_pid:
                try:
                    import psutil
                    owner_exe = psutil.Process(owner_pid).exe()
                except Exception:
                    owner_exe = None
            try:
                import traceback
                stack = traceback.extract_stack(limit=6)[:-1]
                call_stack = [f"{os.path.basename(s.filename)}:{s.name}:{s.lineno}" for s in stack[-4:]]
            except Exception:
                call_stack = None
    except Exception:
        pass

    rec = {
        'ts': time.time(),
        'kind': 'appbar_event',
        'action': action,
        'hwnd': int(hwnd) if hwnd else None,
        'screen_index': screen_index,
        'monitor': monitor,
        'result': result,
        'reason': reason,
        'owner_pid': owner_pid,
        'owner_exe': owner_exe,
        'call_stack': call_stack
    }
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + "\n")
        if DEBUG_APPBAR:
            colored_print(f"[TRACE] Wrote appbar_event trace to: {path} ({action} hwnd={hwnd} result={result} reason={reason})")
    except Exception:
        pass



def _force_repaint_hwnd(hwnd_int):
    """Attempt native invalidation/update/redraw for a window given an integer HWND.

    Supports a small bounded retry loop when `debug_try_force_repaint_retries` is enabled.
    Returns True if at least one attempt succeeded, False on total failure.
    """
    try:
        user32 = ctypes.windll.user32

        # Retry configuration (gated)
        try:
            retry_enabled = bool(get_settings().get('debug_try_force_repaint_retries', False))
            retry_count = int(get_settings().get('debug_repaint_retry_count', 2)) if retry_enabled else 0
            backoff_ms = int(get_settings().get('debug_repair_backoff_ms', 150))
        except Exception:
            retry_enabled = False
            retry_count = 0
            backoff_ms = 150

        total_attempts = 1 + max(0, retry_count)
        success = False
        for attempt in range(1, total_attempts + 1):
            try:
                # Invalidate and update
                try:
                    user32.InvalidateRect(hwnd_int, None, True)
                    user32.UpdateWindow(hwnd_int)
                except Exception:
                    pass

                # Redraw immediately
                try:
                    RDW_INVALIDATE = 0x0001
                    RDW_UPDATENOW = 0x0100
                    user32.RedrawWindow(hwnd_int, None, None, RDW_INVALIDATE | RDW_UPDATENOW)
                except Exception:
                    pass

                # Small pause to let system process
                time.sleep(backoff_ms / 1000.0)

                # Consider success if no exception reached here and window is valid
                try:
                    visible = bool(user32.IsWindowVisible(hwnd_int))
                except Exception:
                    visible = True

                try:
                    last_err = ctypes.get_last_error()
                except Exception:
                    last_err = None
                colored_print(f"[REPAINT] Attempt {attempt}/{total_attempts} for hwnd={hwnd_int} - visible={visible} last_error={last_err}")
                try:
                    _trace_ticker_state_event(None, 'forced_native_repaint_attempt', info={'hwnd': hwnd_int, 'attempt': attempt, 'visible': visible, 'last_error': last_err})
                except Exception:
                    pass

                success = True if visible else success
                if visible:
                    return True
            except Exception as e:
                if DEBUG_APPBAR:
                    colored_print(f"[REPAINT] Exception on attempt {attempt} for hwnd={hwnd_int}: {e}")
            # Backoff before next try
            time.sleep(backoff_ms / 1000.0)

        return success
    except Exception:
        return False


def _invoke_check_first_paint(target):
    """Resiliently call the first-paint watchdog on the correct object.

    Prefer object._check_first_paint_after_load(), else try target.ticker_window,
    else force a native repaint on the target HWND as a last resort.
    """
    try:
        # Prefer direct method if available
        if hasattr(target, '_check_first_paint_after_load'):
            try:
                target._check_first_paint_after_load()
                return
            except Exception as e:
                if DEBUG_APPBAR:
                    colored_print(f"[WATCHDOG] target._check_first_paint_after_load raised: {e}")
        # Next try the ticker_window child
        tw = getattr(target, 'ticker_window', None)
        if tw is not None and hasattr(tw, '_check_first_paint_after_load'):
            try:
                tw._check_first_paint_after_load()
                return
            except Exception as e:
                if DEBUG_APPBAR:
                    colored_print(f"[WATCHDOG] ticker_window._check_first_paint_after_load raised: {e}")
        # Final fallback: force native repaint using HWND if available
        try:
            hwnd = None
            if hasattr(target, 'winId'):
                try:
                    hwnd = int(target.winId())
                except Exception:
                    pass
            elif tw is not None and hasattr(tw, 'winId'):
                try:
                    hwnd = int(tw.winId())
                except Exception:
                    pass

            if hwnd:
                colored_print(f"[WATCHDOG] Forcing native repaint fallback for hwnd={hwnd}")
                _force_repaint_hwnd(hwnd)
                try:
                    _trace_ticker_state_event(target if hasattr(target, 'windowTitle') else tw or target, 'forced_native_repaint', info={'hwnd': hwnd})
                except Exception:
                    pass
                return
        except Exception as e:
            if DEBUG_APPBAR:
                colored_print(f"[WATCHDOG] Exception during native repaint fallback: {e}")
    except Exception as e:
        if DEBUG_APPBAR:
            colored_print(f"[WATCHDOG] _invoke_check_first_paint unexpected error: {e}")


def _attempt_repair_not_visible(hwnd, rect_tuple, screen_index=None, context=''):
    """Try to make a window visible when it's reported not visible.
    Non-destructive; logs attempts. Returns True if visible after attempt."""
    try:
        # Gate by debug setting
        try:
            enabled = get_settings().get('debug_try_fix_not_visible', True)
        except Exception:
            enabled = True
        if not enabled:
            return False

        user32 = ctypes.windll.user32

        # Normalize HWND int robustly (int, ctypes objects, pointers, bytes)
        hwnd_int = None
        try:
            if isinstance(hwnd, int):
                hwnd_int = hwnd
            else:
                try:
                    hwnd_int = int(hwnd)
                except Exception:
                    # Try common ctypes patterns
                    if hasattr(hwnd, 'value'):
                        hwnd_int = hwnd.value
                    else:
                        try:
                            hwnd_int = ctypes.cast(hwnd, ctypes.c_void_p).value
                        except Exception:
                            hwnd_int = None

            # If we got raw bytes, convert little-endian
            if isinstance(hwnd_int, (bytes, bytearray)):
                try:
                    hwnd_int = int.from_bytes(hwnd_int, 'little')
                except Exception:
                    hwnd_int = None

            # Zero/None are considered invalid here
            if not hwnd_int:
                if DEBUG_APPBAR:
                    colored_print(f"[REPAIR] Cannot normalize hwnd for repair (post attempts): {hwnd!r} -> {hwnd_int!r}")
                return False
        except Exception as e:
            if DEBUG_APPBAR:
                colored_print(f"[REPAIR] Exception normalizing hwnd: {e} ({hwnd!r})")
            return False

        # Quick re-check
        was_visible = bool(user32.IsWindowVisible(hwnd_int))
        if was_visible:
            if DEBUG_APPBAR:
                colored_print(f"[REPAIR] Already visible hwnd={hwnd_int} ({context})")
            return True

        SW_SHOW = 5
        SW_RESTORE = 9
        HWND_TOPMOST = -1
        SWP_NOACTIVATE = 0x0010
        SWP_SHOWWINDOW = 0x0040

        # Retry configuration (gated)
        try:
            retry_enabled = bool(get_settings().get('debug_try_force_repaint_retries', False))
            retry_count = int(get_settings().get('debug_repair_retry_count', 2)) if retry_enabled else 0
            backoff_ms = int(get_settings().get('debug_repair_backoff_ms', 150))
        except Exception:
            retry_enabled = False
            retry_count = 0
            backoff_ms = 150

        total_attempts = 1 + max(0, retry_count)
        for attempt in range(1, total_attempts + 1):
            try:
                colored_print(f"[REPAIR] Attempt {attempt}/{total_attempts}: ShowWindow / SetWindowPos for hwnd={hwnd_int} ({context})")

                # Try ShowWindow then restore
                try:
                    user32.ShowWindow(hwnd_int, SW_SHOW)
                    time.sleep(0.03)
                    user32.ShowWindow(hwnd_int, SW_RESTORE)
                except Exception:
                    pass

                # Force position/topmost again
                try:
                    x, y, r, b = rect_tuple
                    w = r - x
                    h = b - y
                    user32.SetWindowPos(hwnd_int, HWND_TOPMOST, x, y, w, h, SWP_SHOWWINDOW | SWP_NOACTIVATE)
                except Exception:
                    pass

                # Give a small interval for Window Manager to update state
                time.sleep(backoff_ms / 1000.0)

                # Optionally trigger a native repaint as part of repair
                try:
                    _force_repaint_hwnd(hwnd_int)
                except Exception:
                    pass

                now_visible = bool(user32.IsWindowVisible(hwnd_int))
                colored_print(f"[REPAIR] hwnd={hwnd_int} visible after attempt {attempt}={now_visible} ({context})")

                # Capture last error snapshot for diagnostics
                try:
                    last_err = ctypes.get_last_error()
                except Exception:
                    last_err = None

                # Trace each attempt for post-mortem (visibility + structured repair attempt)
                try:
                    _trace_visibility_event(hwnd, f"REPAIR-{context}-ATTEMPT-{attempt}", rect_tuple, now_visible, None, None, None, screen_index)
                except Exception:
                    pass
                try:
                    _trace_repair_attempt_event(hwnd_int, context, attempt, now_visible, last_error=last_err, screen_index=screen_index)
                except Exception:
                    pass

                if now_visible:
                    return True

            except Exception as ex:
                if DEBUG_APPBAR:
                    colored_print(f"[REPAIR] Exception in attempt {attempt}: {ex}")

        # All attempts failed
        return False
    except Exception as e:
        if DEBUG_APPBAR:
            colored_print(f"[REPAIR] Exception during repair attempt: {e}")
        return False

def remove_appbar(hwnd):
    """Remove the AppBar registration and restore the work area"""
    import time as time_module
    start_time = time_module.time()

    global _appbar_lock
    caller = _threading.current_thread().name
    start_ts = time.perf_counter()
    acquired = _appbar_lock.acquire(timeout=2)
    colored_print(f"[APPBAR] [{start_ts:.6f}] remove_appbar start by {caller}, hwnd={hwnd}")
    # If a combined reservation was set very recently, skip removal to avoid
    # accidentally tearing down a combined AppBar created for multi-ticker layout.
    try:
        global _last_reserved_ts, _last_reserved_height, _last_reserved_by_hwnd
        now_ts = time.time()
        ttl = 10.0  # seconds to honor recent combined reservation
        try:
            configured_height = get_settings().get('ticker_height', 35) * 2
        except Exception:
            configured_height = 70

        # If a recent combined reservation exists and it was applied by a different HWND,
        # do not remove it — this avoids race conditions where another instance just applied
        # the combined AppBar and we would immediately teardown their reservation.
        # If a recent combined reservation exists and it was applied by a different HWND,
        # do not remove it — but only skip removal when we currently have a ReservationKeeper
        # (meaning a combined reservation is actively being held by a separate HWND).
        global _reservation_keeper
        if _last_reserved_ts and (now_ts - _last_reserved_ts) < ttl and _last_reserved_height >= configured_height:
            try:
                keeper_present = _reservation_keeper is not None
                if keeper_present and _last_reserved_by_hwnd and int(_last_reserved_by_hwnd) != int(hwnd):
                    colored_print(f"[APPBAR] Skipping remove_appbar for hwnd={hwnd}; recent combined reservation {_last_reserved_height}px by hwnd={_last_reserved_by_hwnd} detected ({now_ts - _last_reserved_ts:.1f}s ago) and keeper present")
                    if acquired:
                        try:
                            _appbar_lock.release()
                        except Exception:
                            pass
                    return
            except Exception:
                # Fall back to previous behavior if comparison fails
                pass

    except Exception:
        pass

    try:
        # Skip removal if this HWND is not on the configured screen to avoid touching other monitors
        try:
            target_idx = get_settings().get('screen_index', None)
            if target_idx is not None and not _is_hwnd_on_target_screen(hwnd, target_idx):
                colored_print(f"[APPBAR] Skipping remove_appbar for hwnd={hwnd} - not on target screen index={target_idx}")
                _trace_appbar_event('remove_skip', hwnd, screen_index=target_idx, monitor=_get_monitor_info_for_hwnd(hwnd), result='skipped', reason='not_on_target')
                if acquired:
                    try:
                        _appbar_lock.release()
                    except Exception:
                        pass
                return False
        except Exception:
            pass

        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32

        if DEBUG_APPBAR: print(f"[APPBAR] Removing AppBar registration for window handle {hwnd}")

        abd = APPBARDATA()
        abd.cbSize = ctypes.sizeof(APPBARDATA)
        abd.hWnd = hwnd
        result = shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
        if DEBUG_APPBAR: print(f"[APPBAR] ABM_REMOVE result: {result}")
        # Trace remove attempt
        try:
            mon = _get_monitor_info_for_hwnd(hwnd)
            _trace_appbar_event('remove', hwnd, screen_index=get_settings().get('screen_index', None), monitor=mon, result=result)
        except Exception:
            pass

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
    finally:
        try:
            end_ts = time.perf_counter()
            colored_print(f"[APPBAR] [{end_ts:.6f}] remove_appbar end by {caller}, duration_ms={(end_ts - start_ts)*1000:.1f}")
            if acquired:
                _appbar_lock.release()
        except Exception:
            pass
        


def reserve_combined_appbar(primary_hwnd, secondary_hwnd, screen_index=0):
    """Compute physical heights of two windows and register a combined AppBar height."""
    try:
        user32 = ctypes.windll.user32
        rect1 = wintypes.RECT()
        rect2 = wintypes.RECT()
        user32.GetWindowRect(int(primary_hwnd), ctypes.byref(rect1))
        user32.GetWindowRect(int(secondary_hwnd), ctypes.byref(rect2))
        h1 = rect1.bottom - rect1.top
        h2 = rect2.bottom - rect2.top
        combined = h1 + h2
        colored_print(f"[SECOND TICKER] Registering combined AppBar height: {combined}px (h1={h1}, h2={h2})")

        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        if 0 <= screen_index < len(screens):
            screen = screens[screen_index]
        else:
            screen = app.primaryScreen()
        rect = screen.geometry()

        # Per-screen key (use screen name when available, otherwise geometry tuple)
        try:
            screen_key = screen.name() if hasattr(screen, 'name') else None
        except Exception:
            screen_key = None
        if not screen_key:
            screen_key = f"{rect.left()}_{rect.top()}_{rect.width()}_{rect.height()}"

        # If this screen was previously observed to not support AppBar (reserved==0), skip heavy combined reservation attempts
        if _appbar_supported.get(screen_key) is False and not get_settings().get('enable_appbar_on_nonprimary', False):
            colored_print(f"[SECOND TICKER] Screen {screen_key} previously observed to not support AppBar; skipping combined reservation")
            return None

        # Ensure primary and secondary hwnds are actually on the target screen; try to nudge them if not
        try:
            target_idx = int(screen_index) if screen_index is not None else None
            primary_on_target = _is_hwnd_on_target_screen(primary_hwnd, target_idx)
            secondary_on_target = _is_hwnd_on_target_screen(secondary_hwnd, target_idx)
            if not primary_on_target or not secondary_on_target:
                colored_print(f"[SECOND TICKER] One or both ticker windows not on target screen (primary_on_target={primary_on_target} secondary_on_target={secondary_on_target}); attempting native move")
                try:
                    user32.SetWindowPos(int(primary_hwnd), 0, rect.left(), rect.top(), 0, 0, 0x0004 | 0x0001 | 0x0040)
                    user32.SetWindowPos(int(secondary_hwnd), 0, rect.left(), rect.top() + h1, 0, 0, 0x0004 | 0x0001 | 0x0040)
                    time.sleep(0.05)
                except Exception:
                    pass
                # Re-evaluate
                primary_on_target = _is_hwnd_on_target_screen(primary_hwnd, target_idx)
                secondary_on_target = _is_hwnd_on_target_screen(secondary_hwnd, target_idx)
                if not primary_on_target or not secondary_on_target:
                    colored_print(f"[SECOND TICKER] Aborting combined reservation - windows not present on target screen after nudge")
                    _trace_appbar_event('set_skip_combined', primary_hwnd, screen_index=target_idx, monitor=_get_monitor_info_for_hwnd(primary_hwnd), result='skipped', reason='not_on_target')
                    return None
        except Exception:
            pass

        # Try multiple synchronous remove/register attempts to force Windows to update work area
        max_attempts = 5
        last_top = None
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    colored_print(f"[SECOND TICKER] Combined reservation retry attempt {attempt}/{max_attempts}")

                # Ensure any previous AppBar registration is removed first
                try:
                    remove_appbar(int(primary_hwnd))
                except Exception:
                    pass

                # Small pause to let Windows process removal synchronously
                time.sleep(0.05)

                # Request combined reservation (blocking call into set_appbar)
                actual_top = set_appbar(int(primary_hwnd), combined, rect)
                last_top = actual_top

                # Verify work area top for the monitor containing our rect
                work_area = wintypes.RECT()
                user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0)  # SPI_GETWORKAREA

                # Compute reserved amount relative to this screen's top
                reserved = work_area.top - rect.top()
                colored_print(f"[SECOND TICKER] After attempt {attempt}: work_area.top={work_area.top}, screen.top={rect.top()}, reserved={reserved}, requested={combined}")

                # Update per-screen AppBar support cache: if Windows returned zero reserved, mark unsupported
                try:
                    if reserved == 0:
                        _appbar_supported[screen_key] = False
                    elif reserved >= combined:
                        _appbar_supported[screen_key] = True
                except Exception:
                    pass

                # If Windows honored the full combined reservation, we're done
                if reserved >= combined:
                    colored_print(f"[SECOND TICKER] Combined AppBar reservation succeeded on attempt {attempt}")
                    try:
                        force_window_to_top(int(primary_hwnd), rect, h1)
                    except Exception:
                        pass
                    return actual_top

                # Otherwise, wait a bit and retry (exponential backoff)
                time.sleep(0.08 * attempt)

            except Exception as e:
                colored_print(f"[SECOND TICKER] Error during combined reservation attempt {attempt}: {e}")
                time.sleep(0.1)

        # If we get here, Windows did not honor the full combined reservation
        colored_print(f"[SECOND TICKER] Warning: Windows did not reserve full combined height after {max_attempts} attempts (reserved approx {reserved}px, requested {combined}px)")
        # Try to at least force primary to top using its own physical height
        try:
            force_window_to_top(int(primary_hwnd), rect, h1)
        except Exception:
            pass

        return last_top
    except Exception as e:
        colored_print(f"[SECOND TICKER] Failed combined reservation: {e}")
        return None


class ReservationKeeper(QtWidgets.QWidget):
    """Invisible helper window that holds an AppBar reservation for combined tickers."""
    def __init__(self, rect, reserved_height):
        super().__init__()
        flags = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        try:
            self.setWindowOpacity(0.0)
        except Exception:
            pass
        # Ensure a small but valid geometry so Qt creates a native HWND
        # Convert the requested physical reserved_height into Qt logical units
        # so that the native HWND produced by Qt has the intended physical height
        dpr = 1.0
        try:
            app = QtWidgets.QApplication.instance()
            if app:
                screen = app.primaryScreen()
                if screen and hasattr(screen, 'devicePixelRatioF'):
                    dpr = float(screen.devicePixelRatioF())
                elif screen and hasattr(screen, 'devicePixelRatio'):
                    try:
                        dpr = float(screen.devicePixelRatio())
                    except Exception:
                        dpr = 1.0
        except Exception:
            dpr = 1.0

        w = max(1, int(rect.width()))
        # Compute logical height so that logical * dpr ≈ reserved_height (physical)
        h_logical = max(1, int(round(reserved_height / dpr)))
        if DEBUG_APPBAR:
            colored_print(f"[SECOND TICKER] Keeper creating Qt geometry w={w}, h_logical={h_logical} (reserved_phys={reserved_height}, dpr={dpr})")
        self.setGeometry(rect.left(), rect.top(), w, h_logical)
        self._reserved_height = reserved_height
        self._rect = rect
        self._registered = False
        self._honored = False  # True when Windows actually honors the reserved height
        # Show to force native HWND creation, then register AppBar using our HWND
        self.show()
        QtWidgets.QApplication.processEvents()
        try:
            keeper_hwnd = int(self.winId())
            set_appbar(keeper_hwnd, reserved_height, rect)
            self._registered = True
        except Exception:
            self._registered = False

    def remove(self):
        # Declare globals used in this method before any usage to avoid SyntaxError
        global _reservation_keeper, _last_reserved_height, _last_reserved_by_hwnd, _last_reserved_ts, _keeper_removal_in_progress

        try:
            keeper_hwnd = None
            try:
                keeper_hwnd = int(self.winId())
            except Exception:
                keeper_hwnd = None

            # Mark removal in-progress so primaries defer re-registration
            global _keeper_removal_in_progress
            try:
                _keeper_removal_in_progress = True
            except Exception:
                pass

            user32 = ctypes.windll.user32

            # If this keeper never successfully registered an AppBar, do a minimal cleanup
            # and avoid force-closing other ticker windows. This prevents failed keeper
            # creation from aggressively tearing down ticker windows (observed when
            # keeper creation wasn't honored by Windows).
            try:
                # If keeper wasn't registered or Windows didn't honor the reservation,
                # do a minimal cleanup and avoid force-closing other ticker windows.
                if not getattr(self, '_registered', False) or not getattr(self, '_honored', False):
                    if DEBUG_APPBAR:
                        colored_print(f"[APPBAR] Keeper removal: keeper not registered/honored (registered={getattr(self,'_registered',False)}, honored={getattr(self,'_honored',False)}) - skipping forced close of secondary tickers")
                    try:
                        self.hide()
                        self.close()
                    except Exception:
                        pass
                    # Clear any partial reservation state and exit early
                    try:
                        _reservation_keeper = None
                        _last_reserved_height = 0
                        _last_reserved_by_hwnd = None
                        _last_reserved_ts = 0.0
                    except Exception:
                        pass
                    return
            except Exception:
                pass

            # Capture current work-area top so we can detect a shrink (pre-remove)
            try:
                _pre_remove_wa = wintypes.RECT()
                user32.SystemParametersInfoW(48, 0, ctypes.byref(_pre_remove_wa), 0)
                _pre_remove_wa_top = getattr(_pre_remove_wa, 'top', -1)
            except Exception:
                _pre_remove_wa_top = -1

            # Build exclusion set: keep the keeper HWND and any last-reserved HWND out of forced-close
            exclude = set()
            if keeper_hwnd:
                exclude.add(keeper_hwnd)
            try:
                if _last_reserved_by_hwnd:
                    exclude.add(int(_last_reserved_by_hwnd))
            except Exception:
                pass

            if DEBUG_APPBAR:
                colored_print(f"[APPBAR] Keeper removal: attempting to close secondary tickers first (exclude={exclude})")

            # 1) Passive Qt close
            try:
                _force_close_secondary_tickers()
            except Exception:
                pass

            # 2) Enum-based WM_CLOSE pass (skip excludes)
            try:
                _force_close_secondary_tickers_by_enum(exclude_hwnds=list(exclude))
            except Exception:
                pass

            # 3) Targeted per-HWND forced-close with longer polling
            try:
                created_hwnds = list(_created_ticker_hwnds)
                for th in created_hwnds:
                    try:
                        if th in exclude:
                            continue
                        if not user32.IsWindow(th):
                            try:
                                _created_ticker_hwnds.discard(th)
                            except Exception:
                                pass
                            continue

                        if DEBUG_APPBAR:
                            colored_print(f"[APPBAR] Forcing close of tracked ticker HWND={th}")

                        try:
                            remove_appbar(th)
                        except Exception:
                            pass

                        # Send WM_CLOSE (timeout) then PostMessage as fallback
                        try:
                            WM_CLOSE = 0x0010
                            SMTO_ABORTIFHUNG = 0x0002
                            # Increase timeout to give hung windows more time to respond
                            user32.SendMessageTimeoutW(th, WM_CLOSE, 0, 0, SMTO_ABORTIFHUNG, 2000, None)
                        except Exception:
                            pass
                        try:
                            user32.PostMessageW(th, WM_CLOSE, 0, 0)
                        except Exception:
                            pass

                        # Poll for disappearance (up to ~8s)
                        gone = False
                        for _poll in range(160):
                            try:
                                if not user32.IsWindow(th):
                                    gone = True
                                    break
                            except Exception:
                                gone = True
                                break
                            time.sleep(0.05)

                        if gone:
                            try:
                                _created_ticker_hwnds.discard(th)
                            except Exception:
                                pass
                        else:
                                        # Last-resort: attempt to terminate the owning process for stubborn windows
                                        if DEBUG_APPBAR:
                                            colored_print(f"[APPBAR] Tracked HWND {th} did not close after forced attempts - considering process termination")
                                        try:
                                            # Respect user settings - do not terminate processes by default
                                            allow_term = False
                                            try:
                                                allow_term = bool(get_settings().get('allow_forced_termination', False)) or bool(DEBUG_ALLOW_FORCED_TERMINATION)
                                            except Exception:
                                                allow_term = bool(DEBUG_ALLOW_FORCED_TERMINATION)

                                            if not allow_term:
                                                if DEBUG_APPBAR:
                                                    colored_print(f"[APPBAR] Skipping process termination for HWND {th} (settings disallow forced termination)")
                                            else:
                                                # Gather PID and exe path for diagnostics before terminating
                                                try:
                                                    pid = wintypes.DWORD()
                                                    user32.GetWindowThreadProcessId(wintypes.HWND(th), ctypes.byref(pid))
                                                    pid_val = pid.value if pid.value else None
                                                    remoteexe = None
                                                    if pid_val:
                                                        try:
                                                            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                                                            hproc_q = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid_val))
                                                            if hproc_q:
                                                                buf = ctypes.create_unicode_buffer(260)
                                                                buf_size = wintypes.DWORD(260)
                                                                if ctypes.windll.kernel32.QueryFullProcessImageNameW(hproc_q, 0, buf, ctypes.byref(buf_size)):
                                                                    remoteexe = buf.value
                                                                try:
                                                                    ctypes.windll.kernel32.CloseHandle(hproc_q)
                                                                except Exception:
                                                                    pass
                                                        except Exception:
                                                            remoteexe = None
                                                    colored_print(f"[APPBAR] Termination requested: HWND={th}, PID={pid_val}, exe={remoteexe}")
                                                except Exception:
                                                    pass

                                                terminated = _terminate_window_process(th)
                                                if terminated and DEBUG_APPBAR:
                                                    colored_print(f"[APPBAR] Terminated process owning HWND {th}")
                                                # brief poll to confirm window gone
                                                for _p in range(40):
                                                    try:
                                                        if not user32.IsWindow(th):
                                                            try:
                                                                _created_ticker_hwnds.discard(th)
                                                            except Exception:
                                                                pass
                                                            break
                                                    except Exception:
                                                        break
                                                    time.sleep(0.05)
                                        except Exception:
                                            if DEBUG_APPBAR:
                                                colored_print(f"[APPBAR] Exception while attempting termination for HWND {th}")
                                            pass

                    except Exception:
                        pass
            except Exception:
                pass

            # 4) Wait briefly for any remaining TCKR windows (excluding keepers) to vanish
            remaining_nonexcluded = None
            try:
                for i in range(160):
                    rem = _list_and_diagnose_tckr_windows()
                    remaining_nonexcluded = [r for r in rem if int(r[0]) not in exclude]
                    if not remaining_nonexcluded:
                        break
                    time.sleep(0.05)
                    # Mid-wait escalation: try enum-based WM_CLOSE again
                    if i == 40 or i == 100:
                        try:
                            _force_close_secondary_tickers_by_enum(exclude_hwnds=list(exclude))
                        except Exception:
                            pass
            except Exception:
                remaining_nonexcluded = []

            if remaining_nonexcluded and DEBUG_APPBAR:
                colored_print(f"[APPBAR] Keeper removal: secondary windows still present after forced-close wait: {[(r[0], r[1]) for r in remaining_nonexcluded]}")

            # Before removing the keeper, wait briefly for Windows work-area to shrink
            try:
                if _pre_remove_wa_top is not None and _pre_remove_wa_top >= 0:
                    wa_changed = False
                    for i in range(80):
                        wa = wintypes.RECT()
                        user32.SystemParametersInfoW(48, 0, ctypes.byref(wa), 0)
                        if getattr(wa, 'top', -1) < _pre_remove_wa_top:
                            wa_changed = True
                            break
                        time.sleep(0.05)
                        if i == 20 or i == 50:
                            try:
                                _force_close_secondary_tickers_by_enum(exclude_hwnds=list(exclude))
                            except Exception:
                                pass
                    if not wa_changed and DEBUG_APPBAR:
                        colored_print(f"[APPBAR] Keeper removal: pre-remove work area did not change after polling (will still attempt removal)")
            except Exception:
                pass

            # Now remove keeper AppBar registration
            try:
                if keeper_hwnd and user32.IsWindow(keeper_hwnd):
                    remove_appbar(keeper_hwnd)
            except Exception:
                pass

            # Hide/close the keeper widget
            try:
                self.hide()
                self.close()
            except Exception:
                pass

            # Clear global keeper reference and last-reservation metadata so primaries can re-register
            try:
                _reservation_keeper = None
                _last_reserved_height = 0
                _last_reserved_by_hwnd = None
                _last_reserved_ts = 0.0
            except Exception:
                pass

            # Ask Windows to recalculate work area and wait for propagation
            try:
                SPI_SETWORKAREA = 47
                SPIF_SENDCHANGE = 0x0002
                SPIF_UPDATEINIFILE = 0x0001

                before = wintypes.RECT()
                try:
                    user32.SystemParametersInfoW(48, 0, ctypes.byref(before), 0)
                except Exception:
                    before.top = -1

                user32.SystemParametersInfoW(SPI_SETWORKAREA, 0, None, SPIF_SENDCHANGE | SPIF_UPDATEINIFILE)

                # Poll for work-area change (up to ~2s)
                changed = False
                try:
                    for i in range(40):
                        wa = wintypes.RECT()
                        user32.SystemParametersInfoW(48, 0, ctypes.byref(wa), 0)
                        if hasattr(before, 'top') and getattr(before, 'top', -1) >= 0 and wa.top < before.top:
                            changed = True
                            break
                        time.sleep(0.05)
                        if i == 15:
                            try:
                                _force_close_secondary_tickers_by_enum(exclude_hwnds=list(exclude))
                            except Exception:
                                pass
                except Exception:
                    pass

                if not changed and DEBUG_APPBAR:
                    colored_print(f"[APPBAR] Keeper removal: work area did not change after polling (may require further investigation)")

            except Exception:
                pass

        finally:
            # Clear removal-in-progress flag
            try:
                _keeper_removal_in_progress = False
            except Exception:
                pass

            # Trigger primaries to re-register AppBar
            try:
                app = QtWidgets.QApplication.instance()
                if app:
                    _force_close_secondary_tickers()
                    for w in app.topLevelWidgets():
                        try:
                            if hasattr(w, 'setup_appbar_and_position'):
                                try:
                                    w.setup_appbar_and_position()
                                except Exception:
                                    QtCore.QTimer.singleShot(150, (lambda ww=w: ww.setup_appbar_and_position()))
                                    QtCore.QTimer.singleShot(350, (lambda ww=w: ww.setup_appbar_and_position()))
                                else:
                                    QtCore.QTimer.singleShot(150, (lambda ww=w: ww.setup_appbar_and_position()))
                                    QtCore.QTimer.singleShot(350, (lambda ww=w: ww.setup_appbar_and_position()))
                        except Exception:
                            pass
            except Exception:
                pass



def reserve_combined_with_keeper(primary_hwnd, secondary_hwnd, screen_index=0):
    """
    Reserve combined AppBar height using an invisible ReservationKeeper window
    so that the reservation is owned by a separate HWND and won't be overwritten
    by the primary ticker instance re-registering itself.
    """
    global _reservation_keeper
    global _reservation_keeper, _keeper_creation_in_progress
    try:
        # If another keeper creation is already in progress, wait briefly
        wait_attempts = 0
        while _keeper_creation_in_progress and wait_attempts < 6:
            time.sleep(0.05)
            wait_attempts += 1
        # If still in progress, fall back to not attempting keeper creation
        if _keeper_creation_in_progress:
            colored_print(f"[SECOND TICKER] Keeper creation already in progress; skipping keeper attempt")
            return None
        user32 = ctypes.windll.user32
        rect1 = wintypes.RECT()
        rect2 = wintypes.RECT()
        user32.GetWindowRect(int(primary_hwnd), ctypes.byref(rect1))
        user32.GetWindowRect(int(secondary_hwnd), ctypes.byref(rect2))
        h1 = rect1.bottom - rect1.top
        h2 = rect2.bottom - rect2.top
        combined = h1 + h2
        colored_print(f"[SECOND TICKER] Keeper: registering combined AppBar height: {combined}px (h1={h1}, h2={h2})")

        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        if 0 <= screen_index < len(screens):
            screen = screens[screen_index]
        else:
            screen = app.primaryScreen()
        rect = screen.geometry()

        # Try to create a ReservationKeeper and verify Windows honored the reserved area
        max_attempts = 4
        last_top = None
        # Indicate keeper creation is in-flight so primaries defer their own registration
        _keeper_creation_in_progress = True
        for attempt in range(1, max_attempts + 1):
            try:
                if _reservation_keeper:
                    try:
                        _reservation_keeper.remove()
                    except Exception:
                        pass
                    _reservation_keeper = None

                keeper = ReservationKeeper(rect, combined)
                if not getattr(keeper, '_registered', False):
                    # Creation failed to register AppBar
                    keeper.remove()
                    time.sleep(0.06)
                    continue

                # Verify work area top
                work_area = wintypes.RECT()
                user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0)
                reserved = work_area.top - rect.top()
                colored_print(f"[SECOND TICKER] Keeper attempt {attempt}: work_area.top={work_area.top}, reserved={reserved}")
                if reserved >= combined:
                    colored_print(f"[SECOND TICKER] Keeper combined reservation succeeded on attempt {attempt}")
                    # Mark keeper as honored so removal will perform full cleanup
                    try:
                        keeper._honored = True
                    except Exception:
                        pass
                    _reservation_keeper = keeper
                    last_top = work_area.top
                    # finished - clear in-flight flag
                    _keeper_creation_in_progress = False
                    return last_top
                else:
                    # Not honored fully; destroy keeper and retry
                    keeper.remove()
                    _reservation_keeper = None
                    time.sleep(0.08 * attempt)
            except Exception as e:
                colored_print(f"[SECOND TICKER] Keeper error attempt {attempt}: {e}")
                time.sleep(0.08)
        colored_print(f"[SECOND TICKER] Keeper failed to reserve full combined height after {max_attempts} attempts")
        _keeper_creation_in_progress = False
        return None
    except Exception as e:
        colored_print(f"[SECOND TICKER] Keeper reservation failed: {e}")
        _keeper_creation_in_progress = False
        return None


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
    # Also remove reservation keeper if present
    global _reservation_keeper
    try:
        if _reservation_keeper:
            try:
                colored_print("[EMERGENCY] Global cleanup - removing reservation keeper AppBar")
                _reservation_keeper.remove()
            except Exception:
                pass
            _reservation_keeper = None
    except Exception:
        pass


def _force_close_secondary_tickers():
    """Force-close any ticker windows marked as secondary/second to ensure only primary remains."""
    try:
        app = QtWidgets.QApplication.instance()
        if not app:
            return
        for w in list(app.topLevelWidgets()):
            try:
                # Some windows may be marked with either flag name
                if getattr(w, 'is_secondary_ticker', False) or getattr(w, 'is_second_ticker', False):
                    try:
                        if sys.platform == 'win32':
                            try:
                                remove_appbar(int(w.winId()))
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        w.close()
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass


def _force_close_secondary_tickers_by_enum(exclude_hwnds=None, title_prefix="TCKR-"):
    """Enumerate top-level windows and attempt to close windows whose title starts with `title_prefix`.
    Excludes any HWNDs in `exclude_hwnds` (list of ints).
    Attempts to remove AppBar registration for those HWNDs, then sends WM_CLOSE with a timeout.
    """
    try:
        if sys.platform != 'win32':
            return
        user32 = ctypes.windll.user32

        # Prepare exclusion set
        excl = set()
        if exclude_hwnds:
            try:
                excl = set(int(h) for h in exclude_hwnds if h is not None)
            except Exception:
                excl = set()

        if DEBUG_APPBAR:
            colored_print(f"[APPBAR] Enumerating windows to force-close TCKR windows (exclude={excl})")

        ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        import re
        title_re = re.compile(r'^TCKR-\d+$')

        def _enum_proc(hwnd, lParam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True


                # Use module-level `_terminate_window_process(hwnd)` for process termination
                def _is_pid_running(pid):
                    """Return True if PID is running on Windows, False otherwise."""
                    try:
                        if sys.platform != 'win32':
                            # Fallback: on non-windows, try os.kill
                            try:
                                os.kill(pid, 0)
                                return True
                            except Exception:
                                return False
                        kernel32 = ctypes.windll.kernel32
                        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
                        if not h:
                            return False
                        try:
                            exit_code = wintypes.DWORD()
                            res = kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
                            if not res:
                                return False
                            # STILL_ACTIVE == 259
                            return int(exit_code.value) == 259
                        finally:
                            try:
                                kernel32.CloseHandle(h)
                            except Exception:
                                pass
                    except Exception:
                        return False


                def _wait_for_pid_exit(pid, timeout=30.0):
                    """Wait until `pid` is no longer running or timeout (seconds) expires. Returns True if exited."""
                    try:
                        start = time.time()
                        while time.time() - start < float(timeout):
                            if not _is_pid_running(pid):
                                return True
                            time.sleep(0.05)
                        return not _is_pid_running(pid)
                    except Exception:
                        return False
                length = user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if not title:
                    return True
                # Match strictly formatted TCKR window titles like 'TCKR-1', 'TCKR-2'
                if title_re.match(title):
                    hval = int(hwnd)
                    if hval in excl:
                        if DEBUG_APPBAR:
                            colored_print(f"[APPBAR] Skipping excluded HWND {hval} ({title})")
                        return True
                    # Try removing AppBar registration for this HWND first
                    try:
                        remove_appbar(hval)
                    except Exception:
                        pass
                    # Send WM_CLOSE with timeout
                    try:
                        WM_CLOSE = 0x0010
                        SMTO_ABORTIFHUNG = 0x0002
                        user32.SendMessageTimeoutW(hwnd, WM_CLOSE, 0, 0, SMTO_ABORTIFHUNG, 300, None)
                        if DEBUG_APPBAR:
                            colored_print(f"[APPBAR] Sent WM_CLOSE to HWND {hval} ({title})")
                    except Exception:
                        pass
            except Exception:
                pass
            return True

        user32.EnumWindows(ENUMPROC(_enum_proc), 0)
        if DEBUG_APPBAR:
            colored_print("[APPBAR] Enumeration forced-close pass complete")
    except Exception:
        pass


def _list_and_diagnose_tckr_windows(title_prefix="TCKR-"):
    """Enumerate top-level windows with titles starting with title_prefix and log diagnostics."""
    try:
        if sys.platform != 'win32':
            return []
        user32 = ctypes.windll.user32
        results = []

        ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        import re
        title_re = re.compile(r'^TCKR-\d+$')

        def _enum_proc(hwnd, lParam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if not title:
                    return True
                if title_re.match(title):
                    rect = wintypes.RECT()
                    try:
                        user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    except Exception:
                        rect.left = rect.top = rect.right = rect.bottom = -1
                    hval = int(hwnd)
                    results.append((hval, title, rect))
            except Exception:
                pass
            return True

        user32.EnumWindows(ENUMPROC(_enum_proc), 0)

        # Log diagnostics for each found window
        if results:
            colored_print(f"[APPBAR] Remaining TCKR windows ({len(results)}):")
            for hval, title, rect in results:
                try:
                    colored_print(f"  HWND={hval}, title='{title}', rect=({rect.left},{rect.top},{rect.right},{rect.bottom})")
                    # Use diagnose_appbar_state to print work-area/reservation info
                    try:
                        diagnose_appbar_state(hval, get_settings().get('ticker_height', 35))
                    except Exception:
                        pass
                except Exception:
                    pass
        return results
    except Exception:
        return []

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
    
    # Compute device pixel ratio and expected physical height for clearer diagnostics
    dpr = 1.0
    try:
        app = QtWidgets.QApplication.instance()
        if app:
            screen = app.primaryScreen()
            if screen and hasattr(screen, 'devicePixelRatioF'):
                dpr = float(screen.devicePixelRatioF())
            elif screen and hasattr(screen, 'devicePixelRatio'):
                try:
                    dpr = float(screen.devicePixelRatio())
                except Exception:
                    dpr = 1.0
    except Exception:
        dpr = 1.0

    expected_physical = int(expected_height * dpr) if expected_height is not None else None

    # Determine screen top to compute reserved amount relative to screen
    screen_top = 0
    try:
        app = QtWidgets.QApplication.instance()
        if app:
            screen = app.primaryScreen()
            if screen:
                screen_top = int(screen.geometry().top())
    except Exception:
        screen_top = 0

    reserved_amount = work_area.top - screen_top

    colored_print(f"[APPBAR DIAGNOSTICS]")
    print(f"  Window position: top={window_rect.top}, bottom={window_rect.bottom}, height={actual_height}")
    print(f"  Expected logical height: {expected_height}")
    print(f"  Expected physical (logical * DPR={dpr}): {expected_physical}")
    print(f"  Monitor type: {'Primary (x=0)' if is_primary_monitor else f'Secondary (x={window_rect.left})'}")
    print(f"  Work area: top={work_area.top}, left={work_area.left}, right={work_area.right}, bottom={work_area.bottom}")
    print(f"  Space reserved at top (relative to screen top {screen_top}): {reserved_amount} pixels")
    
    if is_primary_monitor:
        # Only check work area for primary monitor; compare physical values
        if expected_physical is not None:
            if reserved_amount < expected_physical:
                print(f"  ⚠️ WARNING: Work area reserved ({reserved_amount}) is less than expected physical height ({expected_physical})")
                print(f"     This means Windows did not reserve the full space for the AppBar")
                print(f"     Other windows may overlap the ticker bar")
            elif reserved_amount > expected_physical:
                print(f"  ℹ️ Work area reserved MORE space than requested ({reserved_amount} vs {expected_physical})")
            else:
                print(f"  ✓ Work area correctly reserved {expected_physical} pixels at top")
        else:
            # Fallback to legacy comparison when expected_physical is unavailable
            if reserved_amount < expected_height:
                print(f"  ⚠️ WARNING: Work area top ({work_area.top}) is less than expected height ({expected_height})")
            elif reserved_amount > expected_height:
                print(f"  ℹ️ Work area reserved MORE space than requested ({reserved_amount} vs {expected_height})")
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
        "led_bloom_intensity": 200,  # Bloom/glow effect intensity (0-200%) - DEFAULT 200% for striking visuals
        "led_ghosting_effect": True,  # Enable motion blur/trailing effect
        "led_icon_matrix": True,  # Apply LED matrix overlay to icons
        "led_glass_glare": True,  # Enable glass cover with reflections/glare
        "glass_opacity": 60,
        "glass_highlight_ratio": 0,
        "screen_index": 0,
        "force_pre_show_move_always": True,
        "debug_force_pre_show_move": True,
        "debug_pre_show_retry_count": 3,
        "debug_pre_show_backoff_ms": 100,
        "post_show_verify_attempts": 2,
        "post_show_backoff_ms": 100,
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
        "websocket_batch_interval": 150,  # Batch WebSocket updates every N milliseconds (reduces jitter)
        "websocket_min_update_interval": 100,  # Minimum milliseconds between updates per symbol
        "websocket_change_threshold": 0.001,  # Only update if price change > 0.1%
        # Debug: collect extra native visibility fields for deep diagnostics (low-volume)
        "debug_extra_visibility_fields": True,
        # Retry behavior for repair/repaint (low-volume, gated by flags)
        "debug_try_force_repaint_retries": True,
        "debug_repair_retry_count": 2,
        "debug_repaint_retry_count": 2,
        "debug_repair_backoff_ms": 150,
        # Massive monitor tracing to debug cross-screen positioning issues
        "debug_massive_monitor_trace": True,
        # Throttled incremental rebuilds: interval per tick (ms) and max symbols per tick
        "websocket_incremental_interval_ms": 30,  # Process a batch of symbol rebuilds every N ms
        "websocket_incremental_max_per_tick": 6,  # Max symbols rebuilt per timer tick
        "allow_forced_termination": False  # If True, last-resort will terminate foreign ticker processes that won't close
    }

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

def fetch_all_stock_prices_with_429(tickers, api_key, api_key_2=None):
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
        # Use cache if it's less than 60 seconds old
        if current_time - cached_time < 60:
            colored_print(f"[API CACHE] Using cached results for {len(tickers)} tickers (age: {current_time - cached_time:.1f}s)")
            return cached_prices, False
        else:
            colored_print(f"[API CACHE] Cache expired for {len(tickers)} tickers (age: {current_time - cached_time:.1f}s) - fetching fresh data")

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

    # Cache the results, but avoid caching a complete failure (all prices None)
    try:
        any_valid = any((p is not None and p[0] is not None) for p in prices.values())
    except Exception:
        any_valid = False

    if any_valid:
        fetch_all_stock_prices_with_429._cache[cache_key] = (current_time, prices.copy())
    else:
        # Don't cache an all-failed result; keep previous cache if present
        try:
            colored_print(f"[API CACHE] Not caching all-failed result for {len(tickers)} tickers")
        except Exception:
            pass

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
        # Allow many reconnect attempts to survive transient DNS/network outages
        self.max_reconnect_attempts = 1000000
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
                        # Use the centralized flush routine which retries on transient failures
                        sent = self._flush_queued_subscriptions()
                        # Add successfully-sent (approx) to subscribed_symbols if any were sent
                        # We conservatively add those that were attempted (queued minus remaining)
                        # Remaining entries are left in self.queued_subscriptions by the flusher
                        # so we can compute attempted as the difference from before/after
                        # (best-effort: if none left, assume all were sent)
                        # If queue was emptied by flush, add all finnhub symbols
                        if not self.queued_subscriptions:
                            finnhub_symbols = [s for s in list(self.subscribed_symbols) if not s.startswith('^')]
                        # No strict update here; the flusher will re-enqueue failures
                except Exception as e:
                    colored_print(f"[WEBSOCKET] ❌ Error flushing queued subscriptions: {e}")
                # Trigger a coordinated fetch now that websocket is connected so secondaries recover
                try:
                    from PyQt5 import QtCore
                    def _trigger_coordinated_fetch():
                        try:
                            if hasattr(self, 'window') and self.window:
                                tray = getattr(self.window, 'tray_icon', None)
                                target = tray.primary_ticker if (tray and getattr(tray, 'primary_ticker', None)) else self.window
                                if hasattr(target, 'update_prices_inplace'):
                                    colored_print(f"[WEBSOCKET] Triggering coordinated fetch on websocket open via target id={id(target)}")
                                    try:
                                        target.update_prices_inplace(force=True)
                                    except Exception as e:
                                        colored_print(f"[WEBSOCKET] Error calling update_prices_inplace: {e}")
                        except Exception as e:
                            colored_print(f"[WEBSOCKET] Error preparing coordinated fetch: {e}")
                    # Schedule slightly delayed to allow subscriptions to flush
                    try:
                        QtCore.QTimer.singleShot(250, _trigger_coordinated_fetch)
                    except Exception:
                        # Fallback: call directly
                        _trigger_coordinated_fetch()
                except Exception:
                    pass

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

            # Prevent multiple concurrent connection attempts
            if self.connection_thread and self.connection_thread.is_alive():
                colored_print("[WEBSOCKET] Connection already in progress")
                return True

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
        
        if symbols_to_process:
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
                            ticker.loading = False
                            try:
                                ticker.stale = False
                            except Exception:
                                pass
                            ticker.bloom_cache_valid = False
                            
                            # Log significant price changes
                            if old_price and abs(price - old_price) > 0.01:
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
        if updates_sent > 0 or symbols_skipped > 0:
            remaining = len(self.price_buffer)
            colored_print(f"[WEBSOCKET] 📈 Batch complete: {updates_sent} sent, {symbols_skipped} skipped | {remaining} remain | Total: {self.price_updates_processed} updates")
        
        return updates_sent, updated_symbols

    def _flush_queued_subscriptions(self, retry_delay=0.5, max_retries=6):
        """Attempt to send queued subscriptions, retrying a few times on transient errors."""
        if not self.queued_subscriptions:
            return 0

        finnhub_symbols = [s for s in list(self.queued_subscriptions) if not s.startswith('^')]
        if not finnhub_symbols:
            # Nothing to send
            self.queued_subscriptions.clear()
            return 0

        sent = 0
        remaining = []

        for sym in finnhub_symbols:
            try:
                # Double-check ws presence
                if not self.ws:
                    raise RuntimeError('no ws instance')
                self.ws.send(json.dumps({'type': 'subscribe', 'symbol': sym}))
                sent += 1
            except Exception as e:
                colored_print(f"[WEBSOCKET] ❌ Failed to send queued subscribe for {sym}: {e}")
                remaining.append(sym)

        # Update queued_subscriptions to only the ones that failed
        self.queued_subscriptions = set(remaining)

        colored_print(f"[WEBSOCKET] 📥 Flushed queued subscriptions: sent {sent}/{len(finnhub_symbols)} messages, {len(remaining)} remaining")

        # If there are remaining and we still have retries, schedule another attempt
        if remaining and max_retries > 0:
            def _retry():
                # Exponential backoff-ish
                try:
                    self._flush_queued_subscriptions(retry_delay=min(2.0, retry_delay * 1.5), max_retries=max_retries - 1)
                except Exception:
                    pass

            t = threading.Timer(retry_delay, _retry)
            t.daemon = True
            t.start()

        return sent

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ TCKR Settings")
        self.settings = get_settings()
        self.original_settings = self.settings.copy()
        
        # Apply modern theme
        apply_modern_theme(self)
        self.setMinimumWidth(520)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # === API KEYS GROUP ===
        api_group = QtWidgets.QGroupBox("🔑 API Keys")
        api_layout = QtWidgets.QFormLayout(api_group)
        api_layout.setSpacing(8)
        api_layout.setContentsMargins(12, 20, 12, 12)

        # Primary Key with eye icon
        primary_key_container = QtWidgets.QWidget()
        primary_key_layout = QtWidgets.QHBoxLayout(primary_key_container)
        primary_key_layout.setContentsMargins(0, 0, 0, 0)
        primary_key_layout.setSpacing(4)
        
        self.finnhub_api_key_edit = QtWidgets.QLineEdit(self.settings.get("finnhub_api_key", ""))
        self.finnhub_api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.finnhub_api_key_edit.setPlaceholderText("Primary Finnhub API key")
        
        self.primary_key_toggle = QtWidgets.QPushButton("👁")
        self.primary_key_toggle.setFixedSize(30, 26)
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
        
        primary_key_layout.addWidget(self.finnhub_api_key_edit)
        primary_key_layout.addWidget(self.primary_key_toggle)
        api_layout.addRow("Primary Key:", primary_key_container)

        # Secondary Key with eye icon
        secondary_key_container = QtWidgets.QWidget()
        secondary_key_layout = QtWidgets.QHBoxLayout(secondary_key_container)
        secondary_key_layout.setContentsMargins(0, 0, 0, 0)
        secondary_key_layout.setSpacing(4)
        
        self.finnhub_api_key_2_edit = QtWidgets.QLineEdit(self.settings.get("finnhub_api_key_2", ""))
        self.finnhub_api_key_2_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.finnhub_api_key_2_edit.setPlaceholderText("Optional - for load balancing")
        
        self.secondary_key_toggle = QtWidgets.QPushButton("👁")
        self.secondary_key_toggle.setFixedSize(30, 26)
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
        
        secondary_key_layout.addWidget(self.finnhub_api_key_2_edit)
        secondary_key_layout.addWidget(self.secondary_key_toggle)
        api_layout.addRow("Secondary Key:", secondary_key_container)
        
        # Update Interval and WebSocket Refresh on same row
        intervals_container = QtWidgets.QWidget()
        intervals_layout = QtWidgets.QHBoxLayout(intervals_container)
        intervals_layout.setContentsMargins(0, 0, 0, 0)
        intervals_layout.setSpacing(20)
        
        # Update Interval (API fetch)
        update_interval_widget = QtWidgets.QWidget()
        update_interval_layout = QtWidgets.QHBoxLayout(update_interval_widget)
        update_interval_layout.setContentsMargins(0, 0, 0, 0)
        update_interval_layout.setSpacing(4)
        update_interval_label = QtWidgets.QLabel("Update Interval:")
        self.update_interval_spin = QtWidgets.QSpinBox()
        self.update_interval_spin.setRange(10, 3600)
        self.update_interval_spin.setSuffix(" sec")
        self.update_interval_spin.setValue(self.settings.get("update_interval", 300))
        self.update_interval_spin.setToolTip("How often to fetch prices from API")
        update_interval_layout.addWidget(update_interval_label)
        update_interval_layout.addWidget(self.update_interval_spin)
        intervals_layout.addWidget(update_interval_widget)
        
        # WebSocket Visual Refresh
        ws_refresh_widget = QtWidgets.QWidget()
        ws_refresh_layout = QtWidgets.QHBoxLayout(ws_refresh_widget)
        ws_refresh_layout.setContentsMargins(0, 0, 0, 0)
        ws_refresh_layout.setSpacing(4)
        ws_refresh_label = QtWidgets.QLabel("WS Visual Refresh:")
        ws_refresh_label.setToolTip("How often to update display with WebSocket prices\n0 = Disabled (perfectly smooth, no stutter)\n15-30 = Periodic updates (causes brief stutter)")
        self.ws_refresh_spin = QtWidgets.QSpinBox()
        self.ws_refresh_spin.setRange(0, 60)
        self.ws_refresh_spin.setSuffix(" sec")
        self.ws_refresh_spin.setSpecialValueText("Off (smooth)")
        self.ws_refresh_spin.setValue(self.settings.get("websocket_visual_refresh_seconds", 0))
        self.ws_refresh_spin.setToolTip("0 = Smooth scrolling (no WS updates)\n15-30 = Periodic updates (brief stutter)")
        self.ws_refresh_spin.setMinimumWidth(140)  # Wider to show "Off (smooth)" text
        ws_refresh_layout.addWidget(ws_refresh_label)
        ws_refresh_layout.addWidget(self.ws_refresh_spin)
        intervals_layout.addWidget(ws_refresh_widget)
        
        # Left-justify instead of stretching
        api_layout.addRow("", intervals_container)
        
        layout.addWidget(api_group)
        
        # === APPEARANCE GROUP ===
        appearance_group = QtWidgets.QGroupBox("🎨 Appearance")
        appearance_layout = QtWidgets.QFormLayout(appearance_group)
        appearance_layout.setSpacing(8)
        appearance_layout.setContentsMargins(12, 20, 12, 12)
        # Left-align labels and fields so values are justified to the left
        appearance_layout.setLabelAlignment(QtCore.Qt.AlignLeft)
        appearance_layout.setFormAlignment(QtCore.Qt.AlignLeft)
        # Let the field column expand to fill empty space in the Appearance section
        try:
            appearance_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        except Exception:
            try:
                # Fallback: if enum name differs, set numeric value for ExpandingFieldsGrow (1)
                appearance_layout.setFieldGrowthPolicy(1)
            except Exception:
                pass
        
        self.scroll_speed_spin = QtWidgets.QSpinBox()
        self.scroll_speed_spin.setRange(1, 50)
        self.scroll_speed_spin.setSuffix(" px/frame")
        self.scroll_speed_spin.setValue(self.settings.get("speed", 2))
        try:
            self.scroll_speed_spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        except Exception:
            pass
        appearance_layout.addRow("Scroll Speed:", self.scroll_speed_spin)
        
        self.ticker_height_spin = QtWidgets.QSpinBox()
        self.ticker_height_spin.setRange(24, 200)
        self.ticker_height_spin.setSuffix(" px")
        self.ticker_height_spin.setValue(self.settings.get("ticker_height", 60))
        try:
            self.ticker_height_spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        except Exception:
            pass
        appearance_layout.addRow("Height:", self.ticker_height_spin)
        
        self.transparency_spin = QtWidgets.QSpinBox()
        self.transparency_spin.setRange(0, 100)
        self.transparency_spin.setSuffix(" %")
        self.transparency_spin.setValue(self.settings.get("transparency", 100))
        try:
            self.transparency_spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        except Exception:
            pass
        appearance_layout.addRow("Transparency:", self.transparency_spin)
        
        self.display_combo = QtWidgets.QComboBox()
        app = QtWidgets.QApplication.instance()
        screens = app.screens()
        for i, screen in enumerate(screens):
            geom = screen.geometry()
            self.display_combo.addItem(f"Display {i+1} ({geom.width()}×{geom.height()})")
        self.display_combo.setCurrentIndex(self.settings.get("screen_index", 0))
        try:
            self.display_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        except Exception:
            pass
        appearance_layout.addRow("Display:", self.display_combo)
        
        self.price_indicator_combo = QtWidgets.QComboBox()
        self.price_indicator_combo.addItem("Arrows - Thick", "arrows")
        self.price_indicator_combo.addItem("Arrows - Thin", "thin_arrows")
        self.price_indicator_combo.addItem("Triangles", "triangles")
        current_indicator = self.settings.get("price_indicator_style", "triangles")
        index = self.price_indicator_combo.findData(current_indicator)
        if index >= 0:
            self.price_indicator_combo.setCurrentIndex(index)
        try:
            self.price_indicator_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        except Exception:
            pass
        appearance_layout.addRow("Price Indicator:", self.price_indicator_combo)

        # Second ticker settings - combined row: checkbox + description at left, speed control to the right
        self.enable_second_ticker_checkbox = QtWidgets.QCheckBox("Enable Second Ticker")
        self.enable_second_ticker_checkbox.setChecked(self.settings.get("enable_second_ticker", False))

        self.second_ticker_speed_spin = QtWidgets.QSpinBox()
        self.second_ticker_speed_spin.setRange(1, 50)
        self.second_ticker_speed_spin.setSuffix(" px/frame")
        self.second_ticker_speed_spin.setValue(self.settings.get("second_ticker_speed", 2))
        self.second_ticker_speed_spin.setEnabled(self.settings.get("enable_second_ticker", False))
        try:
            self.second_ticker_speed_spin.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        except Exception:
            pass

        # Build a single row widget: left = checkbox + description, right = speed control
        second_row = QtWidgets.QWidget()
        second_row_layout = QtWidgets.QHBoxLayout(second_row)
        second_row_layout.setContentsMargins(0, 0, 0, 0)
        second_row_layout.setSpacing(8)

        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QHBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        left_layout.addWidget(self.enable_second_ticker_checkbox)
        # Provide description as a tooltip instead of static text
        self.enable_second_ticker_checkbox.setToolTip("Show a second ticker below the main one")

        # Right side: compact speed label + spin
        right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QHBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        speed_label = QtWidgets.QLabel("Second Ticker Speed:")
        right_layout.addWidget(speed_label)
        right_layout.addWidget(self.second_ticker_speed_spin)

        # Add left (label column) and right (field column) to the form layout so checkbox aligns under labels
        appearance_layout.addRow(left_container, right_container)

        self.second_ticker_stock_file_edit = QtWidgets.QLineEdit()
        self.second_ticker_stock_file_edit.setText(self.settings.get("second_ticker_stock_file", ""))
        self.second_ticker_stock_file_edit.setPlaceholderText("Leave empty to use same stocks as main ticker")
        self.second_ticker_stock_file_edit.setEnabled(self.settings.get("enable_second_ticker", False))

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

        appearance_layout.addRow("Second Ticker Stocks:", stock_file_container)

        # Connect checkbox to enable/disable controls
        self.enable_second_ticker_checkbox.stateChanged.connect(self.toggle_second_ticker_controls)

        layout.addWidget(appearance_group)
        
        # === VISUAL EFFECTS GROUP ===
        effects_group = QtWidgets.QGroupBox("✨ Visual Effects")
        effects_layout = QtWidgets.QVBoxLayout(effects_group)
        effects_layout.setSpacing(6)
        effects_layout.setContentsMargins(12, 20, 12, 12)

        # Bloom effect with intensity slider on same line
        bloom_layout = QtWidgets.QHBoxLayout()
        self.led_bloom_checkbox = QtWidgets.QCheckBox("LED Bloom/Glow Effect")
        self.led_bloom_checkbox.setChecked(self.settings.get("led_bloom_effect", True))
        bloom_layout.addWidget(self.led_bloom_checkbox)
        
        bloom_layout.addSpacing(10)
        intensity_label = QtWidgets.QLabel("Intensity:")
        intensity_label.setStyleSheet("color: #b0b0b0; font-size: 10px;")
        self.led_bloom_intensity_spin = QtWidgets.QSpinBox()
        self.led_bloom_intensity_spin.setRange(10, 300)
        self.led_bloom_intensity_spin.setSuffix("%")
        self.led_bloom_intensity_spin.setValue(self.settings.get("led_bloom_intensity", 100))
        self.led_bloom_intensity_spin.setToolTip("Adjust bloom/glow intensity\n50% = Subtle | 100% = Normal | 200%+ = Dramatic")
        self.led_bloom_intensity_spin.setMaximumWidth(80)
        bloom_layout.addWidget(intensity_label)
        bloom_layout.addWidget(self.led_bloom_intensity_spin)
        bloom_layout.addStretch()
        effects_layout.addLayout(bloom_layout)
        
        self.led_ghosting_checkbox = QtWidgets.QCheckBox("Motion Blur/Ghosting")
        self.led_ghosting_checkbox.setChecked(self.settings.get("led_ghosting_effect", True))
        effects_layout.addWidget(self.led_ghosting_checkbox)
        
        self.led_icon_matrix_checkbox = QtWidgets.QCheckBox("LED Icon Matrix Overlay")
        self.led_icon_matrix_checkbox.setChecked(self.settings.get("led_icon_matrix", True))
        effects_layout.addWidget(self.led_icon_matrix_checkbox)
        
        self.led_glass_glare_checkbox = QtWidgets.QCheckBox("Glass Cover with Glare")
        self.led_glass_glare_checkbox.setChecked(self.settings.get("led_glass_glare", True))
        effects_layout.addWidget(self.led_glass_glare_checkbox)

        self.global_text_glow_checkbox = QtWidgets.QCheckBox("Subtle Text Glow")
        self.global_text_glow_checkbox.setChecked(self.settings.get("global_text_glow", True))
        effects_layout.addWidget(self.global_text_glow_checkbox)
        
        layout.addWidget(effects_group)
        
        # === SOUND & NETWORK (Side by side) ===
        misc_layout = QtWidgets.QHBoxLayout()
        misc_layout.setSpacing(12)
        
        # Sound checkbox
        sound_group = QtWidgets.QGroupBox("🔊 Sound")
        sound_layout = QtWidgets.QVBoxLayout(sound_group)
        sound_layout.setContentsMargins(12, 20, 12, 12)
        self.play_sound_checkbox = QtWidgets.QCheckBox("Play on Update")
        self.play_sound_checkbox.setChecked(self.settings.get("play_sound_on_update", True))
        sound_layout.addWidget(self.play_sound_checkbox)
        misc_layout.addWidget(sound_group)
        
        # Network settings (compact)
        net_group = QtWidgets.QGroupBox("🌐 Network")
        net_layout = QtWidgets.QVBoxLayout(net_group)
        net_layout.setSpacing(6)
        net_layout.setContentsMargins(12, 20, 12, 12)
        
        self.use_proxy_checkbox = QtWidgets.QCheckBox("Use Proxy")
        self.use_proxy_checkbox.setChecked(bool(self.settings.get("use_proxy", False)))
        net_layout.addWidget(self.use_proxy_checkbox)
        
        self.proxy_edit = QtWidgets.QLineEdit(self.settings.get("proxy", ""))
        self.proxy_edit.setPlaceholderText("http://proxy:port")
        self.proxy_edit.setEnabled(self.use_proxy_checkbox.isChecked())
        self.use_proxy_checkbox.toggled.connect(self.proxy_edit.setEnabled)
        net_layout.addWidget(self.proxy_edit)
        
        self.use_cert_checkbox = QtWidgets.QCheckBox("Use Certificate")
        self.use_cert_checkbox.setChecked(bool(self.settings.get("use_cert", False)))
        net_layout.addWidget(self.use_cert_checkbox)
        
        cert_layout = QtWidgets.QHBoxLayout()
        self.cert_file_edit = QtWidgets.QLineEdit(self.settings.get("cert_file", ""))
        self.cert_file_edit.setPlaceholderText("certificate.pem")
        self.cert_file_edit.setEnabled(self.use_cert_checkbox.isChecked())
        self.cert_file_btn = QtWidgets.QPushButton("📁")
        self.cert_file_btn.setFixedWidth(32)
        self.cert_file_btn.setEnabled(self.use_cert_checkbox.isChecked())
        self.cert_file_btn.clicked.connect(self.browse_cert_file)
        self.use_cert_checkbox.toggled.connect(self.cert_file_edit.setEnabled)
        self.use_cert_checkbox.toggled.connect(self.cert_file_btn.setEnabled)
        cert_layout.addWidget(self.cert_file_edit)
        cert_layout.addWidget(self.cert_file_btn)
        net_layout.addLayout(cert_layout)
        
        misc_layout.addWidget(net_group)
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
            self.original_settings.get("second_ticker_speed") != s["second_ticker_speed"] or
            self.original_settings.get("second_ticker_stock_file") != s["second_ticker_stock_file"]
        )
        
        app = QtWidgets.QApplication.instance()
        primary_ticker_widget = None
        for widget in app.topLevelWidgets():
            if isinstance(widget, TickerWindow):
                # Remember first found ticker as primary candidate for restart actions
                if primary_ticker_widget is None:
                    primary_ticker_widget = widget
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
                    
                    # Check if any visual effects changed
                    visual_effects_changed = (
                        self.original_settings.get("led_bloom_effect") != s["led_bloom_effect"] or
                        self.original_settings.get("led_bloom_intensity") != s["led_bloom_intensity"] or
                        self.original_settings.get("led_ghosting_effect") != s["led_ghosting_effect"] or
                        self.original_settings.get("led_icon_matrix") != s["led_icon_matrix"] or
                        self.original_settings.get("led_glass_glare") != s["led_glass_glare"] or
                        self.original_settings.get("global_text_glow") != s["global_text_glow"] or
                        self.original_settings.get("price_indicator_style") != s["price_indicator_style"]
                    )
                    
                    if visual_effects_changed:
                        # Instantly apply visual effect changes by invalidating cache and triggering repaint
                        if hasattr(widget, '_cached_effect_settings'):
                            delattr(widget, '_cached_effect_settings')
                        if hasattr(widget, '_settings_cache_time'):
                            widget._settings_cache_time = 0
                        if hasattr(widget, '_cached_settings'):
                            widget._cached_settings = s.copy()
                        
                        # Rebuild ticker text if global_text_glow changed (affects text rendering)
                        if self.original_settings.get("global_text_glow") != s["global_text_glow"]:
                            widget.build_ticker_text(reset_scroll=False)
                        
                        # Rebuild ticker pixmaps if price indicator style changed
                        if self.original_settings.get("price_indicator_style") != s["price_indicator_style"]:
                            widget.build_ticker_pixmaps()
                        
                        # Force immediate repaint to show new visual effects
                        widget.gl_widget.update()
                        print("[SETTINGS] Visual effects applied instantly")
        
        # Update original_settings to current values for next apply
        self.original_settings = s.copy()
        
        # Set flag to indicate if restart is needed
        if not hasattr(self, 'needs_restart'):
            self.needs_restart = False
        # If a major change was detected and we have a ticker/tray, trigger an immediate restart
        if getattr(self, 'needs_restart', False) and primary_ticker_widget and hasattr(primary_ticker_widget, 'tray_icon'):
            try:
                tray = primary_ticker_widget.tray_icon
                old_window = primary_ticker_widget
                # Perform the same restart workflow used by TrayIcon.show_settings
                if sys.platform == "win32":
                    old_window.hide()
                    remove_appbar(int(old_window.winId()))
                    QtCore.QTimer.singleShot(300, lambda: tray._create_new_window_after_cleanup(old_window))
                else:
                    old_window.close()
                    QtCore.QTimer.singleShot(0, tray._create_new_window_immediately)
                colored_print("[SETTINGS] Major changes applied - restarting tickers to apply new configuration")
            except Exception as e:
                colored_print(f"[SETTINGS] Failed to trigger automatic restart: {e}")

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

        # Record first paint asynchronously to avoid blocking paint path
        try:
            if not getattr(self, '_first_paint_reported', False):
                try:
                    QtCore.QTimer.singleShot(0, lambda s=self: s._record_first_paint())
                except Exception:
                    try:
                        self._record_first_paint()
                    except Exception:
                        pass
        except Exception:
            pass

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
            
    def _record_first_paint(self):
        try:
            if getattr(self, '_first_paint_reported', False):
                return
            self._first_paint_reported = True
            try:
                _trace_ticker_state_event(self, 'first_paint')
            except Exception:
                pass
            if DEBUG_APPBAR:
                colored_print(f"[PAINT] First paint reported for instance id={id(self)} title={getattr(self, 'windowTitle', lambda:None)() if hasattr(self, 'windowTitle') else None}")
        except Exception:
            pass

    def _check_first_paint_after_load(self):
        try:
            if getattr(self, '_first_paint_reported', False):
                return
            try:
                _trace_ticker_state_event(self, 'first_paint_missing_before_repaint')
            except Exception:
                pass
            try:
                hwnd = int(self.winId())
                colored_print(f"[WATCHDOG] First paint missing, forcing native repaint for hwnd={hwnd}")
                _force_repaint_hwnd(hwnd)
            except Exception:
                pass
            # Re-check after forcing native repaint
            try:
                QtCore.QTimer.singleShot(250, lambda s=self: s._post_repaint_check())
            except Exception:
                try:
                    self._post_repaint_check()
                except Exception:
                    pass
        except Exception:
            pass

    def _post_repaint_check(self):
        try:
            if getattr(self, '_first_paint_reported', False):
                return
            try:
                _trace_ticker_state_event(self, 'first_paint_missing_after_repaint')
            except Exception:
                pass
            try:
                # Try Qt-level forced update
                self.update()
                self.repaint()
            except Exception:
                pass

            # If still no first paint after Qt repaint, escalate: hide/show, SetWindowPos nudge, redraw, and as last resort recreate GL widget
            try:
                if not getattr(self, '_first_paint_reported', False):
                    hwnd = None
                    try:
                        hwnd = int(self.winId())
                    except Exception:
                        hwnd = None
                    if hwnd:
                        user32 = ctypes.windll.user32
                        SW_HIDE = 0
                        SW_SHOW = 5
                        colored_print(f"[WATCHDOG] Escalation: hide/show for hwnd={hwnd}")
                        try:
                            user32.ShowWindow(hwnd, SW_HIDE)
                            time.sleep(0.05)
                            user32.ShowWindow(hwnd, SW_SHOW)
                            time.sleep(0.05)
                        except Exception:
                            pass
                        # Nudge position to target screen again
                        try:
                            sc = QtGui.QGuiApplication.screens()[get_settings().get('screen_index', 0)]
                            target_x = sc.geometry().left()
                            target_y = getattr(self, 'target_position_y', sc.geometry().top())
                            user32.SetWindowPos(hwnd, 0, int(target_x), int(target_y), 0, 0, 0x0004 | 0x0001 | 0x0040)
                        except Exception:
                            pass
                        # Redraw
                        try:
                            RDW_INVALIDATE = 0x0001
                            RDW_UPDATENOW = 0x0100
                            user32.RedrawWindow(hwnd, None, None, RDW_INVALIDATE | RDW_UPDATENOW)
                        except Exception:
                            pass
                        # Trace escalation attempt
                        _trace_repair_attempt_event(hwnd, f"LOADWATCH-{getattr(self, 'windowTitle', lambda:None)() if hasattr(self, 'windowTitle') else 'unknown'}", 1, False, last_error=ctypes.get_last_error(), screen_index=get_settings().get('screen_index', None))

                    # If still missing after native nudge, attempt re-creating GL widget
                    time.sleep(0.15)
                    if not getattr(self, '_first_paint_reported', False):
                        try:
                            colored_print(f"[WATCHDOG] Recreating GL widget for instance id={id(self)}")
                            try:
                                self.gl_widget.hide()
                                self.gl_widget.deleteLater()
                            except Exception:
                                pass
                            self.gl_widget = TickerGLWidget(self)
                            self.gl_widget.setGeometry(0, 0, self.width(), self.ticker_height)
                            self.gl_widget.show()
                            QtWidgets.QApplication.processEvents()
                            self.update(); self.repaint()
                            _trace_ticker_state_event(self, 'first_paint_forced_reinit')
                        except Exception as e:
                            colored_print(f"[WATCHDOG] GL widget reinit failed: {e}")
            except Exception:
                pass

            # If still no first paint after Qt repaint, escalate: hide/show, SetWindowPos nudge, redraw, and as last resort recreate GL widget
            try:
                if not getattr(self, '_first_paint_reported', False):
                    hwnd = None
                    try:
                        hwnd = int(self.winId())
                    except Exception:
                        hwnd = None
                    if hwnd:
                        user32 = ctypes.windll.user32
                        SW_HIDE = 0
                        SW_SHOW = 5
                        colored_print(f"[WATCHDOG] Escalation: hide/show for hwnd={hwnd}")
                        try:
                            user32.ShowWindow(hwnd, SW_HIDE)
                            time.sleep(0.05)
                            user32.ShowWindow(hwnd, SW_SHOW)
                            time.sleep(0.05)
                        except Exception:
                            pass
                        # Nudge position to target screen again
                        try:
                            sc = QtGui.QGuiApplication.screens()[get_settings().get('screen_index', 0)]
                            target_x = sc.geometry().left()
                            target_y = getattr(self, 'target_position_y', sc.geometry().top())
                            user32.SetWindowPos(hwnd, 0, int(target_x), int(target_y), 0, 0, 0x0004 | 0x0001 | 0x0040)
                        except Exception:
                            pass
                        # Redraw
                        try:
                            RDW_INVALIDATE = 0x0001
                            RDW_UPDATENOW = 0x0100
                            user32.RedrawWindow(hwnd, None, None, RDW_INVALIDATE | RDW_UPDATENOW)
                        except Exception:
                            pass
                        # Trace escalation attempt
                        _trace_repair_attempt_event(hwnd, f"LOADWATCH-{getattr(self, 'windowTitle', lambda:None)() if hasattr(self, 'windowTitle') else 'unknown'}", 1, False, last_error=ctypes.get_last_error(), screen_index=get_settings().get('screen_index', None))

                    # If still missing after native nudge, attempt re-creating GL widget
                    time.sleep(0.15)
                    if not getattr(self, '_first_paint_reported', False):
                        try:
                            colored_print(f"[WATCHDOG] Recreating GL widget for instance id={id(self)}")
                            try:
                                self.gl_widget.hide()
                                self.gl_widget.deleteLater()
                            except Exception:
                                pass
                            self.gl_widget = TickerGLWidget(self)
                            self.gl_widget.setGeometry(0, 0, self.width(), self.ticker_height)
                            self.gl_widget.show()
                            QtWidgets.QApplication.processEvents()
                            self.update(); self.repaint()
                            _trace_ticker_state_event(self, 'first_paint_forced_reinit')
                        except Exception as e:
                            colored_print(f"[WATCHDOG] GL widget reinit failed: {e}")
            except Exception:
                pass
        except Exception:
            pass

    def mousePressEvent(self, event):
        self.ticker_window.ticker_mousePressEvent(event)
    def enterEvent(self, event):
        this = self
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

    def broadcast_prices(self, prices, now=None):
        """Broadcast fetched prices to all managed ticker windows and rebuild their displays."""
        if now is None:
            now = time.time()
        try:
            print(f"[BROADCAST.RUN] Invoked on tray_icon id={id(self)} ticker_count={len(self.ticker_windows)}")
        except Exception:
            pass
        try:
            tickers = list(self.ticker_windows)
            # Diagnostic: print each ticker identity and basic state
            # If incoming fetch contains no valid prices, skip overwriting existing prices
            try:
                valid_count = sum(1 for v in (prices or {}).values() if (v is not None and getattr(v, '__len__', lambda: 0)() and v[0] is not None))
            except Exception:
                valid_count = 0
            if valid_count == 0:
                try:
                    print(f"[BROADCAST.SKIP] Incoming prices contain 0 valid entries — skipping overwrite to preserve existing prices")
                except Exception:
                    pass

                # Ensure tickers don't remain stuck on loading if fetch failed
                # We do NOT overwrite prices here; just clear loading and rebuild so UI updates
                for ticker in tickers:
                    def _clear_loading(t=ticker):
                        try:
                            if getattr(t, 'loading', False):
                                # Increment failure counter and mark stale only if thresholds reached
                                try:
                                    t.consecutive_failed_fetches = getattr(t, 'consecutive_failed_fetches', 0) + 1
                                except Exception:
                                    t.consecutive_failed_fetches = 1
                                last_s = getattr(t, 'last_successful_fetch_ts', getattr(t, 'last_api_update_time', 0)) or 0
                                elapsed_t = time.time() - last_s if last_s else float('inf')
                                if t.consecutive_failed_fetches >= 3 or elapsed_t >= 300:
                                    try:
                                        t.stale = True
                                    except Exception:
                                        pass
                                t.loading = False
                                t.bloom_cache_valid = False
                                t.build_ticker_text(reset_scroll=False)
                                try:
                                    print(f"[BROADCAST.SKIP.CLEAR] Cleared loading for {t.windowTitle() if hasattr(t, 'windowTitle') else repr(t)} (stale={getattr(t,'stale',False)})")
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    try:
                        QtCore.QTimer.singleShot(0, _clear_loading)
                    except Exception:
                        try:
                            _clear_loading()
                        except Exception:
                            pass

                return

            for ticker in tickers:
                try:
                    title = ticker.windowTitle() if hasattr(ticker, 'windowTitle') else repr(ticker)
                    stocks_len = len(getattr(ticker, 'stocks', []))
                    none_count = sum(1 for v in prices.values() if (v is None or (isinstance(v, tuple) and v[0] is None)))
                    print(f"[BROADCAST] Target ticker={title} id={id(ticker)} stocks={stocks_len} all_none_count={none_count}")
                except Exception:
                    pass

            # Schedule UI updates on the main event loop to be safe
            for ticker in tickers:
                def _apply(t=ticker):
                    try:
                        t.stocks = [s[0] for s in load_stocks()]
                        # Prefer copying the primary ticker's prices exactly when available
                        src = None
                        try:
                            src = getattr(self, 'primary_ticker', None)
                        except Exception:
                            src = None

                        if src and getattr(src, 'prices', None):
                            try:
                                # Deep-copy to avoid shared mutable state
                                t.prices = {k: (float(v[0]) if v and v[0] is not None else None, float(v[1]) if v and len(v) > 1 and v[1] is not None else None) for k, v in src.prices.items()}
                            except Exception:
                                t.prices = src.prices.copy()
                            try:
                                # Propagate stale flag from primary to secondary
                                t.stale = bool(getattr(src, 'stale', False))
                            except Exception:
                                pass
                        else:
                            # Normalize incoming prices
                            norm = {}
                            # Capture any existing prev_close values to avoid losing them
                            existing_prev = getattr(t, 'prices', {}) if getattr(t, 'prices', None) else {}
                            for k, v in (prices or {}).items():
                                try:
                                    if v is None:
                                        norm[k] = (None, None)
                                    elif isinstance(v, (list, tuple)):
                                        p = v[0] if len(v) > 0 else None
                                        pc = v[1] if len(v) > 1 else None
                                        try:
                                            p = float(p) if p is not None else None
                                        except Exception:
                                            p = None
                                        try:
                                            pc = float(pc) if pc is not None else None
                                        except Exception:
                                            pc = None

                                        # If incoming prev_close missing, preserve existing prev_close when available
                                        if (pc is None or pc == 0) and existing_prev:
                                            try:
                                                old_pc = existing_prev.get(k, (None, None))[1]
                                                if old_pc is not None:
                                                    pc = float(old_pc)
                                            except Exception:
                                                pass

                                        norm[k] = (p, pc)
                                    else:
                                        norm[k] = (None, None)
                                except Exception:
                                    norm[k] = (None, None)
                            t.prices = norm
                            try:
                                t.stale = False
                            except Exception:
                                pass

                        t.loading = False
                        t.bloom_cache_valid = False
                        t.last_api_update_time = now
                        # Preserve scroll position so ticker speed remains consistent
                        t.build_ticker_text(reset_scroll=False)
                        try:
                            # Diagnostic: report a sample symbol's prices and whether stock_data exists
                            try:
                                ticker_title = t.windowTitle() if hasattr(t, 'windowTitle') else repr(t)
                            except Exception:
                                ticker_title = repr(t)
                            sample_symbol = None
                            if getattr(t, 'stocks', None):
                                sample_symbol = t.stocks[0] if t.stocks else None
                            else:
                                sample_symbol = next(iter(getattr(t, 'prices', {}) or {}), None)
                            sample_prices = None
                            try:
                                sample_prices = t.prices.get(sample_symbol) if (hasattr(t, 'prices') and sample_symbol) else None
                            except Exception:
                                sample_prices = None
                            stock_data_present = bool(getattr(t, 'stock_data', None))
                            print(f"[BROADCAST.DIAG] ticker={ticker_title} sample_symbol={sample_symbol} sample_prices={sample_prices} stock_data_present={stock_data_present}")
                        except Exception:
                            pass
                    except Exception:
                        pass

                try:
                    QtCore.QTimer.singleShot(0, _apply)
                except Exception:
                    # Fallback: call directly
                    try:
                        _apply()
                    except Exception:
                        pass

            try:
                print(f"[BROADCAST] Scheduled update for {len(tickers)} tickers with {len(prices)} prices")
            except Exception:
                pass
        except Exception:
            pass

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
        dlg = SettingsDialog()
        if dlg.exec_():
            # Only restart ticker if major changes were made
            if getattr(dlg, 'needs_restart', False):
                old_window = self.primary_ticker
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
        """Spawn a new process to take over without overlapping AppBar registration.

        This starts a fresh process with `--handoff=<oldpid>` and exits the current process
        after ensuring the old window is closed and its AppBar removed. The new process
        will wait for the old PID to exit before registering AppBar, guaranteeing zero overlap.
        """
        try:
            old_window.close()
        except Exception:
            pass

        try:
            global _restart_in_progress
            if _restart_in_progress:
                # Another restart is in-flight; avoid spawning duplicates
                try:
                    colored_print("[RESTART] Restart already in progress; skipping duplicate spawn")
                except Exception:
                    pass
                return
            _restart_in_progress = True

            old_pid = os.getpid()
            # Build command to spawn new instance in handoff mode
            if getattr(sys, 'frozen', False) or hasattr(sys, '_MEIPASS'):
                # Running as frozen exe - restart the executable
                cmd = [sys.executable, f"--handoff={old_pid}"]
            else:
                # Regular python - run the script file
                cmd = [sys.executable, os.path.abspath(__file__), f"--handoff={old_pid}"]

            try:
                colored_print(f"[RESTART] Spawning new process for zero-overlap handoff: {cmd}")
            except Exception:
                pass

            # Start detached child process
            try:
                # Use detached creation flags to avoid inheriting the console/IDE handles
                creation = 0
                try:
                    creation = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                except Exception:
                    # Fallback numeric flags (DETACHED_PROCESS = 0x8, CREATE_NEW_PROCESS_GROUP = 0x200)
                    creation = 0x8 | 0x200

                # Spawn detached and don't inherit file descriptors
                subprocess.Popen(cmd, creationflags=creation, close_fds=True)

                # Create sentinel file to signal child that parent completed cleanup
                try:
                    # Ensure APPDATA_DIR exists
                    try:
                        os.makedirs(APPDATA_DIR, exist_ok=True)
                    except Exception:
                        pass
                    sentinel_path = os.path.join(APPDATA_DIR, f"handoff_{old_pid}.ready")
                    # Attempt to remove any stale sentinel first
                    try:
                        if os.path.exists(sentinel_path):
                            os.remove(sentinel_path)
                    except Exception:
                        pass
                    # Double-check AppBar removed for the old window before signaling
                    try:
                        if sys.platform == 'win32' and hasattr(old_window, 'winId'):
                            try:
                                remove_appbar(int(old_window.winId()))
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # Write sentinel file atomically
                    try:
                        with open(sentinel_path, 'w') as sf:
                            sf.write(f"pid={old_pid}\nready_at={time.time()}\n")
                        colored_print(f"[RESTART] Wrote handoff sentinel: {sentinel_path}")
                    except Exception as e:
                        try:
                            colored_print(f"[RESTART] Failed to write sentinel {sentinel_path}: {e}")
                        except Exception:
                            pass
                except Exception:
                    pass
            except Exception as e:
                try:
                    colored_print(f"[RESTART] Failed to spawn new process: {e}")
                except Exception:
                    pass

        except Exception:
            pass

        # Quit current application now that we've spawned the new process
        try:
            app = QtWidgets.QApplication.instance()
            if app:
                QtCore.QTimer.singleShot(100, app.quit)
            else:
                sys.exit(0)
        except Exception:
            try:
                sys.exit(0)
            except Exception:
                os._exit(0)

    def _create_new_window_immediately(self):
        """Create and configure the new ticker window"""
        settings = get_settings()
        new_window = TickerWindow()
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
                # Use global helper to force-close any secondary ticker windows
                _force_close_secondary_tickers()
                # Also ensure our internal list is cleaned up
                try:
                    for window in windows_to_close:
                        try:
                            self.remove_ticker_window(window)
                        except Exception:
                            pass
                except Exception:
                    pass

                # Remove reservation keeper (if present) so Windows work area is restored promptly
                try:
                    global _reservation_keeper
                    if _reservation_keeper:
                        try:
                            colored_print("[RESTART] Removing reservation keeper since second ticker disabled")
                            _reservation_keeper.remove()
                        except Exception:
                            pass
                        _reservation_keeper = None
                except Exception:
                    pass

                # After removing second ticker(s) and keeper, ensure primary re-registers AppBar for single height
                try:
                    if hasattr(self, 'primary_ticker') and self.primary_ticker:
                        QtCore.QTimer.singleShot(200, lambda: self.primary_ticker.setup_appbar_and_position())
                except Exception:
                    pass
            # If second ticker should remain enabled, keep the existing windows
            return

        # If we don't have multiple windows but second ticker should be enabled
        if enable_second_ticker and current_window_count == 1:
            print("[RESTART] Enabling second ticker - creating new second window")
            try:
                # Before creating a second ticker, remove primary's current AppBar
                try:
                    if hasattr(self, 'primary_ticker') and self.primary_ticker and sys.platform == "win32":
                        try:
                            remove_appbar(int(self.primary_ticker.winId()))
                        except Exception:
                            pass
                except Exception:
                    pass

                # Create second ticker window
                second_ticker_window = TickerWindow()
                # Mark as second/secondary ticker using both flag names for compatibility
                second_ticker_window.is_second_ticker = True
                second_ticker_window.is_secondary_ticker = True

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

                # Register the new window and show it
                self.add_ticker_window(second_ticker_window)
                second_ticker_window.show()

                # Diagnostic: log second ticker geometry and HWND for multi-screen troubleshooting
                try:
                    hwnd_val = int(second_ticker_window.winId())
                    geom = second_ticker_window.geometry()
                    screen_index = settings.get("screen_index", 0)
                    colored_print(f"[RESTART] Second ticker shown: HWND={hwnd_val}, geom=(x={geom.x()}, y={geom.y()}, w={geom.width()}, h={geom.height()}), screen_index={screen_index}")
                except Exception:
                    pass

                # Attempt to reserve the combined AppBar height immediately using the keeper
                # This reduces races where the primary re-registers and overwrites the combined reservation
                try:
                    # Ensure native window state is processed before attempting reservation
                    QtWidgets.QApplication.processEvents()
                    time.sleep(0.12)
                    QtWidgets.QApplication.processEvents()

                    if hasattr(self, 'primary_ticker') and self.primary_ticker and sys.platform == 'win32':
                        try:
                            primary_hwnd = int(self.primary_ticker.winId())
                            secondary_hwnd = int(second_ticker_window.winId())
                            screen_index = settings.get("screen_index", 0)
                            colored_print(f"[RESTART] Reserving combined AppBar for primary={primary_hwnd} secondary={secondary_hwnd}")
                            try:
                                app = QtWidgets.QApplication.instance()
                                screen = app.screens()[screen_index] if app and 0 <= screen_index < len(app.screens()) else app.primaryScreen()
                                # Only attempt keeper/combined AppBar reservation on the primary screen
                                if screen == app.primaryScreen():
                                    reserved_top = reserve_combined_with_keeper(primary_hwnd, secondary_hwnd, screen_index)
                                    if reserved_top is not None:
                                        # Keeper holds the reservation; ensure primary is positioned inside it
                                        QtCore.QTimer.singleShot(100, lambda: self.primary_ticker.ensure_top_position())
                                    else:
                                        # Fallback: schedule the existing registration flow
                                        QtCore.QTimer.singleShot(250, lambda: self.primary_ticker.setup_appbar_and_position())
                                else:
                                    colored_print(f"[SECOND TICKER] Target screen is not primary - skipping keeper combined reservation")
                                    # Still ensure both tickers are topmost and positioned
                                    QtCore.QTimer.singleShot(100, lambda: self.primary_ticker.ensure_top_position())
                                    QtCore.QTimer.singleShot(100, lambda: second_ticker_window.ensure_top_position())
                            except Exception:
                                QtCore.QTimer.singleShot(250, lambda: self.primary_ticker.setup_appbar_and_position())
                        except Exception:
                            QtCore.QTimer.singleShot(250, lambda: self.primary_ticker.setup_appbar_and_position())
                    else:
                        # Non-Windows or missing primary ticker: fall back to scheduled registration
                        if hasattr(self, 'primary_ticker') and self.primary_ticker:
                            QtCore.QTimer.singleShot(250, lambda: self.primary_ticker.setup_appbar_and_position())
                except Exception:
                    pass

                print("[RESTART] Second ticker created and shown successfully")

            except Exception as e:
                print(f"[RESTART] Failed to create second ticker: {e}")

    def show_manage_stocks(self):
        dlg = ManageStocksDialog(self.primary_ticker)
        if dlg.exec_():
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

    def show_about(self):
        # Modern About dialog
        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("ℹ️ About TCKR")
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
        version = QtWidgets.QLabel("Version 1.0.2026.0119.1810")
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
        
        dialog.exec_()

    def safe_exit(self):
        """Safely exit the application with proper AppBar cleanup"""
        print("[EXIT] Safe exit initiated - cleaning up AppBar registration")

        # Close all ticker windows to trigger AppBar cleanup
        windows_closed = 0
        for ticker in self.ticker_windows:
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
            # Open the primary ticker if present, otherwise the first managed ticker
            target = None
            try:
                target = getattr(self, 'primary_ticker', None)
            except Exception:
                target = None

            if not target:
                try:
                    tws = getattr(self, 'ticker_windows', [])
                    if tws:
                        target = tws[0]
                except Exception:
                    target = None

            if target:
                try:
                    target.showNormal()
                    target.raise_()
                    target.activateWindow()
                except Exception:
                    pass

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

    def __init__(self, is_secondary=False):
        super().__init__()
        
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

        # Startup diagnostics: print visibility trace path and per-screen AppBar cache once
        try:
            if self.instance_id == 1:
                try:
                    base_dir = os.path.dirname(__file__) or os.getcwd()
                except Exception:
                    base_dir = os.getcwd()
                trace_path = os.path.join(base_dir, 'tckr_visibility.log')
                colored_print(f"[TRACE] Visibility trace file: {trace_path}")
                try:
                    # Print current per-screen AppBar cache
                    colored_print(f"[APPBAR CACHE] {_appbar_supported}")
                except Exception:
                    colored_print(f"[APPBAR CACHE] <unavailable>")
        except Exception:
            pass
        
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
        # Staleness tracking: count consecutive failed fetch cycles and remember
        # timestamp of last successful update. Policy: mark `stale` after
        # `consecutive_failed_fetches >= 3` OR `now - last_successful_fetch_ts >= 300`.
        self.consecutive_failed_fetches = 0
        self.last_successful_fetch_ts = time.time()
        self.stale = False
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
                self._websocket_batch_size = 999  # Process all at once
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
        
        # Step 2: Process ALL buffered updates at once (only happens every 15s)
        batch_size = getattr(self, '_websocket_batch_size', 999)
        
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
                
                # Log every refresh to track updates
                colored_print(f"[WEBSOCKET] 🎨 Visual refresh #{self._websocket_refresh_count}: updated {updates_sent} symbols (batched for smoothness)")
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

        # Diagnostic overlay for debugging multi-monitor/AppBar issues
        # This overlay is temporary and can be toggled via settings 'show_diagnostic_overlay'
        # Default enabled for debugging purposes
        self.show_diagnostic_overlay = settings.get('show_diagnostic_overlay', True)
        if self.show_diagnostic_overlay:
            try:
                self._init_diagnostic_overlay()
            except Exception as e:
                colored_print(f"[DEBUG] Could not initialize diagnostic overlay: {e}")
        
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
            
            # Small delay and event processing to let any existing tickers fully initialize
            import time
            QtWidgets.QApplication.processEvents()
            # Increase delay slightly to let Qt and the windowing system settle and attach a windowHandle
            time.sleep(0.30)
            QtWidgets.QApplication.processEvents()

            # Try to explicitly assign our QWindow to the target screen to avoid being created on the primary
            try:
                wh = self.windowHandle()
                if wh is not None:
                    try:
                        wh.setScreen(screen)
                        if DEBUG_APPBAR: print(f"[INIT] Assigned windowHandle to screen {screen.name() if screen else 'None'}")
                    except Exception:
                        pass
                else:
                    if DEBUG_APPBAR: print("[INIT] windowHandle not available yet; will retry screen assignment after show")
            except Exception:
                pass

            # Now check for other tickers (after native window move/geometry propagated)
            self.check_for_other_tickers_early()
            
            # If we detected we're secondary, position ourselves correctly BEFORE showing
            if hasattr(self, 'is_secondary_ticker') and self.is_secondary_ticker and hasattr(self, 'target_position_y'):
                print(f"[INIT] Detected as secondary ticker - positioning at y={self.target_position_y} before show")
                self.setGeometry(rect.left(), self.target_position_y, rect.width(), self.ticker_height)
            
            # Optional: force native pre-show move to target screen and verify monitor mapping (debug-flagged)
            try:
                if get_settings().get('force_pre_show_move_always', False) or get_settings().get('debug_force_pre_show_move', False):
                    user32 = ctypes.windll.user32
                    SWP_NOSIZE = 0x0001
                    SWP_NOZORDER = 0x0004
                    SWP_SHOWWINDOW = 0x0040
                    # Determine target coords
                    try:
                        sc_geom = screen.geometry()
                        target_x = sc_geom.left()
                        target_y = getattr(self, 'target_position_y', sc_geom.top())
                    except Exception:
                        target_x = rect.left()
                        target_y = rect.top()
                    # Retry config
                    retry_count = int(get_settings().get('debug_pre_show_retry_count', 3))
                    backoff_ms = int(get_settings().get('debug_pre_show_backoff_ms', 100))
                    total_attempts = max(1, retry_count)
                    hwnd_int = None
                    for attempt in range(1, total_attempts + 1):
                        try:
                            try:
                                hwnd_int = int(self.winId())
                            except Exception:
                                hwnd_int = None
                            if not hwnd_int:
                                colored_print(f"[PRE-SHOW] Attempt {attempt}/{total_attempts}: winId() not available yet")
                                time.sleep(backoff_ms/1000.0)
                                continue
                            # Move window natively
                            try:
                                res = user32.SetWindowPos(hwnd_int, 0, int(target_x), int(target_y), 0, 0, SWP_NOZORDER | SWP_NOSIZE | SWP_SHOWWINDOW)
                                last_err = ctypes.get_last_error()
                            except Exception as e:
                                last_err = getattr(e, 'errno', None)
                                res = 0
                            # Check monitor
                            mon = _get_monitor_info_for_hwnd(hwnd_int)
                            on_target = False
                            try:
                                screen_name = screen.name() if screen else None
                                if mon and (mon.get('device') == screen_name):
                                    on_target = True
                                else:
                                    # also compare rect overlap
                                    if mon and 'rect' in mon and sc_geom:
                                        on_target = (mon['rect'] == (sc_geom.left(), sc_geom.top(), sc_geom.right(), sc_geom.bottom()))
                            except Exception:
                                on_target = False
                            colored_print(f"[PRE-SHOW] Attempt {attempt}/{total_attempts}: SetWindowPos res={res} last_error={last_err} monitor={mon} on_target={on_target}")
                            # Use a compact trace for attempts
                            try:
                                title_str = self.windowTitle() if hasattr(self, 'windowTitle') else str(getattr(self, 'objectName', lambda: '')())
                            except Exception:
                                title_str = None
                            _trace_repair_attempt_event(hwnd_int, f"PRE-SHOW-{title_str}", attempt, on_target, last_error=last_err, screen_index=get_settings().get('screen_index', None))
                            if on_target:
                                break
                            time.sleep(backoff_ms/1000.0)
                        except Exception:
                            time.sleep(backoff_ms/1000.0)
            except Exception:
                pass
            
            # Show immediately with loading screen
            self.show()

            # Ensure the underlying QWindow is assigned to the target screen shortly after show
            try:
                def _post_show_assign(sc=screen):
                    try:
                        wh = self.windowHandle()
                        if wh is not None:
                            try:
                                wh.setScreen(sc)
                            except Exception:
                                pass
                        # Move to the intended geometry on that screen (respect secondary target if present)
                        try:
                            geom = sc.geometry()
                            target_y = getattr(self, 'target_position_y', geom.top())
                            self.setGeometry(geom.left(), int(target_y), geom.width(), self.ticker_height)
                            if DEBUG_APPBAR: print(f"[INIT] Post-show moved to x={geom.left()}, y={target_y}")
                            # Massive monitor debug: verify the native HWND/monitor mapping after show
                            try:
                                if get_settings().get('debug_massive_monitor_trace', False):
                                    hw = None
                                    try:
                                        hw = int(self.winId())
                                    except Exception:
                                        pass
                                    if hw:
                                        try:
                                            r = wintypes.RECT()
                                            user32 = ctypes.windll.user32
                                            user32.GetWindowRect(hw, ctypes.byref(r))
                                            mon = _get_monitor_info_for_hwnd(hw)
                                            colored_print(f"[INIT.POSTSHOW MONITOR TRACE] hwnd={hw} rect=({r.left},{r.top},{r.right},{r.bottom}) monitor={mon} screen_target_index={get_settings().get('screen_index', None)} screen_geom=({geom.left()},{geom.top()},{geom.width()},{geom.height()})")
                                            try:
                                                _trace_visibility_event(hw, f"POSTSHOW-MONITOR-TRACE", (r.left, r.top, r.right, r.bottom), bool(user32.IsWindowVisible(hw)), None, None, None, get_settings().get('screen_index', None))
                                            except Exception:
                                                pass
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                            # Post-show: bounded verify loop to ensure native HWND is actually on the target monitor and visible
                            try:
                                attempts = int(get_settings().get('post_show_verify_attempts', 2))
                                backoff_ms = int(get_settings().get('post_show_backoff_ms', 100))
                                SWP_NOZORDER = 0x0004
                                SWP_NOSIZE = 0x0001
                                SWP_SHOWWINDOW = 0x0040
                                for p_attempt in range(1, attempts + 1):
                                    try:
                                        hw2 = None
                                        try:
                                            hw2 = int(self.winId())
                                        except Exception:
                                            hw2 = None
                                        if not hw2:
                                            colored_print(f"[POST-SHOW] Attempt {p_attempt}/{attempts}: winId() unavailable")
                                            time.sleep(backoff_ms/1000.0)
                                            continue
                                        mon2 = _get_monitor_info_for_hwnd(hw2)
                                        on_target = False
                                        try:
                                            sc_geom = sc.geometry()
                                            if mon2 and (mon2.get('device') == (sc.name() if sc else None)):
                                                on_target = True
                                            elif mon2 and 'rect' in mon2 and sc_geom:
                                                on_target = (mon2['rect'] == (sc_geom.left(), sc_geom.top(), sc_geom.right(), sc_geom.bottom()))
                                        except Exception:
                                            on_target = False
                                        visible_now = bool(user32.IsWindowVisible(hw2))
                                        colored_print(f"[POST-SHOW] Attempt {p_attempt}/{attempts}: hwnd={hw2} monitor={mon2} on_target={on_target} visible={visible_now}")
                                        _trace_repair_attempt_event(hw2, f"POSTSHOW-{title_str}", p_attempt, on_target and visible_now, last_error=ctypes.get_last_error(), screen_index=get_settings().get('screen_index', None))
                                        if on_target and visible_now:
                                            break
                                        # Force native move to intended geometry
                                        try:
                                            target_x2 = sc_geom.left()
                                            target_y2 = getattr(self, 'target_position_y', sc_geom.top())
                                            user32.SetWindowPos(hw2, 0, int(target_x2), int(target_y2), 0, 0, SWP_NOZORDER | SWP_NOSIZE | SWP_SHOWWINDOW)
                                        except Exception:
                                            pass
                                        time.sleep(backoff_ms/1000.0)
                                    except Exception:
                                        time.sleep(backoff_ms/1000.0)
                            except Exception:
                                pass

                            # Re-run quick coordination checks after we've moved to the screen
                            try:
                                QtCore.QTimer.singleShot(50, lambda: self.check_for_other_tickers_early())
                                QtCore.QTimer.singleShot(150, lambda: self.setup_appbar_and_position())
                            except Exception:
                                pass

                            # If diagnostics are enabled or force-move setting is on, attempt a guarded force-move
                            try:
                                settings = get_settings()
                                do_force = settings.get('enable_force_move_on_startup', False) or getattr(self, 'show_diagnostic_overlay', False)
                                if do_force:
                                    # Delay slightly to let other windows settle, then force-move into place
                                    QtCore.QTimer.singleShot(120, lambda sc=sc, ty=target_y: self._force_move_to_screen(sc, ty))
                                    if DEBUG_APPBAR: print(f"[FORCE] Scheduled guarded force-move to screen {sc.name() if sc else 'None'} y={target_y}")
                            except Exception:
                                pass
                        except Exception:
                            pass
                    except Exception:
                        pass
                QtCore.QTimer.singleShot(100, _post_show_assign)
                if DEBUG_APPBAR: print("[INIT] Scheduled post-show screen assignment and geometry fix")
            except Exception:
                pass

            try:
                # Register created HWND for later forced-close by ReservationKeeper
                try:
                    hwnd_val = int(self.winId())
                    _created_ticker_hwnds.add(hwnd_val)
                    if DEBUG_APPBAR:
                        colored_print(f"[INIT] Registered ticker HWND {hwnd_val} in _created_ticker_hwnds")
                except Exception:
                    pass
            except Exception:
                pass
            
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
        """Cache settings to avoid repeated file I/O in paint loop"""
        if not hasattr(self, '_settings_cache'):
            self._settings_cache = {}
            self._settings_cache_time = 0
        
        import time
        current_time = time.time()
        # Refresh cache every 5 seconds
        if current_time - self._settings_cache_time > 5:
            settings = get_settings()
            self._settings_cache.update({
                'show_bloom': settings.get('show_bloom', True),
                'show_glow': settings.get('show_glow', True),
                'show_glass': settings.get('show_glass', False),
                'bloom_intensity': settings.get('bloom_intensity', 100),
                'show_fps_overlay': settings.get('show_fps_overlay', False)
            })
            self._settings_cache_time = current_time
        
        return self._settings_cache
    
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
    
    # ========== DIAGNOSTIC OVERLAY FOR DEBUGGING ==========
    def _init_diagnostic_overlay(self):
        """Create a small semi-transparent overlay QLabel to display diagnostic info."""
        try:
            self._diag_overlay = QtWidgets.QLabel(self)
            self._diag_overlay.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
            self._diag_overlay.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
            self._diag_overlay.setStyleSheet(
                "background-color: rgba(0,0,0,160); color: white; padding:6px; border-radius:6px; font-size:10px;"
            )
            self._diag_overlay.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
            self._diag_overlay.setVisible(self.show_diagnostic_overlay)
            self._diag_overlay.setWordWrap(True)
            # Timer to update overlay periodically
            self.diagnostic_overlay_timer = QtCore.QTimer(self)
            self.diagnostic_overlay_timer.timeout.connect(self._update_diagnostic_overlay)
            self.diagnostic_overlay_timer.setTimerType(QtCore.Qt.PreciseTimer)
            self.diagnostic_overlay_timer.start(250)
            # Force immediate update
            QtCore.QTimer.singleShot(0, self._update_diagnostic_overlay)
        except Exception:
            pass

    def _update_diagnostic_overlay(self):
        """Update diagnostic overlay contents and position."""
        try:
            if not getattr(self, 'show_diagnostic_overlay', False):
                if getattr(self, '_diag_overlay', None):
                    self._diag_overlay.hide()
                return
            hwnd = 0
            try:
                hwnd = int(self.winId())
            except Exception:
                pass
            screen = self.screen()
            screen_name = screen.name() if screen else 'None'
            geom = self.geometry()
            pos = self.pos()
            y = pos.y()
            target_y = getattr(self, 'target_position_y', 'N/A')
            is_secondary = getattr(self, 'is_secondary_ticker', False)
            # Reservation keeper status
            try:
                keeper = globals().get('_reservation_keeper', None)
                keeper_registered = getattr(keeper, '_registered', 'N/A') if keeper else 'None'
                keeper_honored = getattr(keeper, '_honored', 'N/A') if keeper else 'None'
            except Exception:
                keeper_registered = keeper_honored = 'Err'
            text = (
                f"HWND: {hwnd}\n"
                f"Screen: {screen_name}\n"
                f"Pos: x={pos.x()} y={y}\n"
                f"Geom: x={geom.x()} y={geom.y()} w={geom.width()} h={geom.height()}\n"
                f"Secondary: {is_secondary} target_y={target_y}\n"
                f"Keeper: registered={keeper_registered} honored={keeper_honored}"
            )
            # Update label text and adjust size & position (anchored top-right)
            self._diag_overlay.setText(text)
            self._diag_overlay.adjustSize()
            w = self.width()
            overlay_w = self._diag_overlay.width()
            x = max(8, w - overlay_w - 8)
            self._diag_overlay.move(x, 8)
            self._diag_overlay.show()
        except Exception:
            pass

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
            
        self._transient_candidates = []

        try:
            user32 = ctypes.windll.user32
            ticker_windows = []
            self._transient_candidates = []  # windows that are not visible now but may appear shortly (cloaked/transient)
            
            # Get target screen geometry for the configured screen index
            screen_index = get_settings().get("screen_index", 0)
            app = QtWidgets.QApplication.instance()
            screens = app.screens() if app else []
            if 0 <= screen_index < len(screens):
                screen = screens[screen_index]
            else:
                screen = app.primaryScreen() if app else None
            screen_rect = screen.geometry() if screen else None
            
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
                            # Use monitor handles (MonitorFromPoint) to deterministically check whether
                            # the window belongs to the target screen instead of relying on raw coords
                            on_target_screen = True
                            try:
                                if screen_rect is not None:
                                    MONITOR_DEFAULTTONULL = 0
                                    # monitor for the window
                                    # Use the center of the window to determine the monitor (more robust than top-left)
                                    pt_win = wintypes.POINT((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                                    hmon_win = user32.MonitorFromPoint(pt_win, MONITOR_DEFAULTTONULL)
                                    # monitor for the target screen (use screen center)
                                    pt_screen = wintypes.POINT(screen_rect.left() + screen_rect.width()//2, screen_rect.top() + screen_rect.height()//2)
                                    hmon_screen = user32.MonitorFromPoint(pt_screen, MONITOR_DEFAULTTONULL)
                                    on_target_screen = (hmon_win == hmon_screen)

                                    # Extra massive tracing: dump monitor device names and rects for each candidate
                                    try:
                                        if get_settings().get('debug_massive_monitor_trace', False):
                                            win_mon = _get_monitor_device_from_hmon(hmon_win) if hmon_win else None
                                            screen_mon = _get_monitor_device_from_hmon(hmon_screen) if hmon_screen else None
                                            colored_print(f"[INIT.MONITOR TRACE] hwnd={hwnd} center=({pt_win.x},{pt_win.y}) hmon_win={win_mon} hmon_screen={screen_mon} on_target_screen={on_target_screen}")
                                    except Exception:
                                        pass
                            except Exception:
                                on_target_screen = True

                            is_visible = bool(user32.IsWindowVisible(hwnd))
                            meets_height = 30 <= window_height <= 150
                            if on_target_screen and is_visible and meets_height:
                                ticker_windows.append({
                                    'hwnd': hwnd,
                                    'title': title,
                                    'top': rect.top,
                                    'height': window_height
                                })
                                print(f"[INIT] Found existing ticker: '{title}' at y={rect.top}, height={window_height}")
                            else:
                                try:
                                    if DEBUG_APPBAR:
                                        reason_parts = []
                                        if not on_target_screen:
                                            reason_parts.append('wrong_monitor')
                                        if not is_visible:
                                            reason_parts.append('not_visible')
                                        if not meets_height:
                                            reason_parts.append(f'height={window_height}')
                                        colored_print(f"[INIT] Rejected ticker {title}: reasons={','.join(reason_parts) or 'none'}, on_target_screen={on_target_screen}, visible={is_visible}, height={window_height}, rect=({rect.left},{rect.top},{rect.right},{rect.bottom}), screen_rect=({screen_rect.left()},{screen_rect.top()},{screen_rect.width()},{screen_rect.height()})")

                                        # Persist visibility trace for rejected (not visible) windows
                                        if 'not_visible' in reason_parts:
                                            try:
                                                GWL_STYLE = -16
                                                GWL_EXSTYLE = -20
                                                try:
                                                    style_val = user32.GetWindowLongW(hwnd, GWL_STYLE)
                                                    ex_style_val = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                                                    style_str = f"0x{style_val:08X}"
                                                    ex_style_str = f"0x{ex_style_val:08X}"
                                                except Exception:
                                                    style_str = None
                                                    ex_style_str = None
                                                try:
                                                    dwmapi = ctypes.windll.dwmapi
                                                    DWMWA_CLOAKED = 14
                                                    cloak_val = ctypes.c_int()
                                                    res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloak_val), ctypes.sizeof(cloak_val))
                                                    cloaked = cloak_val.value if res == 0 else None
                                                except Exception:
                                                    cloaked = None
                                                try:
                                                    _trace_visibility_event(hwnd, title, (rect.left, rect.top, rect.right, rect.bottom), is_visible, cloaked, style_str, ex_style_str, get_settings().get('screen_index', None))
                                                except Exception:
                                                    pass

                                                # Guarded repair attempt for initialization-time not-visible windows
                                                try:
                                                    if not is_visible and cloaked == 0:
                                                        repaired_init = _attempt_repair_not_visible(hwnd, (rect.left, rect.top, rect.right, rect.bottom), screen_index=get_settings().get('screen_index', None), context=f"INIT-{title}")
                                                        if repaired_init:
                                                            colored_print(f"[INIT] Repair succeeded for '{title}' on init (hwnd={hwnd})")
                                                        else:
                                                            colored_print(f"[INIT] Repair attempt failed for '{title}' on init (hwnd={hwnd})")
                                                except Exception:
                                                    pass
                                            except Exception:
                                                pass
                                except Exception:
                                    pass
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

            # Resolve configured screen for consistent checks used throughout the enumeration
            screen_index = get_settings().get("screen_index", 0)
            app = QtWidgets.QApplication.instance()
            screens = app.screens() if app else []
            if 0 <= screen_index < len(screens):
                screen = screens[screen_index]
            else:
                screen = app.primaryScreen() if app else None
            screen_rect = screen.geometry() if screen else None

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
                            
                            # Additional validation: ticker windows should be at the top of the TARGET screen
                            # and have a height close to our ticker height (within reasonable range)
                            window_height = rect.bottom - rect.top
                            
                            # Determine whether the window is on the target monitor using MonitorFromPoint
                            try:
                                MONITOR_DEFAULTTONULL = 0
                                # Use the center of the window to determine the monitor (more robust than top-left)
                                pt_win = wintypes.POINT((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                                hmon_win = user32.MonitorFromPoint(pt_win, MONITOR_DEFAULTTONULL)
                                if screen_rect is not None:
                                    pt_screen = wintypes.POINT(screen_rect.left() + screen_rect.width()//2, screen_rect.top() + screen_rect.height()//2)
                                    hmon_screen = user32.MonitorFromPoint(pt_screen, MONITOR_DEFAULTTONULL)
                                    on_target_screen = (hmon_win == hmon_screen)
                                else:
                                    on_target_screen = True

                                # Extra massive tracing: dump monitor device names and rects for each candidate
                                try:
                                    if get_settings().get('debug_massive_monitor_trace', False):
                                        win_mon = _get_monitor_device_from_hmon(hmon_win) if hmon_win else None
                                        screen_mon = _get_monitor_device_from_hmon(hmon_screen) if hmon_screen else None
                                        colored_print(f"[COORD.MONITOR TRACE] hwnd={hwnd} center=({pt_win.x},{pt_win.y}) hmon_win={win_mon} hmon_screen={screen_mon} on_target_screen={on_target_screen}")
                                except Exception:
                                    pass
                            except Exception:
                                # Fallback to coordinate compare if monitor APIs fail
                                if screen_rect is not None:
                                    on_target_screen = (
                                        rect.left >= screen_rect.left() and rect.left < (screen_rect.left() + screen_rect.width()) and
                                        rect.top >= screen_rect.top() and rect.top < (screen_rect.top() + screen_rect.height())
                                    )
                                else:
                                    on_target_screen = True

                            # CRITICAL: Filter out hidden/minimized windows and windows not on target screen
                            is_visible = bool(user32.IsWindowVisible(hwnd))
                            not_hidden = (rect.top != -32000 and rect.left != -32000)
                            meets_height = 30 <= window_height <= 150
                            if on_target_screen and (is_visible or not_hidden) and meets_height:
                                ticker_windows.append({
                                    'hwnd': hwnd,
                                    'title': title,
                                    'top': rect.top,
                                    'height': window_height
                                })
                                print(f"[COORDINATE] Found valid ticker: '{title}' at y={rect.top}, height={window_height}")
                            else:
                                try:
                                    if DEBUG_APPBAR:
                                        reason_parts = []
                                        if not on_target_screen:
                                            reason_parts.append('wrong_monitor')
                                        if not (is_visible or not_hidden):
                                            reason_parts.append('not_visible')
                                        if not meets_height:
                                            reason_parts.append(f'height={window_height}')
                                        colored_print(f"[COORDINATE] Rejected '{title}': reasons={','.join(reason_parts) or 'none'}, on_target_screen={on_target_screen}, visible={is_visible}, rect_top={rect.top}, height={window_height}, screen_rect=({screen_rect.left() if screen_rect else 'N/A'},{screen_rect.top() if screen_rect else 'N/A'},{screen_rect.width() if screen_rect else 'N/A'},{screen_rect.height() if screen_rect else 'N/A'})")

                                        # Additional visibility diagnostics for not-visible windows
                                        if 'not_visible' in reason_parts:
                                            try:
                                                GWL_STYLE = -16
                                                GWL_EXSTYLE = -20
                                                style = user32.GetWindowLongW(hwnd, GWL_STYLE)
                                                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                                            except Exception:
                                                style = None
                                                ex_style = None
                                            try:
                                                dwmapi = ctypes.windll.dwmapi
                                                DWMWA_CLOAKED = 14  # DwmGetWindowAttribute - returns cloaked state
                                                cloak_val = ctypes.c_int()
                                                res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloak_val), ctypes.sizeof(cloak_val))
                                                cloaked = cloak_val.value if res == 0 else None
                                            except Exception:
                                                cloaked = None

                                            # Record as a transient candidate for a short re-check after enumeration
                                            try:
                                                self._transient_candidates.append({
                                                    'hwnd': hwnd,
                                                    'title': title,
                                                    'rect': (rect.left, rect.top, rect.right, rect.bottom),
                                                    'reason': ','.join(reason_parts),
                                                    'cloaked': cloaked
                                                })
                                                colored_print(f"[COORDINATE] Transient candidate recorded: '{title}' cloaked={cloaked}")

                                                # Attempt a guarded repair for not-visible but not-cloaked windows
                                                try:
                                                    if not is_visible and cloaked == 0:
                                                        repaired = _attempt_repair_not_visible(hwnd, (rect.left, rect.top, rect.right, rect.bottom), screen_index=get_settings().get('screen_index', None), context=f"VisDetails-{title}")
                                                        if repaired:
                                                            colored_print(f"[COORDINATE] Repair succeeded for '{title}' (hwnd={hwnd})")
                                                        else:
                                                            colored_print(f"[COORDINATE] Repair attempt failed for '{title}' (hwnd={hwnd})")
                                                except Exception:
                                                    pass
                                            except Exception:
                                                pass

                                            style_str = f"0x{style:08X}" if style is not None else 'N/A'
                                            ex_style_str = f"0x{ex_style:08X}" if ex_style is not None else 'N/A'
                                            colored_print(f"[COORDINATE] VisDetails '{title}': IsWindowVisible={is_visible}, not_hidden={not_hidden}, style={style_str}, ex_style={ex_style_str}, cloaked={cloaked}")
                                            colored_print(f"    rect=({rect.left},{rect.top},{rect.right},{rect.bottom}), screen_rect=({screen_rect.left() if screen_rect else 'N/A'},{screen_rect.top() if screen_rect else 'N/A'})")

                                            # Persist a compact visibility trace for offline analysis
                                            try:
                                                screen_idx = get_settings().get('screen_index', None)
                                                _trace_visibility_event(hwnd, title, (rect.left, rect.top, rect.right, rect.bottom), is_visible, cloaked, style_str, ex_style_str, screen_idx)
                                            except Exception:
                                                pass
                                except Exception:
                                    pass
                except:
                    pass
                return True
            
            # Enumerate all windows
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
            
            print(f"[COORDINATE] Enumeration complete. Found {len(ticker_windows)} valid ticker windows")

            # If nothing valid was found, try transient candidates first (they may have been cloaked/hidden briefly)
            if not ticker_windows and getattr(self, "_transient_candidates", None):
                if DEBUG_APPBAR:
                    colored_print(f"[COORDINATE] No valid tickers found - re-checking {len(getattr(self, '_transient_candidates', []))} transient candidates")
                for attempt in range(3):
                    time.sleep(0.12)
                    found_now = []
                    for c in list(getattr(self, "_transient_candidates", [])):
                        try:
                            hwnd = c['hwnd']
                            is_visible = bool(user32.IsWindowVisible(hwnd))
                            rect = wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            window_height = rect.bottom - rect.top
                            not_hidden = (rect.top != -32000 and rect.left != -32000)
                            meets_height = 30 <= window_height <= 150
                            if (is_visible or not_hidden) and meets_height:
                                found_now.append({'hwnd': hwnd, 'title': c.get('title', 'TCKR'), 'top': rect.top, 'height': window_height})
                                colored_print(f"[COORDINATE] Transient re-check OK: '{c.get('title','TCKR')}' now visible at y={rect.top}, height={window_height}")
                        except Exception:
                            pass
                    if found_now:
                        ticker_windows = found_now
                        break
                if not ticker_windows and DEBUG_APPBAR:
                    colored_print(f"[COORDINATE] Transient re-check completed - no candidates became visible after retries")

            # If nothing valid was found, perform a relaxed scan which ignores transient visibility
            # and small coordinate anomalies so we can still position secondary tickers reliably
            if not ticker_windows:
                try:
                    if DEBUG_APPBAR:
                        colored_print("[COORDINATE] No valid tickers found - performing relaxed scan for TCKR windows")
                    relaxed = self._relaxed_ticker_scan(screen)
                    if relaxed:
                        ticker_windows = relaxed
                        print(f"[COORDINATE] Relaxed scan found {len(ticker_windows)} ticker windows")
                except Exception as e:
                    if DEBUG_APPBAR:
                        colored_print(f"[COORDINATE] Relaxed scan error: {e}")
            
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

    def _relaxed_ticker_scan(self, screen=None):
        """Relaxed scan to find TCKR windows even if they're temporarily invisible or slightly off-screen.
        Returns a list of ticker descriptors like [{'hwnd', 'title', 'top', 'height'}, ...]
        This is robust: if `screen` is None we compute the configured screen to avoid caller errors.
        """
        found = []
        try:
            # Resolve screen if caller didn't provide one
            app = QtWidgets.QApplication.instance()
            screens = app.screens() if app else []
            screen_index = get_settings().get('screen_index', 0)
            if screen is None:
                if 0 <= screen_index < len(screens):
                    screen = screens[screen_index]
                else:
                    screen = app.primaryScreen() if app else None

            user32 = ctypes.windll.user32
            screen_rect = screen.geometry() if screen else None

            def enum_callback(hwnd, lParam):
                try:
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length <= 0:
                        return True
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    is_ticker = (title == "TCKR") or (title.startswith("TCKR-") and title[5:].isdigit())
                    if not is_ticker:
                        return True
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    window_height = rect.bottom - rect.top

                    # Use center to determine monitor; if no screen_rect available, use looser horizontal check
                    MONITOR_DEFAULTTONULL = 0
                    pt_win = wintypes.POINT((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
                    hmon_win = user32.MonitorFromPoint(pt_win, MONITOR_DEFAULTTONULL)

                    on_target = False
                    if screen_rect is not None:
                        pt_screen = wintypes.POINT(screen_rect.left() + screen_rect.width()//2, screen_rect.top() + screen_rect.height()//2)
                        hmon_screen = user32.MonitorFromPoint(pt_screen, MONITOR_DEFAULTTONULL)
                        on_target = (hmon_win == hmon_screen) or (rect.left >= screen_rect.left() - 200 and rect.left < screen_rect.left() + screen_rect.width() + 200)
                    else:
                        # If no screen info, accept anything that looks like a TCKR window
                        on_target = True

                    if on_target:
                        found.append({'hwnd': hwnd, 'title': title, 'top': rect.top, 'height': window_height})
                        if DEBUG_APPBAR:
                            colored_print(f"[RELAX] Found ticker (relaxed): {title} at y={rect.top}, h={window_height}, on_target={on_target}")
                except Exception:
                    pass
                return True

            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
            user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
        except Exception as e:
            if DEBUG_APPBAR:
                colored_print(f"[RELAX] relaxed scan error: {e}")
        return found

    def _force_move_to_screen(self, screen, target_y=None):
        """Force-move this ticker to the given QScreen and y coordinate using both Qt and Win32 fallbacks.
        This is a debugging-only non-destructive helper. It will not change z-order if not necessary.
        """
        try:
            if screen is None:
                return False
            # Use QWindow if available
            try:
                wh = self.windowHandle()
                if wh is not None:
                    try:
                        wh.setScreen(screen)
                    except Exception:
                        pass
            except Exception:
                pass

            geom = screen.geometry()
            if target_y is None:
                target_y = geom.top()

            # Use SetWindowPos as a reliable fallback for moving OS-level hwnd
            try:
                hwnd = int(self.winId())
                user32 = ctypes.windll.user32
                HWND_TOPMOST = -1
                SWP_NOACTIVATE = 0x0010
                SWP_SHOWWINDOW = 0x0040
                user32.SetWindowPos(hwnd, HWND_TOPMOST, geom.left(), int(target_y), geom.width(), self.ticker_height, SWP_SHOWWINDOW | SWP_NOACTIVATE)
                if DEBUG_APPBAR:
                    colored_print(f"[FORCE] SetWindowPos moved hwnd={hwnd} to x={geom.left()}, y={target_y} on screen {screen.name()}")
            except Exception as e:
                if DEBUG_APPBAR:
                    colored_print(f"[FORCE] Failed SetWindowPos: {e}")
            return True
        except Exception:
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

        # If using a non-primary monitor, AppBar registration is unreliable on some GPUs/compositors.
        # Skip AppBar registration on non-primary screens and enforce topmost positioning instead.
        try:
            app = QtWidgets.QApplication.instance()
            primary_screen = app.primaryScreen() if app else None
            is_primary_screen = (primary_screen is not None and screen == primary_screen)
            if not is_primary_screen:
                # Mark this screen as unsupported for AppBar unless user explicitly overrides
                try:
                    screen_key = screen.name() if hasattr(screen, 'name') else None
                except Exception:
                    screen_key = None
                if not screen_key:
                    screen_key = f"{rect.left()}_{rect.top()}_{rect.width()}_{rect.height()}"
                if not get_settings().get('enable_appbar_on_nonprimary', False):
                    _appbar_supported[screen_key] = False
                colored_print(f"[APPBAR] Screen not primary - skipping AppBar registration on screen {screen.geometry()} and enforcing topmost window")
                try:
                    user32 = ctypes.windll.user32
                    HWND_TOPMOST = -1
                    SWP_NOACTIVATE = 0x0010
                    SWP_SHOWWINDOW = 0x0040
                    # Force this window to topmost at the target rect (logical coords already set)
                    user32.SetWindowPos(int(self.winId()), HWND_TOPMOST, rect.left(), rect.top(), rect.width(), self.ticker_height, SWP_SHOWWINDOW | SWP_NOACTIVATE)
                except Exception:
                    pass
                # Do not attempt AppBar registration on non-primary screens
                return
        except Exception:
            pass

        # If a ReservationKeeper creation is in-flight, defer primary registration
        global _keeper_creation_in_progress
        try:
            if _keeper_creation_in_progress:
                colored_print(f"[APPBAR] Keeper creation in progress - deferring primary registration for instance #{self.instance_id}")
                # Retry shortly after creation completes
                QtCore.QTimer.singleShot(150, lambda: self.setup_appbar_and_position())
                return
        except Exception:
            pass
        # If a ReservationKeeper removal is in-progress, defer primary registration
        global _keeper_removal_in_progress
        try:
            if _keeper_removal_in_progress:
                colored_print(f"[APPBAR] Keeper removal in progress - deferring primary registration for instance #{self.instance_id}")
                QtCore.QTimer.singleShot(200, lambda: self.setup_appbar_and_position())
                return
        except Exception:
            pass
        
        # Check if space is already reserved at the top (from a previous ticker)
        user32 = ctypes.windll.user32
        work_area = wintypes.RECT()
        user32.SystemParametersInfoW(48, 0, ctypes.byref(work_area), 0)  # SPI_GETWORKAREA
        existing_reservation = work_area.top - rect.top()
        
        if existing_reservation > 0:
            if DEBUG_APPBAR: print(f"[APPBAR] Space already reserved at top ({existing_reservation}px)")
            # Regardless of current reservation, re-register the AppBar to ensure
            # the reserved height matches our current settings (single or double).
            # This avoids treating stale reservations as valid secondary slots
            # which leaves a visible gap at the top of the screen.
            if not has_other_tickers:
                if DEBUG_APPBAR: print(f"[APPBAR] Reservation found but no other tickers detected - will refresh registration")
            else:
                if DEBUG_APPBAR: print(f"[APPBAR] Other tickers detected - primary will refresh registration to ensure correct reservation")
        
        if DEBUG_APPBAR: print(f"[APPBAR] No existing reservation found - will register new AppBar")
        
        # Remove any previous appbar registration for THIS window only
        # If a combined reservation was recently applied and appears sufficient,
        # avoid removing/re-registering here (that can overwrite a combined reservation).
        try:
            global _last_reserved_height, _last_reserved_by, _last_reserved_by_hwnd, _last_reserved_ts
            settings = get_settings()
            # If second ticker support is enabled and we detected other tickers,
            # prefer to keep an existing combined reservation rather than tearing it down.
            if settings.get("enable_second_ticker", False) and has_other_tickers:
                now_ts = time.time()
                ttl = 15.0
                combined_logical = self.ticker_height * 2

                # If a recent combined reservation exists, skip re-registration to avoid overwrite
                if _last_reserved_ts and (now_ts - _last_reserved_ts) < ttl and _last_reserved_height and _last_reserved_height >= combined_logical:
                    colored_print(f"[APPBAR] Detected recent combined reservation ({_last_reserved_height}px) - skipping re-register to avoid overwrite")
                    # Ensure we are placed at top inside reserved space
                    self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
                    QtCore.QTimer.singleShot(300, lambda: self.ensure_top_position())
                    return

                # Otherwise, attempt to actively request a combined physical reservation
                try:
                    # Find other ticker HWND candidate and attempt combined reservation
                    user32 = ctypes.windll.user32
                    other_candidates = []
                    def enum_cb(hwnd, lParam):
                        try:
                            my_hwnd = int(self.winId())
                            if hwnd == my_hwnd:
                                return True
                            length = user32.GetWindowTextLengthW(hwnd)
                            if length > 0:
                                buff = ctypes.create_unicode_buffer(length + 1)
                                user32.GetWindowTextW(hwnd, buff, length + 1)
                                title = buff.value
                                is_ticker = (
                                    title == "TCKR" or
                                    (title.startswith("TCKR-") and len(title) > 5 and title[5:].isdigit())
                                )
                                if is_ticker and user32.IsWindowVisible(hwnd):
                                    rectTmp = wintypes.RECT()
                                    user32.GetWindowRect(hwnd, ctypes.byref(rectTmp))
                                    heightTmp = rectTmp.bottom - rectTmp.top
                                    if rectTmp.top >= 0 and 30 <= heightTmp <= 150:
                                        other_candidates.append(hwnd)
                        except Exception:
                            pass
                        return True

                    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                    user32.EnumWindows(EnumProc(enum_cb), 0)

                    if other_candidates:
                        other_hwnd = int(other_candidates[0])
                        if DEBUG_APPBAR: print(f"[APPBAR] Found other ticker HWND {other_hwnd} - attempting combined PHYSICAL reservation via keeper")
                        actual_top = reserve_combined_with_keeper(int(self.winId()), other_hwnd, screen_index)
                        # If reserve_combined_appbar succeeded in reserving, assume it's good and return
                        if actual_top is not None:
                            colored_print(f"[APPBAR] Combined reservation request returned actual_top={actual_top} - skipping further registration")
                            self.setGeometry(rect.left(), rect.top(), rect.width(), self.ticker_height)
                            QtCore.QTimer.singleShot(300, lambda: self.ensure_top_position())
                            return
                except Exception:
                    pass
        except Exception:
            pass

        # No suitable combined reservation found/kept; remove existing registration for this window
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
                
                # Calculate appbar height - prefer a physical combined reservation
                settings = get_settings()
                appbar_height = self.ticker_height

                # If second ticker is enabled and we detected other tickers, try the
                # combined PHYSICAL reservation helper which computes actual window
                # heights and requests the summed physical pixels from Windows.
                if settings.get("enable_second_ticker", False) and has_other_tickers:
                    try:
                        # Find a candidate other ticker HWND to compute combined height
                        user32 = ctypes.windll.user32
                        other_candidates = []
                        def enum_cb(hwnd, lParam):
                            try:
                                my_hwnd = int(self.winId())
                                if hwnd == my_hwnd:
                                    return True
                                length = user32.GetWindowTextLengthW(hwnd)
                                if length > 0:
                                    buff = ctypes.create_unicode_buffer(length + 1)
                                    user32.GetWindowTextW(hwnd, buff, length + 1)
                                    title = buff.value
                                    is_ticker = (
                                        title == "TCKR" or
                                        (title.startswith("TCKR-") and len(title) > 5 and title[5:].isdigit())
                                    )
                                    if is_ticker and user32.IsWindowVisible(hwnd):
                                        rectTmp = wintypes.RECT()
                                        user32.GetWindowRect(hwnd, ctypes.byref(rectTmp))
                                        heightTmp = rectTmp.bottom - rectTmp.top
                                        if rectTmp.top >= 0 and 30 <= heightTmp <= 150:
                                            other_candidates.append(hwnd)
                            except Exception:
                                pass
                            return True

                        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                        user32.EnumWindows(EnumProc(enum_cb), 0)

                        if other_candidates:
                            other_hwnd = int(other_candidates[0])
                            if DEBUG_APPBAR: print(f"[APPBAR] Found other ticker HWND {other_hwnd} - attempting combined PHYSICAL reservation via keeper")
                            actual_top = reserve_combined_with_keeper(int(self.winId()), other_hwnd, screen_index)
                        else:
                            # Fallback to logical double height if no other HWND found
                            appbar_height = self.ticker_height * 2
                            if DEBUG_APPBAR: print(f"[APPBAR] No other HWND found; falling back to logical double height: {appbar_height}px")
                            actual_top = set_appbar(int(self.winId()), appbar_height, rect)
                    except Exception as e:
                        colored_print(f"[APPBAR WARNING] Combined reservation attempt failed: {e}")
                        appbar_height = self.ticker_height * 2
                        actual_top = set_appbar(int(self.winId()), appbar_height, rect)
                else:
                    if settings.get("enable_second_ticker", False):
                        appbar_height = self.ticker_height * 2
                        if DEBUG_APPBAR: print(f"[APPBAR] Second ticker enabled but no other tickers detected - reserving double height: {appbar_height}px")

                    if DEBUG_APPBAR: print(f"[APPBAR] Registering PRIMARY ticker as appbar: height={appbar_height}, screen={rect}")
                    actual_top = set_appbar(int(self.winId()), appbar_height, rect)
                
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
        try:
            tray = getattr(self, 'tray_icon', None)
            primary_id = id(tray.primary_ticker) if (tray and getattr(tray, 'primary_ticker', None)) else None
            is_primary = (tray and getattr(tray, 'primary_ticker', None) == self)
            print(f"[DELIVER] id(self)={id(self)} tray_primary_id={primary_id} is_primary={is_primary}")
        except Exception:
            pass
        # Don't re-sort! load_stocks() already returns sorted list
        self.stocks = [s[0] for s in load_stocks()]

        # If incoming prices contain no valid entries, skip overwriting existing prices
        try:
            valid_count = sum(1 for v in (prices or {}).values() if (v is not None and getattr(v, '__len__', lambda: 0)() and v[0] is not None))
        except Exception:
            valid_count = 0

        import time as _time_module
        now_ts = _time_module.time()

        if valid_count == 0:
            try:
                print(f"[DELIVER.SKIP] Received {len(prices)} prices but 0 valid entries — preserving existing prices")
            except Exception:
                pass

            # Increment consecutive-failure counter and decide staleness by policy
            try:
                self.consecutive_failed_fetches = getattr(self, 'consecutive_failed_fetches', 0) + 1
            except Exception:
                self.consecutive_failed_fetches = 1

            last_success = getattr(self, 'last_successful_fetch_ts', getattr(self, 'last_api_update_time', 0)) or 0
            elapsed = now_ts - last_success if last_success else float('inf')
            # Mark stale if either threshold reached: 3 consecutive failures OR 5 minutes since last success
            if self.consecutive_failed_fetches >= 3 or elapsed >= 300:
                try:
                    self.stale = True
                    colored_print(f"[STALE.MARK] Ticker id={id(self)} consecutive_failed={self.consecutive_failed_fetches} elapsed={int(elapsed)}s -> STALE")
                except Exception:
                    pass

            # Clear loading state and rebuild display without overwriting prices for self
            self.loading = False
            self.bloom_cache_valid = False
            try:
                self.build_ticker_text(reset_scroll=False)
            except Exception:
                pass

            # Also ensure other managed tickers don't remain stuck on loading; update their failure counters
            try:
                tray = getattr(self, 'tray_icon', None)
                if tray and getattr(tray, 'ticker_windows', None):
                    for t in tray.ticker_windows:
                        if t is self:
                            continue
                        def _clear_other(tt=t):
                            try:
                                # Bump their failure counters
                                try:
                                    tt.consecutive_failed_fetches = getattr(tt, 'consecutive_failed_fetches', 0) + 1
                                except Exception:
                                    tt.consecutive_failed_fetches = 1

                                last_s = getattr(tt, 'last_successful_fetch_ts', getattr(tt, 'last_api_update_time', 0)) or 0
                                elapsed_other = now_ts - last_s if last_s else float('inf')
                                if tt.consecutive_failed_fetches >= 3 or elapsed_other >= 300:
                                    try:
                                        tt.stale = True
                                    except Exception:
                                        pass

                                if getattr(tt, 'loading', False):
                                    tt.loading = False
                                    tt.bloom_cache_valid = False
                                    tt.build_ticker_text(reset_scroll=False)
                                    try:
                                        print(f"[DELIVER.SKIP.CLEAR] Cleared loading for {tt.windowTitle() if hasattr(tt, 'windowTitle') else repr(tt)} (stale={getattr(tt,'stale',False)})")
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                        try:
                            QtCore.QTimer.singleShot(0, _clear_other)
                        except Exception:
                            try:
                                _clear_other()
                            except Exception:
                                pass
            except Exception:
                pass
        else:
            # Successful fetch: reset failure counter and update last-success timestamp
            self.prices = prices
            try:
                self.consecutive_failed_fetches = 0
            except Exception:
                pass
            try:
                self.last_successful_fetch_ts = now_ts
            except Exception:
                try:
                    self.last_api_update_time = now_ts
                except Exception:
                    pass
            try:
                self.stale = False
            except Exception:
                pass
            self.loading = False  # Hide loading screen, show ticker with real data
            self.bloom_cache_valid = False  # Invalidate bloom cache on price update
            self.last_api_update_time = now_ts
            colored_print("[TCKR] Loading complete - building ticker display")

            # Trace ticker ready state and schedule a watchdog to verify first-paint
            try:
                _trace_ticker_state_event(self, 'loading_complete')
            except Exception:
                pass
            try:
                # Use a resilient invoker that won't crash if the target lacks the method
                QtCore.QTimer.singleShot(1500, lambda s=self: _invoke_check_first_paint(s))
            except Exception:
                try:
                    _invoke_check_first_paint(self)
                except Exception:
                    pass

            self.build_ticker_text(reset_scroll=True)

        # If this is the primary ticker, broadcast prices to all managed tickers
        try:
            tray = getattr(self, 'tray_icon', None)
            if tray and getattr(tray, 'primary_ticker', None) == self:
                try:
                    # Only broadcast if we have valid prices to share
                    if valid_count > 0:
                        print(f"[DELIVER] Broadcasting from primary id={id(self)} to tray id={id(tray)}")
                        tray.broadcast_prices(prices, now=self.last_api_update_time)
                        print(f"[DELIVER] broadcast_prices returned")
                    else:
                        try:
                            print(f"[DELIVER.SKIP] Skipping broadcast from primary due to 0 valid prices")
                        except Exception:
                            pass
                except Exception:
                    print(f"[DELIVER] broadcast_prices failed, falling back to per-ticker updates")
                    for ticker in getattr(tray, 'ticker_windows', []):
                        if ticker != self:
                            try:
                                ticker.stocks = [s[0] for s in load_stocks()]
                                # Only overwrite per-ticker prices when valid
                                if valid_count > 0:
                                    ticker.prices = prices.copy()
                                    ticker.last_api_update_time = self.last_api_update_time
                                ticker.loading = False
                                ticker.bloom_cache_valid = False
                                ticker.build_ticker_text(reset_scroll=True)
                            except Exception:
                                pass
        except Exception:
            pass

    def _handle_coordinated_prices(self, prices, had_429, now):
        """Handle coordinated price fetching results and distribute to all tickers"""
        colored_print(f"[COORDINATED FETCH] Received {len(prices)} prices - distributing to all tickers")
        try:
            # Prefer centralized broadcast to ensure all tickers update consistently
            if hasattr(self, 'tray_icon') and self.tray_icon:
                try:
                    self.tray_icon.broadcast_prices(prices, now=now)
                    return
                except Exception:
                    pass

            # Fallback: distribute prices directly
            try:
                valid_count = sum(1 for v in (prices or {}).values() if (v is not None and getattr(v, '__len__', lambda: 0)() and v[0] is not None))
            except Exception:
                valid_count = 0

            for ticker in getattr(self.tray_icon, 'ticker_windows', []):
                try:
                    ticker.stocks = [s[0] for s in load_stocks()]
                    # Only overwrite prices when we have valid data
                    if valid_count > 0:
                        ticker.prices = prices.copy()
                        ticker.last_api_update_time = now
                    ticker.loading = False
                    ticker.bloom_cache_valid = False
                    ticker.build_ticker_text(reset_scroll=True)
                    print(f"[COORDINATED FETCH] Updated ticker with {len(prices)} prices (valid_count={valid_count})")
                except Exception:
                    pass
        except Exception:
            pass

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

    def draw_rotated_triangle(self, painter, x, y, size, rotation_angle, color):
        """
        Draw a triangle rotated to the specified angle.
        
        Args:
            painter: QPainter object
            x, y: Center position for the triangle
            size: Size of the triangle
            rotation_angle: Rotation in degrees (0=up, 90=right, 180=down)
            color: QColor for the triangle
        """
        # Create triangle polygon (pointing up by default, base slightly smaller than sides)
        half_size = size / 2
        triangle = QtGui.QPolygon([
            QtCore.QPoint(0, -int(half_size)),      # Top point
            QtCore.QPoint(-int(half_size * 0.75), int(half_size * 0.5)),  # Bottom left
            QtCore.QPoint(int(half_size * 0.75), int(half_size * 0.5))    # Bottom right
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
            prices, had_429 = fetch_all_stock_prices_with_429(tickers, api_key or "", api_key_2)
            # Diagnostic: count valid prices
            try:
                valid_count = sum(1 for v in prices.values() if (v is not None and v[0] is not None))
            except Exception:
                valid_count = 0
            colored_print(f"[FETCH WORKER] Fetched {len(prices)} prices, valid={valid_count}, had_429={had_429}")
            # Use QTimer to call the handler in the main thread with a fresh timestamp
            import time as _time
            now_local = _time.time()
            def _deliver_on_main():
                try:
                    # Diagnostic: entering delivery on main thread
                    try:
                        print(f"[DELIVER] Updating main instance id={id(self)} now={now_local}")
                    except Exception:
                        pass
                    # Update this window
                    self.stocks = [s[0] for s in load_stocks()]
                    # Normalize prices into (price, prev_close) tuples
                    norm = {}
                    for k, v in (prices or {}).items():
                        try:
                            if v is None:
                                norm[k] = (None, None)
                            elif isinstance(v, (list, tuple)):
                                p = v[0] if len(v) > 0 else None
                                pc = v[1] if len(v) > 1 else None
                                try:
                                    p = float(p) if p is not None else None
                                except Exception:
                                    p = None
                                try:
                                    pc = float(pc) if pc is not None else None
                                except Exception:
                                    pc = None
                                norm[k] = (p, pc)
                            else:
                                norm[k] = (None, None)
                        except Exception:
                            norm[k] = (None, None)

                    self.prices = norm
                    self.loading = False
                    self.bloom_cache_valid = False
                    self.last_api_update_time = now_local
                    try:
                        self.build_ticker_text(reset_scroll=False)
                    except Exception:
                        pass
                except Exception:
                    pass

                # Broadcast to managed ticker windows if present
                try:
                    if hasattr(self, 'tray_icon') and self.tray_icon:
                        try:
                            try:
                                tw_names = [getattr(t, 'windowTitle', lambda: str(id(t)))() if hasattr(t, 'windowTitle') else repr(t) for t in getattr(self.tray_icon, 'ticker_windows', [])]
                                print(f"[DELIVER] tray_icon present id={id(self.tray_icon)} tickers={len(tw_names)} titles={tw_names}")
                            except Exception:
                                pass
                            self.tray_icon.broadcast_prices(prices, now=now_local)
                        except Exception:
                            # Best-effort fallback: call _handle_coordinated_prices
                            try:
                                self._handle_coordinated_prices(prices, had_429, now_local)
                            except Exception:
                                pass
                except Exception:
                    pass

            try:
                QtCore.QTimer.singleShot(0, _deliver_on_main)
            except Exception:
                # Fallback: call directly on this thread
                try:
                    _deliver_on_main()
                except Exception:
                    pass

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
            prices, had_429 = fetch_all_stock_prices_with_429(tickers, api_key or "", api_key_2)
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
            ticker.loading = False
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

        # If the incoming inplace update contains zero valid entries,
        # avoid overwriting existing `self.prices` (preserve displayed values).
        try:
            incoming_valid = sum(1 for v in (new_prices or {}).values() if (v is not None and getattr(v, '__len__', lambda: 0)() and v[0] is not None))
        except Exception:
            incoming_valid = 0

        if incoming_valid == 0:
            try:
                print(f"[INPLACE.SKIP] Incoming inplace update has 0 valid entries — preserving existing prices and clearing loading state")
            except Exception:
                pass
            try:
                self.loading = False
                self.bloom_cache_valid = False
                try:
                    self.stale = True
                    colored_print(f"[STALE.MARK] Ticker id={id(self)} marked stale by INPLACE.SKIP")
                except Exception:
                    pass
                self.build_ticker_text(reset_scroll=False)
            except Exception:
                pass
            return
        
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
                        if self.failed_fetch_counts[tkr] < 3 and old_price is not None:
                            price = old_price
                            prev_close = self.prices.get(tkr, (None, None))[1]
                        else:
                            price = None
                            prev_close = None
                    else:
                        self.failed_fetch_counts[tkr] = 0
                    
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
                    if self.failed_fetch_counts[tkr] < 3 and old_price is not None:
                        price = old_price
                        prev_close = self.prices.get(tkr, (None, None))[1]
                    else:
                        price = None
                        prev_close = None
                else:
                    self.failed_fetch_counts[tkr] = 0
                
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
        
        # Ensure primary instance broadcasts these updated prices to managed tickers
        try:
            # Count valid prices
            try:
                valid_count = sum(1 for v in (new_prices or {}).values() if (v is not None and v[0] is not None))
            except Exception:
                valid_count = 0
            tray = getattr(self, 'tray_icon', None)
            is_primary = bool(tray and getattr(tray, 'primary_ticker', None) == self)
            if is_primary and tray and valid_count > 0:
                try:
                    now_sec = time_module.time()
                    print(f"[INPLACE.BROADCAST] primary id={id(self)} broadcasting {valid_count} valid prices to tray id={id(tray)}")
                    tray.broadcast_prices(new_prices, now=now_sec)
                    print("[INPLACE.BROADCAST] broadcast complete")
                except Exception:
                    pass
        except Exception:
            pass
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
                # Indicate stale data if applicable
                try:
                    is_stale = bool(getattr(self, 'stale', False))
                except Exception:
                    is_stale = False
                if is_stale:
                    items.append(f"{display_name}: {price:.2f} (stale)")
                    try:
                        colored_print(f"[STALE.SHOW] Rendering stale indicator for ticker id={id(self)} sample={display_name} last_success={getattr(self,'last_successful_fetch_ts',None)} consec_fail={getattr(self,'consecutive_failed_fetches',None)}")
                    except Exception:
                        pass
                else:
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
        self.ticker_pixmap_widths = []
        self.ticker_area_templates = []
        
        # Invalidate bloom cache when ticker content changes
        self.bloom_cache_valid = False
        
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
            is_stale = bool(getattr(self, 'stale', False))
            icon = get_ticker_icon(tkr, icon_size)
            tkr_width = metrics.horizontalAdvance(display_name + " ")
            if price is not None:
                price_text = f"{price:.2f} (stale)" if is_stale else f"{price:.2f}"
            else:
                price_text = "N/A"
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
            
            # Add space for triangle indicator (12px width)
            triangle_width = 12 if (change_text or pct_text) else 0
            sep = "      "
            sep_width = metrics.horizontalAdvance(sep)
            total_width = icon_size + 8 + tkr_width + price_width + (10 + change_width + triangle_width if change_width else 0) + sep_width + 20
            
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
            price_y = tkr_y
            if price is not None and prev is not None:
                if USE_OPT:
                    r, g, b, a = opt.get_price_color_rgba(price, prev)
                    price_color = QtGui.QColor(r, g, b, a)
                elif price > prev:
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
                if USE_OPT:
                    change_percent = opt.calculate_change_percent(price, prev)
                else:
                    change_percent = ((price - prev) / prev) * 100
            
            # Check for glow effect on big price changes
            glow_color = self.get_glow_effect(tkr, change_percent)
            # Disable colored glow when the ticker is stale
            if is_stale:
                glow_color = None
            
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
                # If ticker is stale, render price in gray to indicate staleness
                if is_stale:
                    stale_color = QtGui.QColor(140, 140, 140)
                    painter.setPen(stale_color)
                else:
                    painter.setPen(price_color)
                painter.drawText(x, price_y, price_text)
            else:
                # No 5% glow, use global glow if enabled
                if is_stale:
                    stale_color = QtGui.QColor(140, 140, 140)
                    self.draw_text_with_global_glow(painter, x, price_y, price_text, stale_color, settings=settings)
                else:
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
                if is_stale:
                    # Override change color to gray when stale
                    color = QtGui.QColor(140, 140, 140)
                
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
                    indicator_x = x + 10 + change_text_width + 16  # 16px padding for geometric shapes (more spacing)
                
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
            painter.setFont(self.ticker_font)
            self.draw_text_with_global_glow(painter, x, tkr_y, sep, QtGui.QColor("#00B3FF"), settings=settings)
            painter.end()
            self.ticker_pixmaps.append(pixmap)
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
        self._donate_pixmap = donate_pixmap
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
            is_stale = bool(getattr(self, 'stale', False))
            if price is not None:
                price_text = f"{price:.2f} (stale)" if is_stale else f"{price:.2f}"
            else:
                price_text = "N/A"
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
            triangle_width = 12 if (change_text or pct_text) else 0
            sep = "      "
            sep_width = metrics.horizontalAdvance(sep)
            total_width = icon_size + 8 + tkr_width + price_width + (10 + change_width + triangle_width if change_width else 0) + sep_width + 20

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
            price_y = tkr_y

            if price is not None and prev is not None:
                if USE_OPT:
                    r, g, b, a = opt.get_price_color_rgba(price, prev)
                    price_color = QtGui.QColor(r, g, b, a)
                elif price > prev:
                    price_color = QtGui.QColor("#00FF40")
                elif price < prev:
                    price_color = QtGui.QColor("#FF5555")
                else:
                    price_color = QtGui.QColor("#FFFFFF")
            else:
                price_color = QtGui.QColor("#FFD700")

            change_percent = 0
            if price is not None and prev is not None and prev != 0:
                if USE_OPT:
                    change_percent = opt.calculate_change_percent(price, prev)
                else:
                    change_percent = ((price - prev) / prev) * 100

            glow_color = self.get_glow_effect(tkr, change_percent)
            # Disable colored glow when the ticker is stale
            if is_stale:
                glow_color = None
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
                    indicator_x = x + 10 + change_text_width + 16
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

            painter.setFont(self.ticker_font)
            self.draw_text_with_global_glow(painter, x, tkr_y, sep, QtGui.QColor("#00B3FF"), settings=settings)
            painter.end()

            # Replace existing pixmap entries (market pixmap is index 0)
            target_index = idx + 1
            # Ensure lists are long enough
            if target_index < len(self.ticker_pixmaps):
                self.ticker_pixmaps[target_index] = pixmap
                self.ticker_pixmap_widths[target_index] = total_width
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
        
        bloom_intensity = settings.get("led_bloom_intensity", 100) / 100.0
        
        painter.setCompositionMode(QtGui.QPainter.CompositionMode_Plus)
        painter.setPen(QtCore.Qt.NoPen)
        
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
            
            # Set bloom color based on area type
            if area_type == 'price' or area_type == 'change':
                price, prev = self.prices.get(tkr, (None, None))
                if price is not None and prev is not None:
                    if price > prev:
                        gradient.setColorAt(0, QtGui.QColor(0, 255, 64, int(40 * bloom_intensity)))
                    elif price < prev:
                        gradient.setColorAt(0, QtGui.QColor(255, 85, 85, int(40 * bloom_intensity)))
                    else:
                        gradient.setColorAt(0, QtGui.QColor(255, 255, 255, int(30 * bloom_intensity)))
                else:
                    gradient.setColorAt(0, QtGui.QColor(255, 215, 0, int(30 * bloom_intensity)))
            elif area_type == 'symbol' or area_type == 'market_label':
                gradient.setColorAt(0, QtGui.QColor(0, 179, 255, int(35 * bloom_intensity)))
            elif area_type == 'market_status':
                if tkr == 'OPEN':
                    gradient.setColorAt(0, QtGui.QColor(0, 255, 64, int(40 * bloom_intensity)))
                else:
                    gradient.setColorAt(0, QtGui.QColor(255, 85, 85, int(40 * bloom_intensity)))
            elif area_type == 'donate':
                gradient.setColorAt(0, QtGui.QColor(255, 200, 255, int(35 * bloom_intensity)))
            else:
                gradient.setColorAt(0, QtGui.QColor(200, 220, 255, int(20 * bloom_intensity)))
            
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
            bloom_intensity = settings.get("led_bloom_intensity", 100) / 100.0
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

    def apply_ghosting_effect(self, painter, width, height, settings):
        """
        Apply motion blur/ghosting effect by drawing current content at offset positions.
        Simulates LED persistence and creates trailing effect on moving content.
        OPTIMIZED WITH NUMBA for faster position calculations.
        """
        # Check if ghosting effect is enabled (using cached settings)
        if not settings.get("led_ghosting_effect", True):
            return
        
        # Draw ghost trails by rendering current content at offset positions
        painter.setOpacity(0.6)  # 60% opacity for more visible ghost trail
        
        base_cycle_width = self.get_cycle_width()
        donate_cycle_width = self._donate_pixmap_width + base_cycle_width

        # Use optimized ghosting position calculations
        if USE_OPT:
            ghost_offsets = opt.calculate_ghosting_positions(self.scroll_speed, 3)
            
            # Only use the first ghost offset for performance
            ghost_offset = ghost_offsets[0]
            
            # Use optimized cycle position calculation
            cycle_positions_array = opt.calculate_cycle_positions(
                self.offset + ghost_offset, width, base_cycle_width, donate_cycle_width, 20
            )
            
            # Convert to list format for compatibility
            cycle_positions = []
            for i in range(cycle_positions_array.shape[0]):
                x_pos = cycle_positions_array[i, 0]
                is_donate = cycle_positions_array[i, 1] == 1
                cycle_positions.append((x_pos, is_donate))
        else:
            # Fall back to original implementation
            cycle_positions = []
            ghost_offset = max(2, int(self.scroll_speed * 1.5))
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
                        # Convert float to int for drawPixmap (sub-pixel scrolling uses floats)
                        painter.drawPixmap(int(draw_x), 0, pixmap)
                    draw_x += w
            # Then draw donate message at the end (if this cycle includes it)
            if is_donate and hasattr(self, '_donate_pixmap') and self._donate_pixmap and not self._donate_pixmap.isNull():
                if draw_x + self._donate_pixmap.width() > 0 and draw_x < width:
                    # Convert float to int for drawPixmap
                    painter.drawPixmap(int(draw_x), 0, self._donate_pixmap)
        
        # Reset opacity
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
            # Disable ghosting/motion blur when paused (menu or mouse hover - makes text crisp and readable)
            ghosting_enabled = self._cached_effect_settings.get('ghosting', True) and not self.paused and not self.is_paused
            glass_enabled = self._cached_effect_settings.get('glass', True)
            
            # Debug logging (only once per app run to avoid spam)
            if not hasattr(self, '_effects_debug_logged'):
                self._effects_debug_logged = True
                print(f"[EFFECTS] Applying effects - bloom={bloom_enabled}, ghosting={ghosting_enabled}, glass={glass_enabled}")
            
            # Only call effect functions if their individual settings are enabled
            if bloom_enabled:
                # Apply bloom/glow effect (light bleeding from bright LEDs)
                self.apply_bloom_effect(painter, width, height, cached_settings)
            
            if ghosting_enabled:
                # Apply ghosting effect on top of everything (creates glow effect)
                self.apply_ghosting_effect(painter, width, height, cached_settings)
            
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
        if hasattr(self, 'diagnostic_overlay_timer') and getattr(self, 'diagnostic_overlay_timer', None) and self.diagnostic_overlay_timer.isActive():
            self.diagnostic_overlay_timer.stop()
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
    parser.add_argument("--handoff", dest="handoff", type=int, help=argparse.SUPPRESS)
    
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

    # If started in handoff mode, wait for the old PID to exit to guarantee zero-overlap
    try:
        handoff_pid = getattr(args, 'handoff', None)
        if handoff_pid:
            try:
                colored_print(f"[RESTART] Handoff mode: waiting for old PID {handoff_pid} to exit before continuing")
            except Exception:
                pass
            # Wait up to 30 seconds for either the old process to exit OR for the parent to write a sentinel file
            timeout = 30.0
            sentinel_path = os.path.join(APPDATA_DIR, f"handoff_{handoff_pid}.ready") if 'APPDATA_DIR' in globals() else None
            # Clean up stale sentinel files left by aborted runs: if sentinel exists but the PID is not running
            # or the file is older than a short threshold, remove it to avoid false-positive handoffs.
            try:
                if sentinel_path and os.path.exists(sentinel_path):
                    remove_stale = False
                    try:
                        # If the original PID is not running, the sentinel is stale
                        if not _is_pid_running(int(handoff_pid)):
                            remove_stale = True
                    except Exception:
                        pass
                    try:
                        # Or if the sentinel is older than 10 minutes, consider it stale
                        mtime = os.path.getmtime(sentinel_path)
                        if time.time() - float(mtime) > 600:
                            remove_stale = True
                    except Exception:
                        pass
                    if remove_stale:
                        try:
                            os.remove(sentinel_path)
                            colored_print(f"[RESTART] Removed stale handoff sentinel: {sentinel_path}")
                        except Exception:
                            pass
            except Exception:
                pass
            start_wait = time.time()
            ok = False
            try:
                while time.time() - start_wait < timeout:
                    # If sentinel exists, the parent signalled completion
                    try:
                        if sentinel_path and os.path.exists(sentinel_path):
                            ok = True
                            break
                    except Exception:
                        pass
                    # If PID exited, proceed
                    try:
                        if not _is_pid_running(int(handoff_pid)):
                            ok = True
                            break
                    except Exception:
                        pass
                    time.sleep(0.05)
            except Exception:
                pass

            try:
                if ok:
                    colored_print(f"[RESTART] Handoff cleared for old PID {handoff_pid}; proceeding with startup")
                else:
                    colored_print(f"[RESTART] Timeout waiting for handoff sentinel or old PID {handoff_pid}; proceeding anyway")
            except Exception:
                pass
    except Exception:
        pass

    # Show splash screen IMMEDIATELY before any other initialization (unless disabled)
    splash = None
    if not getattr(args, 'no_splash', False):
        splash = SplashScreen()
        splash.show()
        app.processEvents()  # Force splash to display immediately
    
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

                # Ensure primary refreshes its AppBar to reserve combined space
                try:
                    # Remove primary's existing AppBar registration to force a fresh reservation
                    if ticker_window and sys.platform == 'win32':
                        colored_print("[SECOND TICKER] Refreshing primary AppBar registration to account for secondary ticker")
                        remove_appbar(int(ticker_window.winId()))
                        # Give Windows a short moment, then register a combined physical height
                        QtCore.QTimer.singleShot(300, lambda: reserve_combined_with_keeper(int(ticker_window.winId()), int(second_ticker_window.winId()), get_settings().get("screen_index", 0)))
                except Exception as e:
                    colored_print(f"[SECOND TICKER] Failed to refresh primary AppBar: {e}")

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
