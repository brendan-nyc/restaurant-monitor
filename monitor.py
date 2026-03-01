#!/usr/bin/env python3
"""
Restaurant Reservation Monitor
================================
Checks Resy and OpenTable every 10 minutes and texts you when a table
matching your criteria becomes available.

Usage:  python monitor.py
Stop:   Press Ctrl+C
"""

import logging
import os
import re
import sys
import time
from datetime import date as date_type, datetime, timedelta

import smtplib
import ssl

import requests
import schedule
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from database import init_db, get_all_restaurants, is_notified, mark_notified

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

load_dotenv("config.env")

RESY_EMAIL          = os.getenv("RESY_EMAIL", "")
RESY_PASSWORD       = os.getenv("RESY_PASSWORD", "")
OPENTABLE_EMAIL     = os.getenv("OPENTABLE_EMAIL", "")
OPENTABLE_PASSWORD  = os.getenv("OPENTABLE_PASSWORD", "")
GMAIL_ADDRESS       = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD  = os.getenv("GMAIL_APP_PASSWORD", "")
ALERT_EMAIL_TO      = os.getenv("ALERT_EMAIL_TO", "")

CHECK_INTERVAL      = 10                  # minutes between checks

# Resy's public web-client API key (same one their website uses)
RESY_API_KEY = "VbWk7s3L4KiK5fzlO7JD3Q5EYolJI7n5"

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Email via Gmail SMTP
# -----------------------------------------------------------------------------

def send_email(message: str) -> None:
    """Send an email alert. Prints to console if Gmail is not configured."""
    if not all([GMAIL_ADDRESS, GMAIL_APP_PASSWORD, ALERT_EMAIL_TO]):
        log.warning("Gmail not configured - printing alert to console instead:")
        print("\n" + "=" * 50)
        print(message)
        print("=" * 50 + "\n")
        return
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            email_body = (
                f"From: {GMAIL_ADDRESS}\r\n"
                f"To: {ALERT_EMAIL_TO}\r\n"
                f"Subject: Table available!\r\n"
                f"\r\n"
                f"{message}"
            )
            server.sendmail(GMAIL_ADDRESS, ALERT_EMAIL_TO, email_body)
        log.info("Email sent to %s", ALERT_EMAIL_TO)
    except Exception as e:
        log.error("Failed to send email: %s", e)

# -----------------------------------------------------------------------------
# Time-window helper
# -----------------------------------------------------------------------------

def in_time_window(slot_time: str, time_start: str, time_end: str) -> bool:
    """Return True if slot_time (HH:MM) falls within [time_start, time_end]."""
    fmt = "%H:%M"
    slot  = datetime.strptime(slot_time,   fmt).time()
    start = datetime.strptime(time_start,  fmt).time()
    end   = datetime.strptime(time_end,    fmt).time()
    return start <= slot <= end

# -----------------------------------------------------------------------------
# Resy
# -----------------------------------------------------------------------------

_resy_token: str | None = None
_resy_venue_cache: dict = {}   # slug -> venue_id  (avoids redundant API calls)

def _resy_headers(include_token: bool = True) -> dict:
    headers = {
        "Authorization": f'ResyAPI api_key="{RESY_API_KEY}"',
        "Origin": "https://resy.com",
        "Referer": "https://resy.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "X-Origin": "https://resy.com",
    }
    if include_token and _resy_token:
        headers["X-Resy-Auth-Token"] = _resy_token
    return headers

def resy_login() -> str:
    """Authenticate with Resy and return the auth token."""
    global _resy_token
    if _resy_token:
        return _resy_token

    log.info("Logging in to Resy...")
    r = requests.post(
        "https://api.resy.com/3/auth/password",
        data={"email": RESY_EMAIL, "password": RESY_PASSWORD},
        headers=_resy_headers(include_token=False),
        timeout=15,
    )
    if not r.ok:
        log.error(
            "Resy login failed (HTTP %d). Check RESY_EMAIL and RESY_PASSWORD in config.env.",
            r.status_code,
        )
        log.debug("Resy login response: %s", r.text[:300])
        r.raise_for_status()
    _resy_token = r.json()["token"]
    log.info("Resy login successful.")
    return _resy_token

def get_resy_venue_id(slug: str, city: str) -> int:
    """Look up Resy's internal venue ID from the URL slug and city code."""
    cache_key = f"{city}/{slug}"
    if cache_key in _resy_venue_cache:
        return _resy_venue_cache[cache_key]

    r = requests.get(
        "https://api.resy.com/3/venue",
        params={"url_slug": slug, "location": city},
        headers=_resy_headers(),
        timeout=15,
    )
    r.raise_for_status()
    venue_id = r.json()["id"]["resy"]
    _resy_venue_cache[cache_key] = venue_id
    log.info("Resolved Resy venue '%s' -> ID %s", slug, venue_id)
    return venue_id

def check_resy(restaurant: dict) -> list[dict]:
    """Return available slots on Resy that match the restaurant's time window."""
    url = restaurant["url"].rstrip("/")

    # Parse: https://resy.com/cities/ny/venues/le-bernardin
    match = re.search(r"resy\.com/cities/([^/]+)/venues/([^/?]+)", url)
    if not match:
        log.error("Cannot parse Resy URL: %s", url)
        log.error("Expected format:  https://resy.com/cities/ny/venues/restaurant-name")
        return []

    city, slug = match.group(1), match.group(2)

    try:
        token    = resy_login()
        venue_id = get_resy_venue_id(slug, city)

        r = requests.get(
            "https://api.resy.com/4/find",
            params={
                "lat":        0,
                "long":       0,
                "day":        restaurant["date"],
                "party_size": restaurant["party_size"],
                "venue_id":   venue_id,
            },
            headers=_resy_headers(),
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()

    except requests.HTTPError as e:
        # Token may have expired -- clear it so the next call re-authenticates
        if e.response is not None and e.response.status_code in (401, 403):
            global _resy_token
            _resy_token = None
        log.error("Resy API error for '%s': %s", restaurant["name"], e)
        return []
    except Exception as e:
        log.error("Resy error for '%s': %s", restaurant["name"], e)
        return []

    slots = []
    for venue in data.get("results", {}).get("venues", []):
        for slot in venue.get("slots", []):
            # Slot start time format: "2026-03-15 19:00:00"
            raw = slot.get("date", {}).get("start", "")
            if not raw:
                continue
            time_part = raw.split(" ")[1][:5]   # -> "19:00"
            if in_time_window(time_part, restaurant["time_start"], restaurant["time_end"]):
                booking_url = (
                    f"https://resy.com/cities/{city}/venues/{slug}"
                    f"?date={restaurant['date']}&seats={restaurant['party_size']}"
                )
                slots.append({"time": time_part, "url": booking_url})

    return slots

# -----------------------------------------------------------------------------
# OpenTable
# -----------------------------------------------------------------------------

_ot_session: requests.Session | None = None
_ot_rid_cache: dict = {}   # url -> restaurant id

def get_opentable_session() -> requests.Session:
    """Return an authenticated (or at least cookie-holding) OpenTable session."""
    global _ot_session
    if _ot_session:
        return _ot_session

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })

    # Load the homepage to collect session cookies
    try:
        session.get("https://www.opentable.com", timeout=15)
    except Exception:
        pass

    _ot_session = session
    return session

def get_opentable_rid(url: str, session: requests.Session) -> int:
    """Extract the numeric restaurant ID (rid) from an OpenTable page URL."""
    if url in _ot_rid_cache:
        return _ot_rid_cache[url]

    # Some profile URLs already embed the ID: /restaurant/profile/12345
    m = re.search(r"/restaurant/profile/(\d+)", url)
    if m:
        rid = int(m.group(1))
        _ot_rid_cache[url] = rid
        return rid

    # Fetch the page; retry once on timeout since OpenTable can be slow
    log.info("Fetching OpenTable page to find restaurant ID: %s", url)
    last_exc: Exception | None = None
    for attempt in range(1, 3):
        try:
            r = session.get(url, timeout=(5, 15), allow_redirects=True)
            r.raise_for_status()
            last_exc = None
            break
        except requests.Timeout as e:
            last_exc = e
            log.warning("OpenTable page fetch timed out (attempt %d/2) — retrying...", attempt)
            time.sleep(2)
        except Exception as e:
            raise ValueError(f"Could not load OpenTable page '{url}': {e}") from e
    if last_exc is not None:
        raise ValueError(f"Could not load OpenTable page '{url}': {last_exc}") from last_exc

    # OpenTable often redirects slug URLs to a numeric profile URL — check that first
    m = re.search(r"/restaurant/profile/(\d+)", r.url)
    if m:
        rid = int(m.group(1))
        _ot_rid_cache[url] = rid
        log.info("Resolved OpenTable restaurant ID from redirect URL: %d", rid)
        return rid

    # Try several patterns that OpenTable has used over time
    for pattern in [
        r'"rid"\s*:\s*(\d+)',
        r'"restaurantId"\s*:\s*(\d+)',
        r'data-rid="(\d+)"',
        r'"restaurant_id"\s*:\s*(\d+)',
    ]:
        m = re.search(pattern, r.text)
        if m:
            rid = int(m.group(1))
            _ot_rid_cache[url] = rid
            log.info("Resolved OpenTable restaurant ID: %d", rid)
            return rid

    # Last resort: check the canonical <link> tag for a numeric segment
    soup = BeautifulSoup(r.text, "html.parser")
    canonical = soup.find("link", rel="canonical")
    if canonical:
        m = re.search(r"/(\d+)(?:/|$)", canonical.get("href", ""))
        if m:
            rid = int(m.group(1))
            _ot_rid_cache[url] = rid
            log.info("Resolved OpenTable restaurant ID from canonical URL: %d", rid)
            return rid

    raise ValueError(
        f"Could not find restaurant ID for '{url}'.\n"
        "Tip: Try using the direct profile URL, e.g. "
        "https://www.opentable.com/restaurant/profile/12345"
    )

def check_opentable(restaurant: dict) -> list[dict]:
    """Return available slots on OpenTable that match the restaurant's time window."""
    session = get_opentable_session()

    try:
        rid = get_opentable_rid(restaurant["url"], session)
    except ValueError as e:
        log.error("%s", e)
        return []

    try:
        r = session.get(
            "https://www.opentable.com/widget/reservation/counts",
            params={
                "rid":           rid,
                "party_size":    restaurant["party_size"],
                "start_date":    restaurant["date"],
                "end_date":      restaurant["date"],
                "restaurant_id": rid,
                "type":          "both",
                "lang":          "en-US",
            },
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error("OpenTable API error for '%s': %s", restaurant["name"], e)
        return []

    slots = []
    # Response shape: {"availability": {"2026-03-15": [{"time": "19:00:00"}, ...]}}
    day_slots = data.get("availability", {}).get(restaurant["date"], [])
    for slot in day_slots:
        raw_time = slot.get("time", "")    # e.g. "19:00:00"
        if not raw_time:
            continue
        time_part = raw_time[:5]           # -> "19:00"
        if in_time_window(time_part, restaurant["time_start"], restaurant["time_end"]):
            booking_url = (
                f"https://www.opentable.com/restaurant/profile/{rid}/reserve"
                f"?covers={restaurant['party_size']}"
                f"&dateTime={restaurant['date']}T{raw_time}"
            )
            slots.append({"time": time_part, "url": booking_url})

    return slots

# -----------------------------------------------------------------------------
# Date expansion (specific date vs. recurring day-of-week pattern)
# -----------------------------------------------------------------------------

_DAY_ABBREVS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def expand_dates(restaurant: dict) -> list[str]:
    """Return the list of YYYY-MM-DD strings to check for this restaurant."""
    if restaurant.get("days_of_week"):
        abbrevs = [d.strip().lower() for d in restaurant["days_of_week"].split(",")]
        target_weekdays = {_DAY_ABBREVS[d] for d in abbrevs if d in _DAY_ABBREVS}
        look_ahead = int(restaurant.get("look_ahead_days") or 45)
        today = date_type.today()
        return [
            (today + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(look_ahead + 1)
            if (today + timedelta(days=i)).weekday() in target_weekdays
        ]
    if restaurant.get("date"):
        return [restaurant["date"]]
    return []


# -----------------------------------------------------------------------------
# Resy reservations
# -----------------------------------------------------------------------------

_res_cache: list[dict] = []
_res_cache_time: float = 0.0
_RES_CACHE_TTL = 300  # seconds


def fetch_resy_reservations() -> list[dict]:
    """Return the user's upcoming Resy reservations (cached for 5 minutes)."""
    global _res_cache, _res_cache_time

    if not RESY_EMAIL:
        return []

    if time.time() - _res_cache_time < _RES_CACHE_TTL:
        return _res_cache

    try:
        resy_login()
        r = requests.get(
            "https://api.resy.com/3/user/reservations",
            params={"limit": 20, "offset": 0, "type": "upcoming"},
            headers=_resy_headers(),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("Could not fetch Resy reservations: %s", e)
        return _res_cache  # return stale cache rather than nothing

    reservations = []
    for res in data.get("reservations", []):
        try:
            venue   = res.get("venue", {})
            details = res.get("details", {})
            raw_time = details.get("time_slot", "")
            reservations.append({
                "name":       venue.get("name", ""),
                "date":       details.get("day", ""),
                "time":       raw_time[:5] if raw_time else "",
                "party_size": details.get("party_size", ""),
                "seat_type":  details.get("seat_type", ""),
            })
        except Exception:
            continue

    _res_cache = sorted(reservations, key=lambda x: (x["date"], x["time"]))
    _res_cache_time = time.time()
    return _res_cache


# -----------------------------------------------------------------------------
# Watchlist
# -----------------------------------------------------------------------------

def load_watchlist() -> list[dict]:
    """Return all restaurants from the database."""
    rows = get_all_restaurants()
    log.info("Watchlist: %d restaurant(s) loaded.", len(rows))
    return rows

# -----------------------------------------------------------------------------
# Main check loop
# -----------------------------------------------------------------------------

def check_all() -> None:
    log.info("---  Running availability check  ---")
    watchlist = load_watchlist()

    for restaurant in watchlist:
        dates = expand_dates(restaurant)
        if not dates:
            log.warning("Skipping '%s' — no date or days_of_week set.", restaurant["name"])
            continue

        for check_date in dates:
            r = {**restaurant, "date": check_date}
            log.info(
                "Checking %-30s  [%s]  %s  party of %d  %s-%s",
                r["name"], r["platform"], r["date"],
                r["party_size"], r["time_start"], r["time_end"],
            )

            if r["platform"] == "resy":
                available = check_resy(r)
            else:
                available = check_opentable(r)

            if not available:
                log.info("  - No availability in window.")
                continue

            for slot in available:
                key = f"{r['name']}|{r['date']}|{slot['time']}"

                if is_notified(key):
                    log.info("  - Already notified about %s at %s -- skipping.", r["name"], slot["time"])
                    continue

                message = (
                    f"Table available!\n"
                    f"{r['name']}\n"
                    f"{r['date']} at {slot['time']}\n"
                    f"Party of {r['party_size']}\n"
                    f"Book now: {slot['url']}"
                )
                log.info("  - MATCH: %s at %s -- sending email!", r["name"], slot["time"])
                send_email(message)
                mark_notified(key)

    log.info("---  Check complete  ---\n")

# -----------------------------------------------------------------------------
# Startup validation
# -----------------------------------------------------------------------------

def validate_config() -> None:
    """Print clear error messages and exit if required config is missing."""
    errors = []

    if not RESY_EMAIL and not OPENTABLE_EMAIL:
        errors.append("Set at least RESY_EMAIL (and RESY_PASSWORD) in config.env")

    if not GMAIL_ADDRESS:
        errors.append("GMAIL_ADDRESS is missing from config.env")
    if not GMAIL_APP_PASSWORD:
        errors.append("GMAIL_APP_PASSWORD is missing from config.env")
    if not ALERT_EMAIL_TO:
        errors.append("ALERT_EMAIL_TO is missing from config.env")

    if errors:
        print("\n  ERROR - Missing configuration in config.env:\n")
        for msg in errors:
            print(f"    * {msg}")
        print("\n  See README.md for setup instructions.\n")
        sys.exit(1)

# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    print()
    print("  Restaurant Reservation Monitor")
    print("  ================================")
    print(f"  Checking every {CHECK_INTERVAL} minutes")
    print(f"  Alerts -> {ALERT_EMAIL_TO or '(console - Gmail not configured)'}")
    print()

    validate_config()
    init_db()

    # Run an immediate check, then schedule repeating checks
    check_all()
    schedule.every(CHECK_INTERVAL).minutes.do(check_all)

    log.info("Monitoring started. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n  Stopped.")
