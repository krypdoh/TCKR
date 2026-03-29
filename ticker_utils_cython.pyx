# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, nonecheck=False
"""
Cython AOT-compiled utilities for TCKR ticker rendering.
Replaces ticker_utils_numba.py with zero JIT warmup overhead.

Build with: python setup_cython.py build_ext --inplace
"""

import numpy as np
cimport numpy as np
from libc.math cimport sqrt, fabs, fmod

DTYPE_F32 = np.float32
DTYPE_I32 = np.int32

CYTHON_AVAILABLE = True
print("[PERF] Cython AOT-compiled ticker utils loaded - instant startup, no JIT warmup")


# ---------------------------------------------------------------------------
# Scalar kernels (cpdef = callable from both C and Python)
# ---------------------------------------------------------------------------

cpdef double calculate_change_percent(double price, double prev_close):
    """Calculate percentage change between current price and previous close."""
    if prev_close == 0.0:
        return 0.0
    return ((price - prev_close) / prev_close) * 100.0


cpdef double calculate_abs_change_percent(double price, double prev_close):
    """Calculate absolute percentage change."""
    if prev_close == 0.0:
        return 0.0
    return fabs((price - prev_close) / prev_close) * 100.0


cpdef bint should_trigger_glow(double price, double prev_close, double threshold=5.0):
    """Determine if a price change should trigger a glow effect."""
    cdef double change_percent = calculate_abs_change_percent(price, prev_close)
    return change_percent >= threshold


cpdef int calculate_glow_alpha(double elapsed_time, double glow_duration=300.0):
    """Calculate glow effect alpha (constant, no fade)."""
    if elapsed_time > glow_duration:
        return 0
    return 50


cpdef int calculate_text_position(int height, int ascent, int descent):
    """Calculate vertical text position for centering."""
    return (height + ascent - descent) // 2


cpdef int calculate_icon_y_position(int height, int icon_size):
    """Calculate vertical position for centering icon."""
    return (height - icon_size) // 2


cpdef int calculate_icon_size(int ticker_height, double scale_factor=0.85):
    """Calculate icon size based on ticker height."""
    return int(ticker_height * scale_factor)


cpdef double calculate_font_size(int ticker_height, double scale_factor=0.7):
    """Calculate font size based on ticker height."""
    cdef double font_size = ticker_height * scale_factor
    if font_size < 8.0:
        font_size = 8.0
    return font_size


cpdef double calculate_scroll_offset(double offset, double scroll_speed,
                                     double total_width, double window_width):
    """Calculate next scroll offset position."""
    cdef double new_offset = offset - scroll_speed
    if new_offset + total_width < 0:
        new_offset = window_width
    return new_offset


cpdef bint should_cleanup_glow(double current_time, double glow_start_time, double duration=300.0):
    """Check if a glow effect should be cleaned up."""
    return (current_time - glow_start_time) > duration


cpdef double calculate_bloom_radius(int rect_width, int rect_height, double scale_factor=0.8):
    """Calculate bloom effect radius for given rectangle dimensions."""
    cdef int m = rect_width if rect_width > rect_height else rect_height
    return m * scale_factor


cpdef int calculate_radial_gradient_alpha(double distance, double radius,
                                          double base_alpha, double falloff_factor=0.5):
    """Calculate alpha value for radial gradient bloom effect."""
    if distance >= radius:
        return 0
    cdef double normalized_dist = distance / radius
    cdef double alpha = base_alpha * (1.0 - normalized_dist ** falloff_factor)
    cdef int result = int(alpha)
    if result < 0:
        return 0
    if result > 255:
        return 255
    return result


cpdef double update_scroll_position_optimized(double offset, double scroll_speed,
                                               double supercycle_width):
    """Optimized scroll position update with wraparound logic."""
    cdef double new_offset = offset - scroll_speed
    if new_offset <= -supercycle_width:
        new_offset += supercycle_width
    return new_offset


cpdef int calculate_power_surge_effect_chance(double current_time):
    """Return surge intensity (>0 means surge active, 0 means no surge)."""
    cdef int surge_seed = int(current_time * 200) % (2**16)
    cdef double surge_chance = (surge_seed % 1000) / 1000.0
    if surge_chance < 0.05:
        return 5 + (surge_seed % 11)
    return 0


cpdef int calculate_scan_line_position(double current_time, int height):
    """Calculate horizontal scan line position for flicker effect."""
    return int((current_time * 200) % height)


cpdef int optimize_pixelation_effect(int original_size, double pixelation_factor=1.5):
    """Calculate optimal pixelation size for icon effects."""
    cdef int pixel_size = int(original_size // pixelation_factor)
    if pixel_size < 16:
        pixel_size = 16
    return pixel_size


cpdef (int, int) calculate_stacked_text_positions(int ticker_height, int small_font_height):
    """Calculate positions for stacked change/percentage text."""
    cdef int stacked_height = small_font_height * 2 + 2
    cdef int stacked_top = (ticker_height - stacked_height) // 2 + small_font_height
    cdef int second_line_y = stacked_top + small_font_height + 2
    return stacked_top, second_line_y


cpdef (int, int, int, int) calculate_color_blend_rgba(int c1r, int c1g, int c1b, int c1a,
                                                       int c2r, int c2g, int c2b, int c2a,
                                                       double blend_factor):
    """Blend two RGBA colors with given blend factor (0.0 to 1.0)."""
    cdef double inv_blend = 1.0 - blend_factor
    cdef int r = int(c1r * inv_blend + c2r * blend_factor)
    cdef int g = int(c1g * inv_blend + c2g * blend_factor)
    cdef int b = int(c1b * inv_blend + c2b * blend_factor)
    cdef int a = int(c1a * inv_blend + c2a * blend_factor)
    return r, g, b, a


cpdef (double, double, double) rgb_to_hsv(int r, int g, int b):
    """Convert RGB to HSV color space."""
    cdef double rf = r / 255.0
    cdef double gf = g / 255.0
    cdef double bf = b / 255.0
    cdef double max_val = rf if rf > gf else gf
    if bf > max_val:
        max_val = bf
    cdef double min_val = rf if rf < gf else gf
    if bf < min_val:
        min_val = bf
    cdef double diff = max_val - min_val
    cdef double v = max_val
    cdef double s = 0.0 if max_val == 0 else diff / max_val
    cdef double h = 0.0
    if diff != 0:
        if max_val == rf:
            h = fmod(60.0 * ((gf - bf) / diff) + 360.0, 360.0)
        elif max_val == gf:
            h = fmod(60.0 * ((bf - rf) / diff) + 120.0, 360.0)
        else:
            h = fmod(60.0 * ((rf - gf) / diff) + 240.0, 360.0)
    return h, s, v


cpdef (int, int, int) hsv_to_rgb(double h, double s, double v):
    """Convert HSV to RGB color space."""
    cdef double c = v * s
    cdef double x = c * (1.0 - fabs(fmod(h / 60.0, 2.0) - 1.0))
    cdef double m = v - c
    cdef double rf, gf, bf
    if h < 60:
        rf, gf, bf = c, x, 0.0
    elif h < 120:
        rf, gf, bf = x, c, 0.0
    elif h < 180:
        rf, gf, bf = 0.0, c, x
    elif h < 240:
        rf, gf, bf = 0.0, x, c
    elif h < 300:
        rf, gf, bf = x, 0.0, c
    else:
        rf, gf, bf = c, 0.0, x
    return int((rf + m) * 255), int((gf + m) * 255), int((bf + m) * 255)


cpdef (double, double, double, double, double, double) calculate_corner_highlight_params(int width, int height):
    """Calculate corner highlight parameters for glass effect."""
    cdef int m = width if width < height else height
    cdef double tl_radius = m * 0.35
    cdef double br_radius = m * 0.2
    return tl_radius, 30.0, 10.0, br_radius, 10.0, 2.0


# ---------------------------------------------------------------------------
# Array-returning functions (def, typed memoryviews)
# ---------------------------------------------------------------------------

def calculate_flicker_brightness_variations(double current_time, int width, int height, int num_spots=15):
    """Calculate LED flicker effect brightness variations."""
    cdef int flicker_seed = int(current_time * 60)
    cdef int seed = flicker_seed
    cdef int i
    cdef long long seed_ll

    variations = np.empty((num_spots, 5), dtype=np.float32)
    cdef np.ndarray[np.float32_t, ndim=2] var = variations

    for i in range(num_spots):
        seed_ll = (<long long>1664525 * seed + 1013904223) % (2**32)
        seed = <int>seed_ll
        var[i, 0] = seed % width

        seed_ll = (<long long>1664525 * seed + 1013904223) % (2**32)
        seed = <int>seed_ll
        var[i, 1] = seed % height

        seed_ll = (<long long>1664525 * seed + 1013904223) % (2**32)
        seed = <int>seed_ll
        var[i, 2] = 20 + (seed % 61)

        seed_ll = (<long long>1664525 * seed + 1013904223) % (2**32)
        seed = <int>seed_ll
        var[i, 3] = 10 + (seed % 21)

        seed_ll = (<long long>1664525 * seed + 1013904223) % (2**32)
        seed = <int>seed_ll
        var[i, 4] = -15 + (seed % 36)

    return variations


def calculate_ghosting_positions(int scroll_speed, int num_positions=3):
    """Calculate ghosting effect position offsets based on scroll speed."""
    positions = np.empty(num_positions, dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=1] pos = positions
    cdef int base_offset = 2 if scroll_speed < 1 else int(scroll_speed * 1.5)
    if base_offset < 2:
        base_offset = 2
    cdef int i
    for i in range(num_positions):
        pos[i] = base_offset + (i * 2)
    return positions


def calculate_cycle_positions(int offset, int width, int base_cycle_width,
                               int donate_cycle_width, int max_cycles=20):
    """Calculate ticker cycle positions for rendering optimization."""
    positions = np.empty((max_cycles, 2), dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=2] pos = positions
    cdef int count = 0
    cdef int x = offset
    cdef int min_cycle_width = base_cycle_width if base_cycle_width < donate_cycle_width else donate_cycle_width
    cdef int est_cycles = (width // min_cycle_width) + 6
    if est_cycles > max_cycles:
        est_cycles = max_cycles
    cdef int i
    for i in range(est_cycles):
        if count >= max_cycles:
            break
        if i % 3 == 0:
            pos[count, 0] = x
            pos[count, 1] = 1
            x += donate_cycle_width
        else:
            pos[count, 0] = x
            pos[count, 1] = 0
            x += base_cycle_width
        count += 1
    return positions[:count]


def batch_calculate_price_changes_optimized(
        np.ndarray[np.float32_t, ndim=2] prices_array,
        np.ndarray[np.float32_t, ndim=2] prev_prices_array):
    """
    Batch calculation of price changes.
    prices_array: (n_stocks, 2) [current_price, prev_close]
    Returns: (n_stocks, 4) [change, change_percent, direction, should_glow]
    """
    cdef int n_stocks = prices_array.shape[0]
    results = np.empty((n_stocks, 4), dtype=np.float32)
    cdef np.ndarray[np.float32_t, ndim=2] res = results
    cdef int i
    cdef float current_price, prev_close, change, change_percent, direction

    for i in range(n_stocks):
        current_price = prices_array[i, 0]
        prev_close = prices_array[i, 1]

        if current_price <= 0 or prev_close <= 0:
            res[i, 0] = 0.0
            res[i, 1] = 0.0
            res[i, 2] = 0.0
            res[i, 3] = 0.0
            continue

        change = current_price - prev_close
        change_percent = (change / prev_close) * 100.0

        if change > 0:
            direction = 1.0
        elif change < 0:
            direction = -1.0
        else:
            direction = 0.0

        res[i, 0] = change
        res[i, 1] = change_percent
        res[i, 2] = direction
        res[i, 3] = 1.0 if fabs(change_percent) >= 5.0 else 0.0

    return results


def parallel_glow_effect_detection(
        np.ndarray[np.float32_t, ndim=1] prices_array,
        np.ndarray[np.float32_t, ndim=1] prev_closes_array,
        double threshold=5.0):
    """Detect which stocks need glow effects."""
    cdef int n_stocks = prices_array.shape[0]
    glow_flags = np.empty(n_stocks, dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=1] flags = glow_flags
    cdef int i
    cdef float current_price, prev_close, change_percent

    for i in range(n_stocks):
        current_price = prices_array[i]
        prev_close = prev_closes_array[i]
        if prev_close > 0:
            change_percent = fabs((current_price - prev_close) / prev_close) * 100.0
            flags[i] = 1 if change_percent >= threshold else 0
        else:
            flags[i] = 0

    return glow_flags


def generate_rainbow_colors(int text_length, int color_count=7):
    """Generate rainbow colors for character-by-character text rendering."""
    cdef np.ndarray[np.int32_t, ndim=2] rainbow_base = np.array([
        [255, 0, 0], [255, 127, 0], [255, 255, 0],
        [0, 255, 0], [0, 179, 255], [75, 0, 130], [148, 0, 211]
    ], dtype=np.int32)

    colors = np.empty((text_length, 3), dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=2] col = colors
    cdef int i, color_idx
    for i in range(text_length):
        color_idx = i % color_count
        col[i, 0] = rainbow_base[color_idx, 0]
        col[i, 1] = rainbow_base[color_idx, 1]
        col[i, 2] = rainbow_base[color_idx, 2]
    return colors


def calculate_character_positions(int text_length,
                                   np.ndarray[np.int32_t, ndim=1] char_widths,
                                   int start_x=20):
    """Calculate x positions for each character in a text string."""
    positions = np.empty(text_length, dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=1] pos = positions
    cdef int x = start_x, i
    for i in range(text_length):
        pos[i] = x
        x += char_widths[i]
    return positions


def calculate_scanline_positions(int width, int height, int frequency=4):
    """Calculate scanline positions for icon processing."""
    cdef int num_lines = (height + frequency - 1) // frequency
    positions = np.empty(num_lines, dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=1] pos = positions
    cdef int i
    for i in range(num_lines):
        pos[i] = i * frequency
    return positions


def calculate_grid_positions(int width, int height, int grid_spacing=6):
    """Calculate LED matrix grid positions for icon overlay."""
    cdef int num_v = (width + grid_spacing - 1) // grid_spacing
    cdef int num_h = (height + grid_spacing - 1) // grid_spacing
    v_positions = np.empty(num_v, dtype=np.int32)
    h_positions = np.empty(num_h, dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=1] vp = v_positions, hp = h_positions
    cdef int i
    for i in range(num_v):
        vp[i] = i * grid_spacing
    for i in range(num_h):
        hp[i] = i * grid_spacing
    return v_positions, h_positions


def batch_calculate_ticker_dimensions(
        np.ndarray[np.float32_t, ndim=2] prices_array,
        int font_width, int icon_size,
        np.ndarray[np.int32_t, ndim=1] change_width_array):
    """Batch calculate ticker display widths."""
    cdef int n_stocks = prices_array.shape[0]
    widths = np.empty(n_stocks, dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=1] w = widths
    cdef int separator_width = font_width * 6
    cdef int base_width = icon_size + 8 + 20
    cdef float current_price
    cdef int ticker_width, price_width, change_width, i

    for i in range(n_stocks):
        current_price = prices_array[i, 0]
        ticker_width = font_width * 5
        if current_price > 0:
            if current_price >= 1000:
                price_width = font_width * 8
            elif current_price >= 100:
                price_width = font_width * 7
            else:
                price_width = font_width * 6
        else:
            price_width = font_width * 3
        change_width = change_width_array[i] if i < len(change_width_array) else 0
        w[i] = base_width + ticker_width + price_width + change_width + separator_width

    return widths


def optimize_rectangle_calculations(
        np.ndarray[np.int32_t, ndim=1] positions_array,
        np.ndarray[np.int32_t, ndim=1] widths_array,
        int height):
    """Batch calculate rectangle positions and dimensions."""
    cdef int n = positions_array.shape[0]
    rectangles = np.empty((n, 4), dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=2] rects = rectangles
    cdef int i
    for i in range(n):
        rects[i, 0] = positions_array[i]
        rects[i, 1] = 0
        rects[i, 2] = widths_array[i]
        rects[i, 3] = height
    return rectangles


def calculate_market_status_colors(bint is_market_open):
    """Calculate market status colors."""
    market_color = np.array([0, 179, 255], dtype=np.int32)
    if is_market_open:
        status_color = np.array([0, 255, 64], dtype=np.int32)
    else:
        status_color = np.array([255, 85, 85], dtype=np.int32)
    return market_color, status_color


def calculate_glass_glare_gradient_stops(int height, int num_stops=5):
    """Calculate gradient stop positions and alpha values for glass glare effect."""
    stops = np.empty((num_stops, 2), dtype=np.float32)
    cdef np.ndarray[np.float32_t, ndim=2] s = stops
    s[0, 0] = 0.0;  s[0, 1] = 45.0
    s[1, 0] = 0.4;  s[1, 1] = 20.0
    s[2, 0] = 0.7;  s[2, 1] = 8.0
    s[3, 0] = 1.0;  s[3, 1] = 0.0
    s[4, 0] = 1.0;  s[4, 1] = 0.0
    return stops


def calculate_distance_field(int width, int height, double center_x, double center_y):
    """Calculate distance field for radial effects."""
    distances = np.empty((height, width), dtype=np.float32)
    cdef np.ndarray[np.float32_t, ndim=2] dist = distances
    cdef int x, y
    cdef double dx, dy
    for y in range(height):
        for x in range(width):
            dx = x - center_x
            dy = y - center_y
            dist[y, x] = sqrt(dx * dx + dy * dy)
    return distances


def batch_font_metrics_approximation(
        np.ndarray[np.int32_t, ndim=1] text_lengths,
        int avg_char_width):
    """Approximate font metrics for batch text processing."""
    cdef int n = text_lengths.shape[0]
    widths = np.empty(n, dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=1] w = widths
    cdef int i
    for i in range(n):
        w[i] = text_lengths[i] * avg_char_width
    return widths


def calculate_texture_line_positions(int height, double start_height_ratio, int spacing):
    """Calculate positions for glass texture lines."""
    cdef int start_y = int(height * start_height_ratio)
    cdef int num_lines = (height - start_y + spacing - 1) // spacing
    if num_lines <= 0:
        return np.empty(0, dtype=np.int32)
    positions = np.empty(num_lines, dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=1] pos = positions
    cdef int i
    for i in range(num_lines):
        pos[i] = start_y + (i * spacing)
    return positions


def vectorized_color_interpolation(
        np.ndarray[np.int32_t, ndim=2] colors1,
        np.ndarray[np.int32_t, ndim=2] colors2,
        np.ndarray[np.float32_t, ndim=1] blend_factors):
    """Vectorized color interpolation for multiple color pairs."""
    cdef int n = colors1.shape[0]
    result = np.empty((n, 3), dtype=np.int32)
    cdef np.ndarray[np.int32_t, ndim=2] res = result
    cdef int i, c
    cdef float blend, inv_blend
    for i in range(n):
        blend = blend_factors[i]
        inv_blend = 1.0 - blend
        for c in range(3):
            res[i, c] = int(colors1[i, c] * inv_blend + colors2[i, c] * blend)
    return result


def fast_luminance_calculation(np.ndarray[np.int32_t, ndim=2] rgb_array):
    """Calculate luminance values for multiple RGB colors."""
    cdef int n = rgb_array.shape[0]
    luminance = np.empty(n, dtype=np.float32)
    cdef np.ndarray[np.float32_t, ndim=1] lum = luminance
    cdef int i
    for i in range(n):
        lum[i] = 0.299 * rgb_array[i, 0] + 0.587 * rgb_array[i, 1] + 0.114 * rgb_array[i, 2]
    return luminance


# ---------------------------------------------------------------------------
# Pure-Python helpers (unchanged from numba version)
# ---------------------------------------------------------------------------

def format_price_change(price, prev_close):
    """Format price change as tuple."""
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
        return (255, 215, 0, 255)
    if price > prev_close:
        return (0, 255, 64, 255)
    elif price < prev_close:
        return (255, 85, 85, 255)
    else:
        return (255, 255, 255, 255)


def get_glow_color_rgba(change_percent):
    """Get RGBA color tuple for glow effect."""
    cdef double abs_change = fabs(change_percent)
    if abs_change < 5.0:
        return None
    if change_percent > 0:
        return (0, 255, 0, 50)
    else:
        return (255, 0, 0, 50)


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
    """Batch calculate price changes for multiple stocks (dict-based)."""
    results = {}
    for ticker, price_data in prices.items():
        if price_data[0] is None or price_data[1] is None:
            continue
        price = float(price_data[0])
        prev_close = float(price_data[1])
        old_data = prev_prices.get(ticker, (None, None))
        if old_data[0] is not None:
            old_price = float(old_data[0])
            should_flash = (price != old_price)
        else:
            should_flash = False
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
        should_glow = abs(pct) >= 5.0
        results[ticker] = (change, pct, direction, should_flash, should_glow)
    return results
