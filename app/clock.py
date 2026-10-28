"""Controllable clock. All code reads time through Clock."""

from __future__ import annotations

from datetime import date, datetime, timezone


class Clock:
    """Production: system clock, or fixed DEMO_TODAY when set. Tests: controllable."""

    def __init__(self, today: date | str | None = None) -> None:
        self._today: date | None
        if today is None:
            self._today = None
        elif isinstance(today, date):
            self._today = today
        else:
            self._today = date.fromisoformat(today)

    def today(self) -> date:
        if self._today is not None:
            return self._today
        return datetime.now(timezone.utc).date()

    def now(self) -> datetime:
        if self._today is not None:
            return datetime(
                self._today.year,
                self._today.month,
                self._today.day,
                tzinfo=timezone.utc,
            )
        return datetime.now(timezone.utc)

    def set_today(self, value: date | str) -> None:
        if isinstance(value, str):
            self._today = date.fromisoformat(value)
        else:
            self._today = value

    def clear(self) -> None:
        """Use the real system clock."""
        self._today = None


def clock_from_settings(demo_today: str | None) -> Clock:
    if demo_today:
        return Clock(today=demo_today)
    return Clock()
