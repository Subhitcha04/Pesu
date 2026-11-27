"""Time handling (fix A3).

v0.1 bug: the container runs in UTC and used naive datetime.now(), so "today"
rolled over at 05:30 IST, the browser parsed naive UTC strings as local time
(5.5 h off), and per-day buckets used the UTC date.

Rules now:
- Every stored timestamp is timezone-aware UTC, written as 'YYYY-MM-DDTHH:MM:SSZ'.
  One fixed format means plain string comparison in SQL is also time comparison.
- "Today" and per-day buckets are computed in settings.tz (PESU_TZ, default Asia/Kolkata).
- now() is the only clock; tests replace it with set_clock().
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from .config import settings

_clock: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731


def set_clock(fn: Callable[[], datetime] | None) -> None:
    """Tests only: pin the clock. Pass None to restore the real clock."""
    global _clock
    _clock = fn or (lambda: datetime.now(UTC))


def now() -> datetime:
    return _clock().astimezone(UTC)


def iso(dt: datetime) -> str:
    """UTC ISO string with a Z suffix and second precision. Pitfall: never store naive times."""
    if dt.tzinfo is None:
        raise ValueError("naive datetime: attach a timezone first")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return iso(now())


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def local_day(ts: str) -> str:
    """The calendar day (in PESU_TZ) on which a stored UTC timestamp happened."""
    return parse(ts).astimezone(settings.tz).date().isoformat()


def today_local() -> date:
    return now().astimezone(settings.tz).date()


def day_start_utc(day: date) -> str:
    """UTC ISO string of local midnight that starts `day`."""
    return iso(datetime.combine(day, time.min, tzinfo=settings.tz))


def last_n_days(n: int) -> list[date]:
    today = today_local()
    return [today - timedelta(days=n - 1 - i) for i in range(n)]
