"""Dashboard numbers. Grouping happens in Python rather than SQL so it works the same on SQLite and
Postgres and can bucket by the business's local time; fine at small-business volumes (a few
thousand rows), and the first thing to push into SQL if it ever got slow."""

from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import clock, schemas
from .availability import local_day_bounds
from .models import CANCELLED, CONFIRMED, Booking, Business


def business_stats(db: Session, business: Business, weeks: int) -> schemas.Stats:
    tz = ZoneInfo(business.timezone)
    now = clock.now()
    today = now.astimezone(tz).date()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(weeks=weeks - 1)
    span_start = local_day_bounds(first_monday, tz).start
    span_end = local_day_bounds(this_monday + timedelta(days=6), tz).end

    rows = db.scalars(
        select(Booking)
        .where(Booking.business_id == business.id, Booking.starts_at >= span_start, Booking.starts_at < span_end)
        .options(selectinload(Booking.service))
    ).all()
    confirmed = [b for b in rows if b.status == CONFIRMED]

    week_count, week_revenue = Counter(), Counter()
    service_count, service_revenue = Counter(), Counter()
    hour_count = Counter()
    for b in confirmed:
        local = b.starts_at.astimezone(tz)
        week = local.date() - timedelta(days=local.weekday())
        week_count[week] += 1
        week_revenue[week] += b.price_cents
        service_count[b.service.name] += 1
        service_revenue[b.service.name] += b.price_cents
        hour_count[local.hour] += 1

    upcoming = db.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.business_id == business.id, Booking.status == CONFIRMED, Booking.starts_at >= now)
    )
    cancelled = sum(1 for b in rows if b.status == CANCELLED)
    hours = range(min(hour_count), max(hour_count) + 1) if hour_count else []

    return schemas.Stats(
        weeks=[
            schemas.WeekStat(week_start=w, bookings=week_count[w], revenue_cents=week_revenue[w])
            for w in (first_monday + timedelta(weeks=i) for i in range(weeks))
        ],
        by_service=[
            schemas.ServiceStat(service=name, bookings=service_count[name], revenue_cents=service_revenue[name])
            for name, _ in service_revenue.most_common()  # biggest earner first
        ],
        by_hour=[schemas.HourStat(hour=h, bookings=hour_count[h]) for h in hours],
        upcoming=upcoming or 0,
        total_bookings=len(confirmed),
        total_revenue_cents=sum(b.price_cents for b in confirmed),
        cancellation_rate=round(cancelled / len(rows), 3) if rows else 0.0,
    )
