"""public-holidays: holiday lookup and workday math tools for Hermes."""

from __future__ import annotations

import json
import logging

from . import core, schemas

logger = logging.getLogger(__name__)

TOOLSET = "public_holidays"
_CALENDAR = core.HolidayCalendar()


def _wrap(operation):
    def handler(args: dict, **kwargs) -> str:
        try:
            return json.dumps(operation(_CALENDAR, args or {}), ensure_ascii=False)
        except core.HolidayError as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
        except Exception as exc:  # a tool handler must never raise into the agent loop
            logger.exception("public-holidays tool failed")
            return json.dumps({"error": f"public-holidays internal error: {exc}"}, ensure_ascii=False)

    handler.__name__ = operation.__name__
    return handler


_TOOLS = (
    ("holidays_list", schemas.HOLIDAYS_LIST, core.list_holidays, "List public holidays"),
    ("workday_check", schemas.WORKDAY_CHECK, core.check_day, "Is this date a workday?"),
    ("workdays_count", schemas.WORKDAYS_COUNT, core.count_workdays, "Count workdays in a range"),
    ("workdays_add", schemas.WORKDAYS_ADD, core.add_workdays, "Add workdays to a date"),
)


def register(ctx):
    for name, schema, operation, description in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=schema,
            handler=_wrap(operation),
            description=description,
            emoji="📅",
        )
