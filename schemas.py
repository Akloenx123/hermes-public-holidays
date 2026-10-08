"""Tool schemas (OpenAI function format) for the public-holidays plugin."""

_COUNTRY = {
    "type": "string",
    "description": "ISO 3166-1 alpha-2 country code, e.g. DE, AT, CH, US, GB.",
}
_SUBDIVISION = {
    "type": "string",
    "description": (
        "Optional ISO 3166-2 region, e.g. DE-NI (Lower Saxony), DE-BY, US-CA. Needed for regional "
        "holidays; without it only nationwide holidays count as days off."
    ),
}
_WEEKEND = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Optional weekend days (weekday names). Default: Saturday and Sunday.",
}
_TYPES = {
    "type": "array",
    "items": {"type": "string", "enum": ["Public", "Bank", "School", "Authorities", "Optional", "Observance"]},
    "description": "Holiday types that count. Default: Public only.",
}

HOLIDAYS_LIST = {
    "name": "holidays_list",
    "description": (
        "List the public holidays of a country (optionally one region) for a year, with dates, weekdays, "
        "local names and which regions observe them. Data: Nager.Date."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "country": _COUNTRY,
            "year": {"type": "integer", "description": "Year, e.g. 2026. Default: current year."},
            "subdivision": _SUBDIVISION,
            "types": _TYPES,
        },
        "required": ["country"],
    },
}

WORKDAY_CHECK = {
    "name": "workday_check",
    "description": (
        "Check whether a date is a working day in a country/region: weekday, weekend, and which "
        "public holiday falls on it. Use instead of guessing from memory."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "ISO date YYYY-MM-DD."},
            "country": _COUNTRY,
            "subdivision": _SUBDIVISION,
            "weekend": _WEEKEND,
            "types": _TYPES,
        },
        "required": ["date", "country"],
    },
}

WORKDAYS_COUNT = {
    "name": "workdays_count",
    "description": (
        "Count working days between two dates (both inclusive), excluding weekends and public holidays, "
        "and list the holidays that fell on weekdays. Max ~10 years per call."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "First day, ISO YYYY-MM-DD (inclusive)."},
            "end": {"type": "string", "description": "Last day, ISO YYYY-MM-DD (inclusive)."},
            "country": _COUNTRY,
            "subdivision": _SUBDIVISION,
            "weekend": _WEEKEND,
            "types": _TYPES,
        },
        "required": ["start", "end", "country"],
    },
}

WORKDAYS_ADD = {
    "name": "workdays_add",
    "description": (
        "Return the date that is N working days after (or before, if negative) a start date, skipping "
        "weekends and public holidays. The start date itself is not counted. Useful for deadlines."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "start": {"type": "string", "description": "Start date, ISO YYYY-MM-DD (not counted)."},
            "workdays": {"type": "integer", "description": "Working days to add; negative goes backwards. |n| <= 2000."},
            "country": _COUNTRY,
            "subdivision": _SUBDIVISION,
            "weekend": _WEEKEND,
            "types": _TYPES,
        },
        "required": ["start", "workdays", "country"],
    },
}
