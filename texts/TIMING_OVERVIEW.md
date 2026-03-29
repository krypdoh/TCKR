# Price Update Timing Overview

## How Price Fetching Works

### Initial Startup
1. **Window Initialization**: When the ticker window is created, it starts a QTimer called `update_timer`
2. **First Price Fetch**: An immediate fetch happens during startup to populate the ticker with initial data
3. **Timer Starts**: The `update_timer` begins running with the configured interval (default: 5 minutes, configurable up to 15+ minutes)

### Timer Interval Configuration
- **Base Interval**: Loaded from settings file (`update_interval` in seconds, converted to milliseconds)
- **Default**: 300 seconds (5 minutes) if not configured
- **Smart Adjustment**: The interval dynamically changes based on market hours

### Smart Update Intervals
The `get_smart_update_interval()` function adjusts fetch frequency automatically:

**Market Open** (9:30 AM - 4:00 PM ET, weekdays):
- Uses the configured base interval (e.g., 5 minutes)
- More frequent updates when prices are actively changing

**Market Closed** (nights, weekends):
- Extends to 3x the base interval OR 15 minutes minimum (whichever is larger)
- Reduces API usage when prices aren't changing
- Example: 5-minute base → 15 minutes when closed

**Check Frequency**: Market status is recalculated every 5 minutes to detect market open/close transitions

### Update Cycle Flow
1. **Timer Fires**: Every X seconds (based on smart interval)
2. **`update_prices_inplace()` Called**: Starts the fetch process
3. **Smart Interval Check**: Recalculates and adjusts timer if needed (e.g., market just opened/closed)
4. **Backoff Check**: Skips fetch if in 429 error backoff mode
5. **Background Fetch**: API calls run in a QThreadPool worker to avoid blocking the UI
6. **Completion Handler**: `_handle_prices_inplace()` updates `last_api_update_time` and processes results

### Countdown Overlay Calculation
The "Next Update" countdown overlay shows time until the next fetch:

**Calculation**:
- Current time - Last API update time = Time elapsed
- Timer's current interval - Time elapsed = Time remaining
- Displays as "MM:SS" countdown

**Key Detail**: Uses `update_timer.interval()` (the **actual** current interval) rather than the base configured interval, so it accounts for smart interval adjustments

**Color Coding**:
- **Cyan**: Normal update countdown
- **Orange**: In backoff mode (after rate limiting errors)

### Backoff Mode
If two consecutive API calls return 429 errors (rate limit):
- Enters 5-minute backoff period
- Timer continues firing but skips actual API calls
- Countdown shows orange and displays time until backoff ends
- Automatically resumes normal fetching after backoff expires

### Timing Precision
- Timer fires with ~1 second accuracy (QTimer limitation)
- API calls take 1-3 seconds typically (Yahoo Finance indices only in your case)
- `last_api_update_time` is updated **after** API completion, not when timer fires
- This ensures the countdown accounts for actual API call duration

### Special Events That Reset Timing
- **Stock List Changes**: When adding/removing stocks, `last_api_update_time` resets to current time to prevent immediate re-fetch
- **Window Recreation**: When changing ticker height, the new window loads settings and restores countdown state
- **Settings Changes**: Changing `update_interval` takes effect on the next timer fire
