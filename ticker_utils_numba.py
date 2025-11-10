# Alternative Performance Optimization Using Numba (No Compilation Required!)
# This provides similar performance to Cython but uses JIT compilation at runtime

"""
Numba-optimized utilities for TCKR ticker rendering
JIT-compiled performance without requiring C compiler

Install with: pip install numba
"""

try:
    import numba
    from numba import jit, prange
    NUMBA_AVAILABLE = True
    print("[PERF] Numba JIT compilation available - functions will be optimized")
except ImportError:
    print("[PERF] Numba not available (Python 3.14+ not supported yet) - using pure Python fallbacks")
    # Create dummy decorators that do nothing
    def jit(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    
    def prange(*args, **kwargs):
        return range(*args, **kwargs)
    
    NUMBA_AVAILABLE = False

import numpy as np


@jit(nopython=True, cache=True)
def calculate_change_percent(price, prev_close):
    """Calculate percentage change between current price and previous close."""
    if prev_close == 0.0:
        return 0.0
    return ((price - prev_close) / prev_close) * 100.0


@jit(nopython=True, cache=True)
def calculate_abs_change_percent(price, prev_close):
    """Calculate absolute percentage change."""
    if prev_close == 0.0:
        return 0.0
    return abs((price - prev_close) / prev_close) * 100.0


@jit(nopython=True, cache=True)
def should_trigger_glow(price, prev_close, threshold=5.0):
    """Determine if a price change should trigger a glow effect."""
    change_percent = calculate_abs_change_percent(price, prev_close)
    return change_percent >= threshold


@jit(nopython=True, cache=True)
def calculate_glow_alpha(elapsed_time, glow_duration=300.0):
    """Calculate glow effect alpha (constant, no fade)."""
    if elapsed_time > glow_duration:
        return 0
    return 50


@jit(nopython=True, cache=True)
def calculate_text_position(height, ascent, descent):
    """Calculate vertical text position for centering."""
    return (height + ascent - descent) // 2


@jit(nopython=True, cache=True)
def calculate_icon_y_position(height, icon_size):
    """Calculate vertical position for centering icon."""
    return (height - icon_size) // 2


@jit(nopython=True, cache=True)
def calculate_icon_size(ticker_height, scale_factor=0.85):
    """Calculate icon size based on ticker height."""
    return int(ticker_height * scale_factor)


@jit(nopython=True, cache=True)
def calculate_font_size(ticker_height, scale_factor=0.7):
    """Calculate font size based on ticker height."""
    font_size = ticker_height * scale_factor
    if font_size < 8.0:
        font_size = 8.0
    return font_size


@jit(nopython=True, cache=True)
def calculate_scroll_offset(offset, scroll_speed, total_width, window_width):
    """Calculate next scroll offset position."""
    new_offset = offset - scroll_speed
    if new_offset + total_width < 0:
        new_offset = window_width
    return new_offset


@jit(nopython=True, cache=True)
def should_cleanup_glow(current_time, glow_start_time, duration=300.0):
    """Check if a glow effect should be cleaned up."""
    return (current_time - glow_start_time) > duration


def format_price_change(price, prev_close):
    """Format price change as tuple (not JIT-compiled due to tuple return)."""
    change = price - prev_close
    if prev_close != 0.0:
        pct = (change / prev_close) * 100.0
    else:
        pct = 0.0
    
    if change > 0:
        direction = 1
    elif change < 0:
        direction = -1
    else:
        direction = 0
    
    return (change, pct, direction)


def get_price_color_rgba(price, prev_close):
    """Get RGB color tuple for price based on change direction."""
    if prev_close == 0.0:
        return (255, 215, 0, 255)  # Gold
    
    if price > prev_close:
        return (0, 255, 64, 255)  # Green
    elif price < prev_close:
        return (255, 85, 85, 255)  # Red
    else:
        return (255, 255, 255, 255)  # White


def get_glow_color_rgba(change_percent):
    """Get RGBA color tuple for glow effect."""
    abs_change = abs(change_percent)
    
    if abs_change < 5.0:
        return None
    
    if change_percent > 0:
        return (0, 255, 0, 50)  # Green glow
    else:
        return (255, 0, 0, 50)  # Red glow


def get_glow_offsets():
    """Get pre-calculated glow effect pixel offsets."""
    return (
        (-2, -2), (-2, -1), (-2, 0), (-2, 1), (-2, 2),
        (-1, -2), (-1, -1), (-1, 0), (-1, 1), (-1, 2),
        (0, -2), (0, -1), (0, 1), (0, 2),
        (1, -2), (1, -1), (1, 0), (1, 1), (1, 2),
        (2, -2), (2, -1), (2, 0), (2, 1), (2, 2)
    )


def get_subtle_glow_offsets():
    """Get pre-calculated subtle glow offsets."""
    return (
        (-1, -1), (-1, 0), (-1, 1),
        (0, -1), (0, 1),
        (1, -1), (1, 0), (1, 1)
    )


def batch_calculate_changes(prices, prev_prices):
    """Batch calculate price changes for multiple stocks."""
    results = {}
    
    for ticker, price_data in prices.items():
        if price_data[0] is None or price_data[1] is None:
            continue
            
        price = float(price_data[0])
        prev_close = float(price_data[1])
        
        # Get old price if available
        old_data = prev_prices.get(ticker, (None, None))
        if old_data[0] is not None:
            old_price = float(old_data[0])
            should_flash = (price != old_price)
        else:
            should_flash = False
        
        # Calculate change
        change = price - prev_close
        if prev_close != 0.0:
            pct = (change / prev_close) * 100.0
        else:
            pct = 0.0
        
        # Determine direction
        if change > 0:
            direction = 1
        elif change < 0:
            direction = -1
        else:
            direction = 0
        
        # Check if should glow
        should_glow = abs(pct) >= 5.0
        
        results[ticker] = (change, pct, direction, should_flash, should_glow)
    
    return results


@jit(nopython=True, cache=True)
def calculate_flicker_brightness_variations(current_time, width, height, num_spots=15):
    """Calculate LED flicker effect brightness variations for given time and dimensions."""
    # Use time-based seed for consistent but changing flicker
    flicker_seed = int(current_time * 60)  # Changes every ~16ms for 60fps
    
    # Simulate random number generation without actual random module
    # Using linear congruential generator for deterministic randomness
    variations = np.empty((num_spots, 5), dtype=np.float32)  # x, y, width, height, brightness_delta
    
    seed = flicker_seed
    for i in range(num_spots):
        # Linear congruential generator: (a * seed + c) % m
        seed = (1664525 * seed + 1013904223) % (2**32)
        fx = (seed % width)
        
        seed = (1664525 * seed + 1013904223) % (2**32)
        fy = (seed % height)
        
        seed = (1664525 * seed + 1013904223) % (2**32)
        flicker_width = 20 + (seed % 61)  # 20 to 80
        
        seed = (1664525 * seed + 1013904223) % (2**32)
        flicker_height = 10 + (seed % 21)  # 10 to 30
        
        seed = (1664525 * seed + 1013904223) % (2**32)
        brightness_delta = -15 + (seed % 36)  # -15 to 20
        
        variations[i, 0] = fx
        variations[i, 1] = fy
        variations[i, 2] = flicker_width
        variations[i, 3] = flicker_height
        variations[i, 4] = brightness_delta
    
    return variations


@jit(nopython=True, cache=True)
def calculate_power_surge_effect(current_time):
    """Calculate power surge flicker effect parameters."""
    # Deterministic surge calculation based on time
    surge_seed = int(current_time * 200) % (2**16)
    surge_chance = (surge_seed % 1000) / 1000.0  # 0.0 to 0.999
    
    if surge_chance < 0.05:  # 5% chance
        surge_intensity = 5 + (surge_seed % 11)  # 5 to 15
        return True, surge_intensity
    return False, 0


@jit(nopython=True, cache=True)
def calculate_scan_line_position(current_time, height):
    """Calculate horizontal scan line position for flicker effect."""
    return int((current_time * 200) % height)


@jit(nopython=True, cache=True)
def calculate_bloom_radius(rect_width, rect_height, scale_factor=0.8):
    """Calculate bloom effect radius for given rectangle dimensions."""
    return max(rect_width, rect_height) * scale_factor


@jit(nopython=True, cache=True)
def calculate_radial_gradient_alpha(distance, radius, base_alpha, falloff_factor=0.5):
    """Calculate alpha value for radial gradient bloom effect."""
    if distance >= radius:
        return 0
    
    # Normalized distance (0.0 at center, 1.0 at edge)
    normalized_dist = distance / radius
    
    # Calculate falloff using exponential decay
    alpha = base_alpha * (1.0 - normalized_dist**falloff_factor)
    return max(0, min(255, int(alpha)))


@jit(nopython=True, cache=True)
def calculate_ghosting_positions(scroll_speed, num_positions=3):
    """Calculate ghosting effect position offsets based on scroll speed."""
    positions = np.empty(num_positions, dtype=np.int32)
    base_offset = max(2, int(scroll_speed * 1.5))
    
    for i in range(num_positions):
        positions[i] = base_offset + (i * 2)
    
    return positions


@jit(nopython=True, cache=True)
def calculate_cycle_positions(offset, width, base_cycle_width, donate_cycle_width, max_cycles=20):
    """Calculate ticker cycle positions for rendering optimization."""
    positions = np.empty((max_cycles, 2), dtype=np.int32)  # x_position, is_donate
    count = 0
    x = offset
    
    min_cycle_width = min(base_cycle_width, donate_cycle_width)
    est_cycles = min(max_cycles, (width // min_cycle_width) + 6)
    
    for i in range(est_cycles):
        if count >= max_cycles:
            break
            
        if i % 3 == 0:
            positions[count, 0] = x
            positions[count, 1] = 1  # is_donate = True
            x += donate_cycle_width
        else:
            positions[count, 0] = x
            positions[count, 1] = 0  # is_donate = False
            x += base_cycle_width
        
        count += 1
    
    return positions[:count]


@jit(nopython=True, cache=True)
def update_scroll_position_optimized(offset, scroll_speed, supercycle_width):
    """Optimized scroll position update with wraparound logic."""
    new_offset = offset - scroll_speed
    if new_offset <= -supercycle_width:
        new_offset += supercycle_width
    return new_offset


@jit(nopython=True, cache=True)
def batch_calculate_price_changes_optimized(prices_array, prev_prices_array):
    """
    Optimized batch calculation of price changes.
    Input arrays should be shaped as (n_stocks, 2) where columns are [current_price, prev_close]
    Returns array of (n_stocks, 4) with [change, change_percent, direction, should_glow]
    """
    n_stocks = prices_array.shape[0]
    results = np.empty((n_stocks, 4), dtype=np.float32)
    
    for i in range(n_stocks):
        current_price = prices_array[i, 0]
        prev_close = prices_array[i, 1]
        old_price = prev_prices_array[i, 0] if i < prev_prices_array.shape[0] else current_price
        
        # Skip invalid prices
        if current_price <= 0 or prev_close <= 0:
            results[i, 0] = 0.0  # change
            results[i, 1] = 0.0  # change_percent
            results[i, 2] = 0.0  # direction
            results[i, 3] = 0.0  # should_glow
            continue
        
        # Calculate change
        change = current_price - prev_close
        change_percent = (change / prev_close) * 100.0
        
        # Determine direction
        if change > 0:
            direction = 1.0
        elif change < 0:
            direction = -1.0
        else:
            direction = 0.0
        
        # Determine if should glow (>= 5% change)
        should_glow = 1.0 if abs(change_percent) >= 5.0 else 0.0
        
        results[i, 0] = change
        results[i, 1] = change_percent
        results[i, 2] = direction
        results[i, 3] = should_glow
    
    return results


@jit(nopython=True, cache=True)
def calculate_color_blend_rgba(color1_r, color1_g, color1_b, color1_a,
                               color2_r, color2_g, color2_b, color2_a,
                               blend_factor):
    """Blend two RGBA colors with given blend factor (0.0 to 1.0)."""
    inv_blend = 1.0 - blend_factor
    
    r = int(color1_r * inv_blend + color2_r * blend_factor)
    g = int(color1_g * inv_blend + color2_g * blend_factor)
    b = int(color1_b * inv_blend + color2_b * blend_factor)
    a = int(color1_a * inv_blend + color2_a * blend_factor)
    
    return r, g, b, a


@jit(nopython=True, cache=True)
def calculate_glass_glare_gradient_stops(height, num_stops=5):
    """Calculate gradient stop positions and alpha values for glass glare effect."""
    stops = np.empty((num_stops, 2), dtype=np.float32)  # position, alpha
    
    # Main glare area (top 1/3)
    glare_height = height * 0.33
    
    stops[0, 0] = 0.0      # Top
    stops[0, 1] = 45.0     # Strong alpha
    
    stops[1, 0] = 0.4      # 40% down
    stops[1, 1] = 20.0     # Medium alpha
    
    stops[2, 0] = 0.7      # 70% down
    stops[2, 1] = 8.0      # Weak alpha
    
    stops[3, 0] = 1.0      # Bottom of glare
    stops[3, 1] = 0.0      # Transparent
    
    stops[4, 0] = 1.0      # End marker
    stops[4, 1] = 0.0
    
    return stops


@jit(nopython=True, cache=True)
def calculate_corner_highlight_params(width, height):
    """Calculate corner highlight parameters for glass effect."""
    # Top-left corner
    tl_radius = min(width, height) * 0.35
    tl_alpha_center = 30.0
    tl_alpha_mid = 10.0
    
    # Bottom-right corner  
    br_radius = min(width, height) * 0.2
    br_alpha_center = 10.0
    br_alpha_mid = 2.0
    
    return (tl_radius, tl_alpha_center, tl_alpha_mid,
            br_radius, br_alpha_center, br_alpha_mid)


@jit(nopython=True, cache=True, parallel=True)
def calculate_distance_field(width, height, center_x, center_y):
    """Calculate distance field for radial effects using parallel processing."""
    distances = np.empty((height, width), dtype=np.float32)
    
    for y in prange(height):
        for x in prange(width):
            dx = x - center_x
            dy = y - center_y
            distances[y, x] = np.sqrt(dx * dx + dy * dy)
    
    return distances


# Enhanced color utilities with more precision
@jit(nopython=True, cache=True)
def rgb_to_hsv(r, g, b):
    """Convert RGB to HSV color space for advanced color manipulations."""
    r, g, b = r/255.0, g/255.0, b/255.0
    
    max_val = max(r, max(g, b))
    min_val = min(r, min(g, b))
    diff = max_val - min_val
    
    # Value
    v = max_val
    
    # Saturation
    if max_val == 0:
        s = 0
    else:
        s = diff / max_val
    
    # Hue
    if diff == 0:
        h = 0
    elif max_val == r:
        h = (60 * ((g - b) / diff) + 360) % 360
    elif max_val == g:
        h = (60 * ((b - r) / diff) + 120) % 360
    else:  # max_val == b
        h = (60 * ((r - g) / diff) + 240) % 360
    
    return h, s, v


@jit(nopython=True, cache=True)
def hsv_to_rgb(h, s, v):
    """Convert HSV to RGB color space."""
    c = v * s
    x = c * (1 - abs(((h / 60) % 2) - 1))
    m = v - c
    
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    
    r = int((r + m) * 255)
    g = int((g + m) * 255)
    b = int((b + m) * 255)
    
    return r, g, b


@jit(nopython=True, cache=True)
def generate_rainbow_colors(text_length, color_count=7):
    """Generate rainbow colors for character-by-character text rendering."""
    # Pre-defined rainbow colors as RGB tuples
    rainbow_base = np.array([
        [255, 0, 0],    # Red
        [255, 127, 0],  # Orange
        [255, 255, 0],  # Yellow
        [0, 255, 0],    # Green
        [0, 179, 255],  # Blue
        [75, 0, 130],   # Indigo
        [148, 0, 211]   # Violet
    ], dtype=np.int32)
    
    colors = np.empty((text_length, 3), dtype=np.int32)
    for i in range(text_length):
        color_idx = i % color_count
        colors[i] = rainbow_base[color_idx]
    
    return colors


@jit(nopython=True, cache=True)
def calculate_character_positions(text_length, char_widths, start_x=20):
    """Calculate x positions for each character in a text string."""
    positions = np.empty(text_length, dtype=np.int32)
    x = start_x
    
    for i in range(text_length):
        positions[i] = x
        x += char_widths[i]
    
    return positions


@jit(nopython=True, cache=True)
def calculate_scanline_positions(width, height, frequency=4):
    """Calculate scanline positions for icon processing."""
    num_lines = (height + frequency - 1) // frequency  # Ceiling division
    positions = np.empty(num_lines, dtype=np.int32)
    
    for i in range(num_lines):
        positions[i] = i * frequency
    
    return positions


@jit(nopython=True, cache=True)
def calculate_grid_positions(width, height, grid_spacing=6):
    """Calculate LED matrix grid positions for icon overlay."""
    # Calculate vertical lines
    num_v_lines = (width + grid_spacing - 1) // grid_spacing
    v_positions = np.empty(num_v_lines, dtype=np.int32)
    for i in range(num_v_lines):
        v_positions[i] = i * grid_spacing
    
    # Calculate horizontal lines
    num_h_lines = (height + grid_spacing - 1) // grid_spacing
    h_positions = np.empty(num_h_lines, dtype=np.int32)
    for i in range(num_h_lines):
        h_positions[i] = i * grid_spacing
    
    return v_positions, h_positions


@jit(nopython=True, cache=True)
def batch_calculate_ticker_dimensions(prices_array, font_width, icon_size, change_width_array):
    """
    Batch calculate ticker dimensions for multiple stocks.
    prices_array: shape (n_stocks, 2) [current_price, prev_close]
    Returns: array of total widths for each ticker
    """
    n_stocks = prices_array.shape[0]
    widths = np.empty(n_stocks, dtype=np.int32)
    
    separator_width = font_width * 6  # "      " (6 spaces)
    base_width = icon_size + 8 + 20  # icon + padding + margins
    
    for i in range(n_stocks):
        current_price = prices_array[i, 0]
        
        # Calculate ticker symbol width (assume 4 chars average)
        ticker_width = font_width * 5  # "AAPL "
        
        # Calculate price text width (assume 6-8 chars for price)
        if current_price > 0:
            if current_price >= 1000:
                price_width = font_width * 8  # "1234.56"
            elif current_price >= 100:
                price_width = font_width * 7  # "123.45"
            else:
                price_width = font_width * 6  # "12.34"
        else:
            price_width = font_width * 3  # "N/A"
        
        # Add change width if available
        change_width = change_width_array[i] if i < len(change_width_array) else 0
        
        total_width = base_width + ticker_width + price_width + change_width + separator_width
        widths[i] = total_width
    
    return widths


@jit(nopython=True, cache=True)
def calculate_stacked_text_positions(ticker_height, small_font_height):
    """Calculate positions for stacked change/percentage text."""
    stacked_height = small_font_height * 2 + 2
    stacked_top = (ticker_height - stacked_height) // 2 + small_font_height  # Approximation of ascent
    second_line_y = stacked_top + small_font_height + 2
    
    return stacked_top, second_line_y


@jit(nopython=True, cache=True)
def optimize_rectangle_calculations(positions_array, widths_array, height):
    """
    Batch calculate rectangle positions and dimensions.
    positions_array: x positions for each element
    widths_array: widths for each element
    Returns: array of rectangles as [x, y, width, height]
    """
    n_elements = len(positions_array)
    rectangles = np.empty((n_elements, 4), dtype=np.int32)
    
    for i in range(n_elements):
        rectangles[i, 0] = positions_array[i]  # x
        rectangles[i, 1] = 0  # y (always 0 for ticker)
        rectangles[i, 2] = widths_array[i]  # width
        rectangles[i, 3] = height  # height
    
    return rectangles


@jit(nopython=True, cache=True, parallel=True)
def parallel_glow_effect_detection(prices_array, prev_closes_array, threshold=5.0):
    """
    Parallel detection of which stocks need glow effects.
    Uses parallel processing for large portfolios.
    """
    n_stocks = prices_array.shape[0]
    glow_flags = np.empty(n_stocks, dtype=np.int32)
    
    for i in prange(n_stocks):  # Parallel loop
        current_price = prices_array[i]
        prev_close = prev_closes_array[i]
        
        if prev_close > 0:
            change_percent = abs((current_price - prev_close) / prev_close) * 100.0
            glow_flags[i] = 1 if change_percent >= threshold else 0
        else:
            glow_flags[i] = 0
    
    return glow_flags


@jit(nopython=True, cache=True)
def calculate_market_status_colors(is_market_open):
    """Calculate market status colors with optimization."""
    if is_market_open:
        # Market open: blue for "Market:", green for "Open"
        market_color = np.array([0, 179, 255], dtype=np.int32)  # Blue
        status_color = np.array([0, 255, 64], dtype=np.int32)   # Green
    else:
        # Market closed: blue for "Market:", red for "Closed"
        market_color = np.array([0, 179, 255], dtype=np.int32)  # Blue
        status_color = np.array([255, 85, 85], dtype=np.int32)  # Red
    
    return market_color, status_color


@jit(nopython=True, cache=True)
def optimize_pixelation_effect(original_size, pixelation_factor=1.5):
    """Calculate optimal pixelation size for icon effects."""
    pixel_size = max(16, int(original_size // pixelation_factor))
    return pixel_size


@jit(nopython=True, cache=True)
def batch_font_metrics_approximation(text_lengths, avg_char_width):
    """
    Approximate font metrics for batch text processing.
    Useful when exact Qt font metrics aren't needed.
    """
    widths = np.empty(len(text_lengths), dtype=np.int32)
    for i in range(len(text_lengths)):
        widths[i] = text_lengths[i] * avg_char_width
    
    return widths


@jit(nopython=True, cache=True)
def calculate_texture_line_positions(height, start_height_ratio, spacing):
    """Calculate positions for glass texture lines with optimization."""
    start_y = int(height * start_height_ratio)
    num_lines = (height - start_y + spacing - 1) // spacing
    positions = np.empty(num_lines, dtype=np.int32)
    
    for i in range(num_lines):
        positions[i] = start_y + (i * spacing)
    
    return positions


# Advanced memory-efficient operations
@jit(nopython=True, cache=True)
def vectorized_color_interpolation(colors1, colors2, blend_factors):
    """
    Vectorized color interpolation for multiple color pairs.
    colors1, colors2: (n, 3) arrays of RGB values
    blend_factors: (n,) array of blend factors (0.0 to 1.0)
    """
    n = colors1.shape[0]
    result = np.empty((n, 3), dtype=np.int32)
    
    for i in range(n):
        blend = blend_factors[i]
        inv_blend = 1.0 - blend
        
        for c in range(3):  # RGB channels
            result[i, c] = int(colors1[i, c] * inv_blend + colors2[i, c] * blend)
    
    return result


@jit(nopython=True, cache=True)
def fast_luminance_calculation(rgb_array):
    """Calculate luminance values for multiple RGB colors using fast approximation."""
    # Using fast luminance approximation: 0.299*R + 0.587*G + 0.114*B
    n = rgb_array.shape[0]
    luminance = np.empty(n, dtype=np.float32)
    
    for i in range(n):
        r, g, b = rgb_array[i, 0], rgb_array[i, 1], rgb_array[i, 2]
        luminance[i] = 0.299 * r + 0.587 * g + 0.114 * b
    
    return luminance


# Pre-compile functions on import (warms up the JIT cache)
if __name__ != '__main__':
    # Warm up the JIT compiler with dummy calls
    _ = calculate_change_percent(100.0, 95.0)
    _ = calculate_abs_change_percent(100.0, 95.0)
    _ = should_trigger_glow(100.0, 95.0, 5.0)
    _ = calculate_glow_alpha(50.0, 300.0)
    _ = calculate_text_position(60, 20, 5)
    _ = calculate_icon_y_position(60, 50)
    _ = calculate_icon_size(60, 0.85)
    _ = calculate_font_size(60, 0.7)
    _ = calculate_scroll_offset(100, 2, 500, 800)
    _ = should_cleanup_glow(100.0, 50.0, 300.0)
    
    # Warm up new optimized functions
    _ = calculate_flicker_brightness_variations(100.0, 800, 60, 15)
    _ = calculate_power_surge_effect(100.0)
    _ = calculate_scan_line_position(100.0, 60)
    _ = calculate_bloom_radius(100, 50, 0.8)
    _ = calculate_radial_gradient_alpha(25.0, 50.0, 100.0, 0.5)
    _ = calculate_ghosting_positions(2, 3)
    _ = calculate_cycle_positions(0, 800, 500, 600, 20)
    _ = update_scroll_position_optimized(100, 2, 1000)
    
    # Warm up array-based functions
    dummy_prices = np.array([[100.0, 95.0], [50.0, 52.0]], dtype=np.float32)
    dummy_prev = np.array([[98.0, 95.0], [51.0, 52.0]], dtype=np.float32)
    _ = batch_calculate_price_changes_optimized(dummy_prices, dummy_prev)
    
    _ = calculate_color_blend_rgba(255, 0, 0, 255, 0, 255, 0, 255, 0.5)
    _ = calculate_glass_glare_gradient_stops(60, 5)
    _ = calculate_corner_highlight_params(800, 60)
    _ = calculate_distance_field(10, 10, 5, 5)
    _ = rgb_to_hsv(255, 128, 64)
    _ = hsv_to_rgb(30.0, 0.75, 1.0)
    
    # Warm up new advanced functions
    _ = generate_rainbow_colors(30, 7)
    _ = calculate_character_positions(5, np.array([8, 8, 8, 8, 8], dtype=np.int32), 20)
    _ = calculate_scanline_positions(60, 60, 4)
    _ = calculate_grid_positions(60, 60, 6)
    
    dummy_prices = np.array([[100.0, 95.0], [50.0, 52.0]], dtype=np.float32)
    _ = batch_calculate_ticker_dimensions(dummy_prices, 8, 50, np.array([40, 40], dtype=np.int32))
    
    _ = calculate_stacked_text_positions(60, 12)
    _ = optimize_rectangle_calculations(np.array([0, 100], dtype=np.int32), np.array([50, 50], dtype=np.int32), 60)
    _ = parallel_glow_effect_detection(np.array([100.0, 110.0], dtype=np.float32), np.array([95.0, 100.0], dtype=np.float32), 5.0)
    _ = calculate_market_status_colors(True)
    _ = optimize_pixelation_effect(32, 1.5)
    _ = batch_font_metrics_approximation(np.array([4, 6, 8], dtype=np.int32), 8)
    _ = calculate_texture_line_positions(60, 0.33, 15)
    
    # Warm up vectorized operations
    dummy_colors1 = np.array([[255, 0, 0], [0, 255, 0]], dtype=np.int32)
    dummy_colors2 = np.array([[0, 0, 255], [255, 255, 0]], dtype=np.int32)
    dummy_blends = np.array([0.5, 0.3], dtype=np.float32)
    _ = vectorized_color_interpolation(dummy_colors1, dummy_colors2, dummy_blends)
    _ = fast_luminance_calculation(dummy_colors1)

print("[NUMBA] Advanced JIT-compiled utilities loaded and ready (25+ optimized functions)")
