"""Behaviour tests for the public-holidays plugin.

Holiday data is a recorded Nager.Date response (tests/fixtures/DE-<year>.json), so the suite
runs offline. Set HOLIDAYS_LIVE=1 to also run one test against the real API.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "public_holidays_plugin", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


plugin = _load_plugin()
core = plugin.core


def fixture_fetch(country, year):
    path = FIXTURES / f"{country}-{year}.json"
    if not path.exists():
        raise core.HolidayError(f"no fixture for {country} {year}")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def cal():
    return core.HolidayCalendar(fetcher=fixture_fetch)


def test_regional_holiday_applies_only_to_its_region(cal):
    nrw = core.check_day(cal, {"date": "2026-06-04", "country": "DE", "subdivision": "DE-NW"})
    ni = core.check_day(cal, {"date": "2026-06-04", "country": "de", "subdivision": "ni"})
    assert nrw["is_workday"] is False and nrw["holidays"] == ["Fronleichnam"]
    assert ni["is_workday"] is True and ni["subdivision"] == "DE-NI"


def test_without_subdivision_regional_holidays_are_reported_not_applied(cal):
    res = core.check_day(cal, {"date": "2026-06-04", "country": "DE"})
    assert res["is_workday"] is True
    assert res["regional_holidays_not_applied"] == ["Fronleichnam"]
    assert res["note"]


def test_count_workdays_inclusive_month(cal):
    # May 2026: 21 weekdays, minus May 1, Ascension (14th) and Whit Monday (25th).
    res = core.count_workdays(cal, {"start": "2026-05-01", "end": "2026-05-31", "country": "DE", "subdivision": "DE-NI"})
    assert res["workdays"] == 18
    assert res["calendar_days"] == 31
    assert [h["date"] for h in res["holidays_on_workdays"]] == ["2026-05-01", "2026-05-14", "2026-05-25"]


def test_count_and_add_agree(cal):
    added = core.add_workdays(cal, {"start": "2026-03-31", "workdays": 25, "country": "DE", "subdivision": "DE-BY"})
    counted = core.count_workdays(cal, {"start": "2026-04-01", "end": added["result_date"], "country": "DE", "subdivision": "DE-BY"})
    assert counted["workdays"] == 25
    assert core.check_day(cal, {"date": added["result_date"], "country": "DE", "subdivision": "DE-BY"})["is_workday"]


def test_add_workdays_skips_christmas_and_weekend(cal):
    res = core.add_workdays(cal, {"start": "2026-12-23", "workdays": 3, "country": "DE"})
    assert res["result_date"] == "2026-12-29"
    assert [h["date"] for h in res["holidays_skipped"]] == ["2026-12-25"]


def test_add_workdays_backwards_over_easter(cal):
    res = core.add_workdays(cal, {"start": "2026-04-07", "workdays": -1, "country": "DE"})
    assert res["result_date"] == "2026-04-02"


def test_add_workdays_crosses_year_with_regional_holiday(cal):
    de = core.add_workdays(cal, {"start": "2026-12-30", "workdays": 3, "country": "DE"})
    by = core.add_workdays(cal, {"start": "2026-12-30", "workdays": 4, "country": "DE", "subdivision": "DE-BY"})
    assert de["result_date"] == "2027-01-05"
    assert by["result_date"] == "2027-01-07"  # Epiphany (Jan 6) is a holiday in Bavaria


def test_custom_weekend(cal):
    res = core.check_day(cal, {"date": "2026-05-08", "country": "DE", "weekend": ["Friday", "Saturday"]})
    assert res["weekday"] == "Friday" and res["is_weekend"] is True and res["is_workday"] is False


def test_list_filters_by_region(cal):
    everything = core.list_holidays(cal, {"country": "DE", "year": 2026})
    ni = core.list_holidays(cal, {"country": "DE", "year": 2026, "subdivision": "DE-NI"})
    assert everything["count"] > ni["count"]
    assert all(h["nationwide"] or "DE-NI" in h["regions"] for h in ni["holidays"])
    assert "Reformationstag" in {h["local_name"] for h in ni["holidays"]}


@pytest.mark.parametrize("args, fragment", [
    ({"date": "2026-02-30", "country": "DE"}, "ISO date"),
    ({"date": "2026-01-01", "country": "Germany"}, "alpha-2"),
    ({"date": "2026-01-01", "country": "DE", "subdivision": "AT-9"}, "does not belong"),
    ({"date": "2026-01-01", "country": "DE", "types": ["Bogus"]}, "unknown holiday type"),
])
def test_bad_arguments_raise_actionable_errors(cal, args, fragment):
    with pytest.raises(core.HolidayError, match=fragment):
        core.check_day(cal, args)


def test_fetch_is_cached_per_country_and_year():
    calls = []

    def counting(country, year):
        calls.append((country, year))
        return fixture_fetch(country, year)

    cal = core.HolidayCalendar(fetcher=counting)
    core.count_workdays(cal, {"start": "2026-01-01", "end": "2026-12-31", "country": "DE"})
    core.check_day(cal, {"date": "2026-06-04", "country": "DE"})
    assert calls == [("DE", 2026)]


class _Ctx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, toolset, schema, handler, **kwargs):
        assert schema["name"] == name
        self.tools[name] = handler


def test_register_exposes_declared_tools_and_handlers_return_json(monkeypatch):
    ctx = _Ctx()
    plugin.register(ctx)
    manifest_tools = [line.strip()[2:] for line in (ROOT / "plugin.yaml").read_text(encoding="utf-8").splitlines()
                      if line.startswith("  - ")]
    assert sorted(ctx.tools) == sorted(manifest_tools)

    monkeypatch.setattr(plugin, "_CALENDAR", core.HolidayCalendar(fetcher=fixture_fetch))
    ok = json.loads(ctx.tools["workday_check"]({"date": "2026-12-25", "country": "DE"}))
    bad = json.loads(ctx.tools["workday_check"]({"date": "tomorrow", "country": "DE"}))
    assert ok["is_workday"] is False
    assert "error" in bad


@pytest.mark.skipif(os.environ.get("HOLIDAYS_LIVE") != "1", reason="set HOLIDAYS_LIVE=1 to hit date.nager.at")
def test_live_api_matches_fixture():
    assert core.fetch_year("DE", 2026) == fixture_fetch("DE", 2026)
    with pytest.raises(core.HolidayError, match="no data for country"):
        core.fetch_year("XX", 2026)
    with pytest.raises(core.HolidayError, match="no holiday data"):
        core.fetch_year("IN", 2026)  # valid ISO code that Nager.Date does not cover (HTTP 204)


class _Resp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self, _n=-1):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Opener:
    def __init__(self, resp):
        self.resp = resp

    def open(self, req, timeout=None):
        return self.resp


@pytest.mark.parametrize("status, body", [(204, b""), (200, b"[]")])
def test_country_without_data_is_an_error_not_an_empty_calendar(monkeypatch, status, body):
    # Nager.Date answers 204 for ISO codes it does not cover (e.g. IN). Returning an
    # empty list would make every holiday look like a workday.
    monkeypatch.setattr(core, "_OPENER", _Opener(_Resp(status, body)))
    with pytest.raises(core.HolidayError, match="no holiday data"):
        core.fetch_year("IN", 2026)


def test_fetch_parses_a_normal_response(monkeypatch):
    body = (FIXTURES / "DE-2026.json").read_bytes()
    monkeypatch.setattr(core, "_OPENER", _Opener(_Resp(200, body)))
    assert core.fetch_year("DE", 2026) == fixture_fetch("DE", 2026)
