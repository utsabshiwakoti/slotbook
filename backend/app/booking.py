"""Booking rules that need the database: finding free slots, claiming one, cancelling.

Slot listing and slot claiming share the same code path (slots_for_days), so the API can never
accept a time it wouldn't have offered.
"""

import hashlib
import secrets
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import clock
from .availability import Interval, free_starts, local_day_bounds, shifts_on
from .models import CANCELLED, CONFIRMED, Booking, Business, Service, Staff, TimeOff, WorkingHours


class BookingError(Exception):
    """A rule was broken (slot taken, too late to cancel...). The message is safe to show users."""


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def booking_window(business: Business, now: datetime) -> tuple[date, date]:
    """First and last local dates customers may book right now."""
    today = now.astimezone(ZoneInfo(business.timezone)).date()
    return today, today + timedelta(days=business.max_days_ahead)


def eligible_staff(db: Session, service: Service, staff_id: int | None = None) -> list[Staff]:
    """Active staff of the service's business who perform it (optionally one specific person)."""
    stmt = (
        select(Staff)
        .where(Staff.business_id == service.business_id, Staff.is_active, Staff.services.contains(service))
        .order_by(Staff.id)
    )
    if staff_id is not None:
        stmt = stmt.where(Staff.id == staff_id)
    return list(db.scalars(stmt))


def slots_for_days(
    db: Session,
    business: Business,
    service: Service,
    days: list[date],
    staff_id: int | None = None,
    exclude_booking_id: int | None = None,
) -> dict[date, dict[int, list[datetime]]]:
    """For each date: {staff_id: [free start times]}. Three queries regardless of how many days."""
    tz = ZoneInfo(business.timezone)
    now = clock.now()
    first, last = booking_window(business, now)
    days = sorted(d for d in set(days) if first <= d <= last)
    staff = eligible_staff(db, service, staff_id)
    result: dict[date, dict[int, list[datetime]]] = {d: {} for d in days}
    if not days or not staff:
        return result

    staff_ids = [s.id for s in staff]
    span = Interval(local_day_bounds(days[0], tz).start, local_day_bounds(days[-1], tz).end)

    hours = defaultdict(list)  # (staff_id, weekday) -> [(start, end)]
    for wh in db.scalars(select(WorkingHours).where(WorkingHours.staff_id.in_(staff_ids))):
        hours[(wh.staff_id, wh.weekday)].append((wh.start_time, wh.end_time))

    busy = defaultdict(list)  # staff_id -> [Interval]
    bookings = select(Booking).where(
        Booking.staff_id.in_(staff_ids),
        Booking.status == CONFIRMED,
        Booking.starts_at < span.end,
        Booking.blocked_until > span.start,
    )
    if exclude_booking_id is not None:  # rescheduling: the booking being moved doesn't block itself
        bookings = bookings.where(Booking.id != exclude_booking_id)
    for b in db.scalars(bookings):
        busy[b.staff_id].append(Interval(b.starts_at, b.blocked_until))

    closed = []  # whole-business closures apply to everyone
    time_off = select(TimeOff).where(
        TimeOff.business_id == business.id,
        or_(TimeOff.staff_id.is_(None), TimeOff.staff_id.in_(staff_ids)),
        TimeOff.starts_at < span.end,
        TimeOff.ends_at > span.start,
    )
    for t in db.scalars(time_off):
        interval = Interval(t.starts_at, t.ends_at)
        (closed if t.staff_id is None else busy[t.staff_id]).append(interval)

    earliest = now + timedelta(minutes=business.min_notice_minutes)
    for day in days:
        for person in staff:
            starts = free_starts(
                shifts=shifts_on(day, hours[(person.id, day.weekday())], tz),
                busy=busy[person.id] + closed,
                duration=timedelta(minutes=service.duration_minutes),
                buffer=timedelta(minutes=service.buffer_minutes),
                step=timedelta(minutes=business.slot_interval_minutes),
                earliest=earliest,
            )
            if starts:
                result[day][person.id] = starts
    return result


def merge_slots(by_staff: dict[int, list[datetime]]) -> list[tuple[datetime, list[int]]]:
    """[(start, [staff ids free then])], sorted by time: what an "anyone" booking page shows."""
    merged = defaultdict(list)
    for staff_id, starts in by_staff.items():
        for start in starts:
            merged[start].append(staff_id)
    return sorted(merged.items())


def _claim_staff(
    db: Session,
    business: Business,
    service: Service,
    start: datetime,
    staff_id: int | None,
    exclude_booking_id: int | None = None,
) -> int:
    """Pick and lock a staff member who is free at `start`, or raise BookingError.

    The slot check runs again *after* locking the staff row (SELECT ... FOR UPDATE on Postgres),
    so two requests racing for the same slot are serialised: the second one sees the first
    booking and is refused. On Postgres the exclusion constraint backs this up.
    """
    start = start.astimezone(UTC)
    day = start.astimezone(ZoneInfo(business.timezone)).date()
    offered = slots_for_days(db, business, service, [day], staff_id, exclude_booking_id)[day]
    candidates = [sid for sid, starts in offered.items() if start in starts]
    if not candidates:
        raise BookingError("That time is no longer available. Please pick another slot.")

    if staff_id is None and len(candidates) > 1:
        # "Anyone": spread the work by giving it to whoever has the fewest bookings that day.
        bounds = local_day_bounds(day, ZoneInfo(business.timezone))
        counts = dict(
            db.execute(
                select(Booking.staff_id, func.count())
                .where(
                    Booking.staff_id.in_(candidates),
                    Booking.status == CONFIRMED,
                    Booking.starts_at >= bounds.start,
                    Booking.starts_at < bounds.end,
                )
                .group_by(Booking.staff_id)
            ).all()
        )
        candidates.sort(key=lambda sid: (counts.get(sid, 0), sid))

    for sid in candidates:
        db.execute(select(Staff.id).where(Staff.id == sid).with_for_update())
        still_free = slots_for_days(db, business, service, [day], sid, exclude_booking_id)[day]
        if start in still_free.get(sid, []):
            return sid
    raise BookingError("That time is no longer available. Please pick another slot.")


def create_booking(
    db: Session,
    business: Business,
    service: Service,
    start: datetime,
    staff_id: int | None,
    customer_name: str,
    customer_email: str,
    note: str = "",
) -> tuple[Booking, str]:
    """Book a slot. Returns the booking and the plain manage token (only ever sent to the customer)."""
    chosen = _claim_staff(db, business, service, start, staff_id)
    token = secrets.token_urlsafe(24)
    start = start.astimezone(UTC)
    end = start + timedelta(minutes=service.duration_minutes)
    booking = Booking(
        business_id=business.id,
        service_id=service.id,
        staff_id=chosen,
        customer_name=customer_name.strip(),
        customer_email=customer_email.lower(),
        note=note.strip(),
        starts_at=start,
        ends_at=end,
        blocked_until=end + timedelta(minutes=service.buffer_minutes),
        price_cents=service.price_cents,
        status=CONFIRMED,
        manage_token_hash=hash_token(token),
    )
    db.add(booking)
    _commit_or_conflict(db)
    return booking, token


def reschedule_booking(db: Session, booking: Booking, start: datetime, staff_id: int | None) -> Booking:
    if booking.status != CONFIRMED:
        raise BookingError("This booking was cancelled, so it can't be moved.")
    if booking.starts_at <= clock.now():
        raise BookingError("This appointment has already started.")
    chosen = _claim_staff(db, booking.business, booking.service, start, staff_id, exclude_booking_id=booking.id)
    start = start.astimezone(UTC)
    length = booking.ends_at - booking.starts_at
    buffer = booking.blocked_until - booking.ends_at
    booking.staff_id = chosen
    booking.starts_at = start
    booking.ends_at = start + length
    booking.blocked_until = start + length + buffer
    _commit_or_conflict(db)
    return booking


def cancel_booking(db: Session, booking: Booking, by: str) -> Booking:
    if booking.status == CANCELLED:
        raise BookingError("This booking is already cancelled.")
    if by == "customer" and booking.starts_at <= clock.now():
        raise BookingError("This appointment has already started, so it can't be cancelled online.")
    booking.status = CANCELLED
    booking.cancelled_at = clock.now()
    booking.cancelled_by = by
    db.commit()
    return booking


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:  # the Postgres exclusion constraint caught an overlap
        db.rollback()
        raise BookingError("That time is no longer available. Please pick another slot.") from None
