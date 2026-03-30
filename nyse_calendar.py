"""
Pure-Python NYSE trading calendar.
No pandas, no pandas-market-calendars, no Apache Arrow.
Covers NYSE regular holidays for any year.
"""
import datetime

try:
    import zoneinfo
    _ET = zoneinfo.ZoneInfo("America/New_York")
except ImportError:
    # Python < 3.9 fallback
    try:
        import pytz
        _ET = pytz.timezone("America/New_York")
    except ImportError:
        _ET = datetime.timezone(datetime.timedelta(hours=-5))


def _nearest_weekday(date):
    """If date falls on a weekend, shift to nearest weekday (Fri if Sat, Mon if Sun)."""
    wd = date.weekday()
    if wd == 5:   # Saturday -> Friday
        return date - datetime.timedelta(days=1)
    elif wd == 6:  # Sunday -> Monday
        return date + datetime.timedelta(days=1)
    return date


def _easter_sunday(year):
    """Compute Easter Sunday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def _nth_weekday(year, month, weekday, n):
    """Return the nth occurrence of weekday (0=Monday…6=Sunday) in the given month."""
    first = datetime.date(year, month, 1)
    delta = (weekday - first.weekday()) % 7
    return first + datetime.timedelta(days=delta) + datetime.timedelta(weeks=n - 1)


def _last_weekday_of_month(year, month, weekday):
    """Return the last occurrence of weekday in the given month."""
    if month == 12:
        next_month_first = datetime.date(year + 1, 1, 1)
    else:
        next_month_first = datetime.date(year, month + 1, 1)
    delta = (next_month_first.weekday() - weekday) % 7
    return next_month_first - datetime.timedelta(days=delta if delta else 7)


def nyse_holidays(year):
    """Return a frozenset of NYSE holiday dates for the given year."""
    holidays = set()

    # New Year's Day — observed nearest weekday
    holidays.add(_nearest_weekday(datetime.date(year, 1, 1)))

    # MLK Jr. Day — 3rd Monday in January
    holidays.add(_nth_weekday(year, 1, 0, 3))

    # Presidents' Day — 3rd Monday in February
    holidays.add(_nth_weekday(year, 2, 0, 3))

    # Good Friday — Friday before Easter Sunday
    easter = _easter_sunday(year)
    holidays.add(easter - datetime.timedelta(days=2))

    # Memorial Day — last Monday in May
    holidays.add(_last_weekday_of_month(year, 5, 0))

    # Juneteenth National Independence Day — observed from 2022 onward
    if year >= 2022:
        holidays.add(_nearest_weekday(datetime.date(year, 6, 19)))

    # Independence Day — July 4, observed nearest weekday
    holidays.add(_nearest_weekday(datetime.date(year, 7, 4)))

    # Labor Day — 1st Monday in September
    holidays.add(_nth_weekday(year, 9, 0, 1))

    # Thanksgiving Day — 4th Thursday in November
    holidays.add(_nth_weekday(year, 11, 3, 4))

    # Christmas Day — December 25, observed nearest weekday
    holidays.add(_nearest_weekday(datetime.date(year, 12, 25)))

    return frozenset(holidays)


def is_nyse_open():
    """
    Return True if NYSE is currently open for regular-session trading.
    Hours: Monday–Friday 9:30 AM – 4:00 PM Eastern Time, excluding NYSE holidays.
    """
    now = datetime.datetime.now(tz=_ET)
    today = now.date()

    # Weekend
    if today.weekday() >= 5:
        return False

    # Holiday
    if today in nyse_holidays(today.year):
        return False

    # Market hours 9:30 AM – 4:00 PM ET
    t = now.time()
    return datetime.time(9, 30) <= t < datetime.time(16, 0)


def is_nyse_holiday(date=None):
    """Return True if the given date (default: today ET) is an NYSE holiday."""
    if date is None:
        date = datetime.datetime.now(tz=_ET).date()
    return date in nyse_holidays(date.year)
