"""
This provides a simple MCP server for managing dates.
Dates are stored in memory and can be added, searched.
"""

import sys
import logging
from datetime import datetime, timedelta
from fastmcp import FastMCP


# configure logger
logger = logging.getLogger("mcp.dates")
h = logging.StreamHandler(sys.stderr)
h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger.addHandler(h)
logger.setLevel(logging.INFO)
logger.propagate = False

# create MCP server
mcp = FastMCP("dates")

# configure date format
FMT = "%Y-%m-%d"


@mcp.tool
def days_between(start: str, end: str) -> int:
    """Calculate the number of days between two dates.

    Args:
        start: The start date.
        end: The end date.

    Returns:
        The number of days between the two dates.
    """
    logger.debug("Calculating days between: start=%s, end=%s", start, end)
    start_date = datetime.strptime(start, FMT)
    end_date = datetime.strptime(end, FMT)
    days = (end_date - start_date).days
    logger.debug("Days between: %s", days)
    return days


@mcp.tool
def next_business_day(date: str, days: int = 1) -> str:
    """Calculate the next business day.

    Args:
        date: The date to calculate the next business day for.
        days: The number of days to add to the date.

    Returns:
        The next business day.
    """
    logger.debug("Calculating next business day: date=%s, days=%s", date, days)
    d = datetime.strptime(date, FMT)
    step = 1 if days >= 0 else -1
    remaining = abs(days)
    while remaining > 0:
        d += timedelta(days=step)
        if d.weekday() < 5:  # 0=Mon..4=Fri
            remaining -= 1
    logger.debug("Next business day: %s +%s(biz) -> %s", date, days, d.strftime(FMT))
    return d.strftime(FMT)


if __name__ == "__main__":
    logger.debug("MCP dates server starting...")
    mcp.run(transport="stdio")
