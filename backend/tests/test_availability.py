"""Unit tests for the pure slot engine: no database involved."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.availability import Interval, free_starts, local_day_bounds, shifts_on

HALIFAX = ZoneInfo("America/Halifax")
MIN = timedelta(minutes=1)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def starts(shifts, busy=(), duration=30, buffer=0, step=30, earliest=utc(2000, 1, 1)):
    return free_starts(
        shifts=shifts, busy=list(busy), duration=duration * MIN, buffer=buffer * MIN,
        step=step * MIN, earliest=earliest,
    )


def test_local_hours_follow_daylight_saving():
    # Halifax is UTC-3 in summer and UTC-4 in winter: the same 9:00 shift moves by an hour in UTC.
    summer = shifts_on(date(2026, 7, 6), [(time(9), time(17))], HALIFAX)[0]
    winter = shifts_on(date(2026, 12, 7), [(time(9), time(17))], HALIFAX)[0]
    assert summer.start == utc(2026, 7, 6, 12)
    assert winter.start == utc(2026, 12, 7, 13)


def test_dst_changeover_day_is_not_24_hours():
    # Clocks went back on Sunday 1 November 2026, so that local day lasted 25 hours.
    day = local_day_bounds(date(2026, 11, 1), HALIFAX)
    assert day.end - day.start == timedelta(hours=25)


def test_appointment_must_end_within_the_shift():
    shift = Interval(utc(2026, 11, 9, 13), utc(2026, 11, 9, 14))  # one hour
    assert starts([shift], duration=45, step=15) == [utc(2026, 11, 9, 13), utc(2026, 11, 9, 13, 15)]


def test_busy_time_blocks_overlapping_starts_but_not_touching_ones():
    shift = Interval(utc(2026, 11, 9, 13), utc(2026, 11, 9, 15))
    booked = Interval(utc(2026, 11, 9, 13, 30), utc(2026, 11, 9, 14))
    # 13:00-13:30 ends exactly when the booking starts and 14:00 starts when it ends: both fine.
    assert starts([shift], [booked]) == [utc(2026, 11, 9, 13), utc(2026, 11, 9, 14), utc(2026, 11, 9, 14, 30)]


def test_buffer_keeps_clean_up_time_free_before_the_next_booking():
    shift = Interval(utc(2026, 11, 9, 13), utc(2026, 11, 9, 15))
    booked = Interval(utc(2026, 11, 9, 14), utc(2026, 11, 9, 14, 30))
    # With a 10-minute buffer, a 13:30 start would run into the 14:00 booking.
    result = starts([shift], [booked], duration=30, buffer=10)
    assert utc(2026, 11, 9, 13, 30) not in result
    assert utc(2026, 11, 9, 13) in result


def test_nothing_before_the_earliest_allowed_start():
    shift = Interval(utc(2026, 11, 9, 13), utc(2026, 11, 9, 15))
    result = starts([shift], earliest=utc(2026, 11, 9, 13, 45))
    assert result == [utc(2026, 11, 9, 14), utc(2026, 11, 9, 14, 30)]


def test_split_shifts_and_reversed_hours():
    shifts = shifts_on(date(2026, 11, 9), [(time(13), time(15)), (time(9), time(10)), (time(12), time(11))], HALIFAX)
    assert len(shifts) == 2  # the reversed 12:00-11:00 entry is ignored
    assert shifts[0].start < shifts[1].start  # sorted
    result = starts(shifts, duration=60, step=60)
    assert [r.astimezone(HALIFAX).hour for r in result] == [9, 13, 14]
