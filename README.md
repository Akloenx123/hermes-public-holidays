# public-holidays — a Hermes plugin

Public holidays for 200+ countries and their regions, plus workday checks,
workday counts and deadline math, as [Hermes Agent](https://github.com/NousResearch/hermes-agent) tools.

Language models are unreliable at calendar arithmetic ("what is 10 working days
after 23 December in Bavaria?"). This plugin fetches the holiday list once per
country and year and does the counting in code.

## Tools

Toolset `public_holidays`:

| Tool | What it does |
|---|---|
| `holidays_list` | Holidays of a country (optionally one region) for a year: date, weekday, local and English name, regions, types |
| `workday_check` | Is a date a working day? Weekday, weekend flag, holiday names. Without a region it also reports regional holidays that were *not* applied |
| `workdays_count` | Working days between two dates (both inclusive), plus the holidays that fell on weekdays |
| `workdays_add` | The date N working days after (or before, with a negative N) a start date; the start date is not counted |

Common arguments:

- `country`: ISO 3166-1 alpha-2 code (`DE`, `AT`, `CH`, `US`, `GB`, …)
- `subdivision` (optional): ISO 3166-2 region (`DE-NI`, `DE-BY`, `US-CA`, or just `NI` together with `country: DE`).
  Without it only nationwide holidays count as days off, and results say so.
- `weekend` (optional): weekday names, default `["Saturday", "Sunday"]`
- `types` (optional): which holiday types count, default `["Public"]`
  (also `Bank`, `School`, `Authorities`, `Optional`, `Observance`)

Example prompts:

- "Is 4 June 2026 a working day in North Rhine-Westphalia?"
- "How many working days are in December 2026 in Lower Saxony?"
- "The notice period is 15 working days from today, Bavaria. What's the last day?"
- "List the public holidays in Austria next year."

## Install

```bash
hermes plugins install public-holidays      # once it is in the catalog
# or directly from this repository
hermes plugins install https://github.com/Akloenx123/hermes-public-holidays
hermes plugins enable public-holidays
```

No API key, no configuration, no Python dependencies (standard library only).
Requires Hermes 0.21 or newer.

## Disclosure

- **Network:** HTTPS GET requests to `https://date.nager.at/api/v3/PublicHolidays/<year>/<country>`
  ([Nager.Date](https://date.nager.at), a free public holiday API). Only the country code and year
  are sent; no dates, prompts or personal data. Redirects are not followed, each request times out
  after 10 seconds and responses over 1 MB are refused.
- **Storage:** none on disk. Fetched holiday lists are cached in memory for the life of the process.
- **No** credentials, shell commands, subprocesses, background tasks, hooks, telemetry or self-updating code.

## Data and limits

- Holiday data is whatever Nager.Date publishes; it covers roughly the years 2000–2098. Check
  results for legal deadlines against an official source.
- "Workday" means not a weekend day and not a holiday of the selected types. Company holidays,
  half days (24/31 December) and bridge days are not modelled.
- `workdays_count` covers at most ~10 years per call, `workdays_add` at most ±2000 working days.

## Development

```bash
python -m pytest tests                    # offline, uses a recorded Nager.Date response
HOLIDAYS_LIVE=1 python -m pytest tests    # also checks the live API
hermes plugins validate . --install-deps  # the check the Hermes plugin catalog runs
```

## License

MIT, see [LICENSE](LICENSE).
