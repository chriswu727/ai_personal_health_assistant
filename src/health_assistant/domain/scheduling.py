"""Time handling for schedules.

Instants are stored in UTC; the originating IANA zone is retained separately so
that later local-calendar rendering and DST reasoning remain possible.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from health_assistant.domain.errors import (
    InvalidTimeRangeError,
    NaiveDatetimeError,
    UnknownTimeZoneError,
)


class Clock(Protocol):
    """Source of the current instant, injected so behavior stays deterministic."""

    def now(self) -> datetime: ...


def require_utc(value: datetime, field: str) -> datetime:
    """Return ``value`` normalized to UTC, rejecting naive datetimes."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise NaiveDatetimeError(field)
    return value.astimezone(UTC)


def require_time_zone(name: str) -> str:
    """Return ``name`` after confirming it resolves against the IANA database."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise UnknownTimeZoneError(name) from exc
    return name


@dataclass(frozen=True, slots=True)
class TimeWindow:
    """A half-open interval ``[start, end)`` anchored to an IANA time zone."""

    start: datetime
    end: datetime
    time_zone: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", require_utc(self.start, "start"))
        object.__setattr__(self, "end", require_utc(self.end, "end"))
        object.__setattr__(self, "time_zone", require_time_zone(self.time_zone))
        if self.end <= self.start:
            raise InvalidTimeRangeError(f"end {self.end.isoformat()} must follow start")

    def overlaps(self, other: "TimeWindow") -> bool:
        """Return whether two half-open intervals share any instant."""
        return self.start < other.end and other.start < self.end

    def contains(self, instant: datetime) -> bool:
        moment = require_utc(instant, "instant")
        return self.start <= moment < self.end

    def local_start(self) -> datetime:
        """Return the start rendered in the originating zone."""
        return self.start.astimezone(ZoneInfo(self.time_zone))
