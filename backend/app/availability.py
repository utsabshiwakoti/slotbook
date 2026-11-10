"""Work out which start times are free. Pure functions: no database, no clock.

All instants are timezone-aware UTC. Working hours are wall-clock times in the business's own
time zone, so they're converted per date: 9:00 in Halifax is 13:00 UTC in summer and 14:00 UTC
in winter, and zoneinfo handles daylight saving for us.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Interval:
    """A half-open range [start, end): a booking ending at 10:00 doesn't clash with one starting at 10:00."""

    start: datetime
    end: datetime

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


def local_day_bounds(day: date, tz: ZoneInfo) -> Interval:
    """Midnight to midnight of a local date, in UTC. Not always 24 hours long (DST days)."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return Interval(start.astimezone(UTC), end.astimezone(UTC))


def shifts_on(day: date, hours: list[tuple[time, time]], tz: ZoneInfo) -> list[Interval]:
    """Turn a day's local working hours into UTC intervals, ignoring empty or reversed ones."""
    result = []
    for start, end in hours:
        if end <= start:
            continue
        result.append(
            Interval(
                datetime.combine(day, start, tzinfo=tz).astimezone(UTC),
                datetime.combine(day, end, tzinfo=tz).astimezone(UTC),
            )
        )
    return sorted(result, key=lambda i: i.start)


def free_starts(
    *,
    shifts: list[Interval],
    busy: list[Interval],
    duration: timedelta,
    buffer: timedelta,
    step: timedelta,
    earliest: datetime,
) -> list[datetime]:
    """Start times where the appointment fits inside a shift and clashes with nothing busy.

    - The appointment itself (duration) must end within the shift.
    - The appointment plus its buffer must not overlap anything busy, so clean-up time after
      this booking can't collide with the next one.
    - Busy intervals for existing bookings already include their own buffer.
    - Starts are offered every `step` from the start of each shift, and never before `earliest`
      (now plus the business's minimum notice).
    """
    starts = []
    for shift in shifts:
        candidate = shift.start
        while candidate + duration <= shift.end:
            occupied = Interval(candidate, candidate + duration + buffer)
            if candidate >= earliest and not any(occupied.overlaps(b) for b in busy):
                starts.append(candidate)
            candidate += step
    return starts
