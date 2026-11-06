from datetime import datetime, timezone

from app.core.clock import current_time_context

NOW = datetime(2026, 11, 6, 10, 30, tzinfo=timezone.utc)


def test_formats_in_configured_timezone():
    text = current_time_context("Asia/Karachi", now=NOW)

    assert "Friday, 06 November 2026, 15:30" in text
    assert "UTC+05:00" in text
    assert "2026-11-06" in text


def test_unknown_timezone_falls_back_to_utc():
    text = current_time_context("Mars/Olympus", now=NOW)

    assert "10:30" in text
    assert "UTC" in text