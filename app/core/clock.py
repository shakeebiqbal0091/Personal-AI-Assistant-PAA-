import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def current_time_context(tz_name: str, now: datetime | None = None) -> str:
    """Human + machine readable 'now' line injected into the system prompt."""
    try:
        tz, label = ZoneInfo(tz_name), tz_name
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown USER_TZ %r; falling back to UTC.", tz_name)
        tz, label = timezone.utc, "UTC"

    local = (now or datetime.now(tz)).astimezone(tz)
    offset = local.strftime("%z")

    return (
        f"Current date and time: {local:%A, %d %B %Y, %H:%M} "
        f"({label}, UTC{offset[:3]}:{offset[3:]}). "
        f"Today's date is {local:%Y-%m-%d}."
    )