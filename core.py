"""Holiday lookup and workday arithmetic. Standard library only, no Hermes imports.

Holiday data comes from the public Nager.Date API (https://date.nager.at, no key).
Everything else (weekends, regional filtering, counting, adding) is computed
locally so the model never has to do calendar math in its head.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import threading
import urllib.error
import urllib.request

API_BASE = "https://date.nager.at/api/v3"
USER_AGENT = "hermes-public-holidays/0.1.0 (+https://github.com/Akloenx123/hermes-public-holidays)"
TIMEOUT_S = 10
MAX_BODY_BYTES = 1_000_000
MAX_SPAN_DAYS = 3660  # ~10 years per count request
MAX_ADD_WORKDAYS = 2000
DEFAULT_WEEKEND = (5, 6)  # Saturday, Sunday (Monday == 0)
DEFAULT_TYPES = ("Public",)
KNOWN_TYPES = ("Public", "Bank", "School", "Authorities", "Optional", "Observance")
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_SUBDIVISION_RE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")


class HolidayError(Exception):
    """A user-facing error: the message says what was wrong and how to fix it."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch_year(country: str, year: int) -> list[dict]:
    """Download one country's holidays for one year from Nager.Date."""
    url = f"{API_BASE}/PublicHolidays/{year}/{country}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with _OPENER.open(req, timeout=TIMEOUT_S) as resp:
            status = resp.status
            body = resp.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise HolidayError(
                f"Nager.Date has no data for country {country!r}. Use an ISO 3166-1 alpha-2 code "
                "such as DE, AT, CH, US or GB (see https://date.nager.at/Country)."
            ) from None
        if exc.code == 400:
            raise HolidayError(
                f"Nager.Date does not cover year {year} (it serves roughly the last and next few decades)."
            ) from None
        raise HolidayError(f"Nager.Date returned HTTP {exc.code} for {country} {year}; try again later.") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise HolidayError(f"Could not reach date.nager.at ({reason}); check the network and try again.") from None
    if status == 204 or not body:
        return []
    if len(body) > MAX_BODY_BYTES:
        raise HolidayError("Nager.Date response was unexpectedly large; refusing to parse it.")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HolidayError("Nager.Date returned a response that is not JSON; try again later.") from None
    if not isinstance(data, list):
        raise HolidayError("Nager.Date returned an unexpected response shape.")
    return [h for h in data if isinstance(h, dict) and isinstance(h.get("date"), str)]


class HolidayCalendar:
    """Per-process cache of (country, year) -> raw holiday rows, plus calendar math."""

    def __init__(self, fetcher=fetch_year):
        self._fetch = fetcher
        self._cache: dict[tuple[str, int], list[dict]] = {}
        self._lock = threading.Lock()

    def raw_year(self, country: str, year: int) -> list[dict]:
        key = (country, year)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        rows = self._fetch(country, year)
        with self._lock:
            self._cache[key] = rows
        return rows

    def holidays(self, country: str, year: int, subdivision: str | None, types) -> list[dict]:
        out = []
        for h in self.raw_year(country, year):
            if not _type_matches(h, types):
                continue
            regions = h.get("counties") or []
            nationwide = bool(h.get("global", not regions))
            if subdivision and not nationwide and subdivision not in regions:
                continue
            out.append({
                "date": h["date"],
                "name": h.get("name") or h.get("localName") or "",
                "local_name": h.get("localName") or h.get("name") or "",
                "nationwide": nationwide,
                "regions": [] if nationwide else list(regions),
                "types": list(h.get("types") or []),
            })
        out.sort(key=lambda x: x["date"])
        return out

    def off_days(self, country, years, subdivision, types) -> dict[str, list[str]]:
        """Dates that are non-working holidays -> holiday names. Without a subdivision only
        nationwide holidays count, since regional ones do not apply everywhere."""
        days: dict[str, list[str]] = {}
        for year in years:
            for h in self.holidays(country, year, subdivision, types):
                if subdivision or h["nationwide"]:
                    days.setdefault(h["date"], []).append(h["local_name"] or h["name"])
        return days


def _type_matches(h: dict, types) -> bool:
    row_types = h.get("types") or ["Public"]
    return any(t in types for t in row_types)


# ── argument parsing ─────────────────────────────────────────────────────────

def parse_country(value) -> str:
    code = str(value or "").strip().upper()
    if not _COUNTRY_RE.match(code):
        raise HolidayError("country must be an ISO 3166-1 alpha-2 code like DE, AT, CH, US.")
    return code


def parse_subdivision(value, country: str) -> str | None:
    if value in (None, ""):
        return None
    code = str(value).strip().upper().replace("_", "-")
    if len(code) <= 3 and "-" not in code:
        code = f"{country}-{code}"  # allow "NI" for DE-NI
    if not _SUBDIVISION_RE.match(code):
        raise HolidayError("subdivision must be an ISO 3166-2 code like DE-NI, DE-BY, AT-9 or US-CA.")
    if not code.startswith(country + "-"):
        raise HolidayError(f"subdivision {code} does not belong to country {country}.")
    return code


def parse_date(value, field: str) -> _dt.date:
    try:
        return _dt.date.fromisoformat(str(value or "").strip())
    except ValueError:
        raise HolidayError(f"{field} must be an ISO date YYYY-MM-DD, got {value!r}.") from None


def parse_year(value) -> int:
    if value in (None, ""):
        return _dt.date.today().year
    try:
        year = int(value)
    except (TypeError, ValueError):
        raise HolidayError(f"year must be a number like 2026, got {value!r}.") from None
    if not 1900 <= year <= 2200:
        raise HolidayError("year must be between 1900 and 2200.")
    return year


def parse_types(value) -> tuple[str, ...]:
    if value in (None, "", []):
        return DEFAULT_TYPES
    items = [value] if isinstance(value, str) else list(value)
    lookup = {t.lower(): t for t in KNOWN_TYPES}
    out = []
    for item in items:
        t = lookup.get(str(item).strip().lower())
        if t is None:
            raise HolidayError(f"unknown holiday type {item!r}; use any of {', '.join(KNOWN_TYPES)}.")
        out.append(t)
    return tuple(out)


def parse_weekend(value) -> tuple[int, ...]:
    if value is None:
        return DEFAULT_WEEKEND
    names = {n.lower(): i for i, n in enumerate(WEEKDAY_NAMES)}
    names.update({n[:3].lower(): i for i, n in enumerate(WEEKDAY_NAMES)})
    out = set()
    for item in ([value] if isinstance(value, (str, int)) else value):
        if isinstance(item, int) and 0 <= item <= 6:
            out.add(item)
        elif str(item).strip().lower() in names:
            out.add(names[str(item).strip().lower()])
        else:
            raise HolidayError(f"weekend entries must be weekday names (e.g. Saturday) or 0-6, got {item!r}.")
    if len(out) == 7:
        raise HolidayError("weekend cannot contain all seven days.")
    return tuple(sorted(out))


# ── operations ───────────────────────────────────────────────────────────────

def _day_info(day: _dt.date, weekend, off) -> dict:
    names = off.get(day.isoformat(), [])
    is_weekend = day.weekday() in weekend
    return {
        "date": day.isoformat(),
        "weekday": WEEKDAY_NAMES[day.weekday()],
        "is_weekend": is_weekend,
        "holidays": names,
        "is_workday": not is_weekend and not names,
    }


def _scope_note(subdivision) -> str | None:
    if subdivision:
        return None
    return ("No subdivision given: only nationwide holidays were treated as days off. "
            "Pass subdivision (e.g. DE-NI) to include regional holidays.")


def list_holidays(cal: HolidayCalendar, args: dict) -> dict:
    country = parse_country(args.get("country"))
    subdivision = parse_subdivision(args.get("subdivision"), country)
    year = parse_year(args.get("year"))
    types = parse_types(args.get("types"))
    rows = cal.holidays(country, year, subdivision, types)
    for row in rows:
        row["weekday"] = WEEKDAY_NAMES[_dt.date.fromisoformat(row["date"]).weekday()]
    return {"country": country, "subdivision": subdivision, "year": year, "types": list(types),
            "count": len(rows), "holidays": rows, "source": "date.nager.at"}


def check_day(cal: HolidayCalendar, args: dict) -> dict:
    country = parse_country(args.get("country"))
    subdivision = parse_subdivision(args.get("subdivision"), country)
    day = parse_date(args.get("date"), "date")
    weekend = parse_weekend(args.get("weekend"))
    types = parse_types(args.get("types"))
    off = cal.off_days(country, [day.year], subdivision, types)
    result = {"country": country, "subdivision": subdivision, **_day_info(day, weekend, off)}
    if not subdivision:
        regional = [h["local_name"] for h in cal.holidays(country, day.year, None, types)
                    if h["date"] == day.isoformat() and not h["nationwide"]]
        if regional:
            result["regional_holidays_not_applied"] = regional
        result["note"] = _scope_note(subdivision)
    return result


def count_workdays(cal: HolidayCalendar, args: dict) -> dict:
    country = parse_country(args.get("country"))
    subdivision = parse_subdivision(args.get("subdivision"), country)
    start = parse_date(args.get("start"), "start")
    end = parse_date(args.get("end"), "end")
    if end < start:
        raise HolidayError("end must be on or after start.")
    if (end - start).days > MAX_SPAN_DAYS:
        raise HolidayError(f"range is limited to {MAX_SPAN_DAYS} days per call; split it up.")
    weekend = parse_weekend(args.get("weekend"))
    types = parse_types(args.get("types"))
    off = cal.off_days(country, range(start.year, end.year + 1), subdivision, types)
    workdays = weekend_days = 0
    holidays_on_workdays = []
    day = start
    while day <= end:
        if day.weekday() in weekend:
            weekend_days += 1
        elif day.isoformat() in off:
            holidays_on_workdays.append({"date": day.isoformat(), "names": off[day.isoformat()]})
        else:
            workdays += 1
        day += _dt.timedelta(days=1)
    return {"country": country, "subdivision": subdivision, "start": start.isoformat(), "end": end.isoformat(),
            "inclusive": True, "calendar_days": (end - start).days + 1, "workdays": workdays,
            "weekend_days": weekend_days, "holidays_on_workdays": holidays_on_workdays,
            "note": _scope_note(subdivision)}


def add_workdays(cal: HolidayCalendar, args: dict) -> dict:
    country = parse_country(args.get("country"))
    subdivision = parse_subdivision(args.get("subdivision"), country)
    start = parse_date(args.get("start"), "start")
    try:
        n = int(args.get("workdays"))
    except (TypeError, ValueError):
        raise HolidayError("workdays must be an integer (negative counts backwards).") from None
    if abs(n) > MAX_ADD_WORKDAYS:
        raise HolidayError(f"workdays is limited to ±{MAX_ADD_WORKDAYS}.")
    weekend = parse_weekend(args.get("weekend"))
    types = parse_types(args.get("types"))
    step = _dt.timedelta(days=1 if n >= 0 else -1)
    off: dict[str, list[str]] = {}
    loaded: set[int] = set()
    day, remaining, skipped = start, abs(n), []
    while remaining:
        day += step
        if day.year not in loaded:  # fetch each year only once the walk reaches it
            off.update(cal.off_days(country, [day.year], subdivision, types))
            loaded.add(day.year)
        info = _day_info(day, weekend, off)
        if info["is_workday"]:
            remaining -= 1
        elif info["holidays"] and not info["is_weekend"]:
            skipped.append({"date": info["date"], "names": info["holidays"]})
    return {"country": country, "subdivision": subdivision, "start": start.isoformat(), "workdays": n,
            "result_date": day.isoformat(), "result_weekday": WEEKDAY_NAMES[day.weekday()],
            "start_counted": False, "holidays_skipped": skipped, "note": _scope_note(subdivision)}
