"""A fictional demo business, rebuilt on every startup so its dates stay current.

Visitors can book on /b/demo and sign in to the dashboard as the read-only demo owner. Bookings
are generated with the same availability engine as real ones, so the data is always valid.
"""

import random
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import clock
from .availability import Interval, free_starts, shifts_on
from .booking import hash_token
from .models import (
    CANCELLED,
    CONFIRMED,
    Booking,
    Business,
    Service,
    Staff,
    TimeOff,
    User,
    WorkingHours,
    staff_services,
)
from .security import hash_password

DEMO_SLUG = "demo"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password"

CUSTOMERS = [
    "Avery Chen", "Jordan Blake", "Maya Patel", "Liam O'Connor", "Noah Martin", "Zoe Fraser",
    "Ethan MacLeod", "Ava Thompson", "Lucas Gill", "Chloe Arsenault", "Owen Boudreau", "Isla Wong",
    "Mason Hart", "Nora Singh", "Caleb Doucette", "Emma Roy", "Felix Grant", "Hana Kim",
]


def wipe_business(db: Session, business_id: int) -> None:
    """Delete a business and everything under it, children first (SQLite doesn't enforce cascades)."""
    staff_ids = select(Staff.id).where(Staff.business_id == business_id)
    db.execute(delete(Booking).where(Booking.business_id == business_id))
    db.execute(delete(TimeOff).where(TimeOff.business_id == business_id))
    db.execute(delete(WorkingHours).where(WorkingHours.staff_id.in_(staff_ids)))
    db.execute(delete(staff_services).where(staff_services.c.staff_id.in_(staff_ids)))
    db.execute(delete(Staff).where(Staff.business_id == business_id))
    db.execute(delete(Service).where(Service.business_id == business_id))
    db.execute(delete(User).where(User.business_id == business_id))
    db.execute(delete(Business).where(Business.id == business_id))


def _week(days: list[int], *shifts: tuple[time, time]) -> list[WorkingHours]:
    return [WorkingHours(weekday=d, start_time=s, end_time=e) for d in days for s, e in shifts]


def seed_demo(db: Session, seed: int = 7) -> Business:
    existing = db.scalar(select(Business.id).where(Business.slug == DEMO_SLUG))
    if existing:
        wipe_business(db, existing)
        db.flush()

    business = Business(
        name="Fernwood Barber Studio",
        slug=DEMO_SLUG,
        description="A fictional demo shop. Book anything you like; the demo resets itself regularly.",
        timezone="America/Halifax",
        slot_interval_minutes=15,
        min_notice_minutes=60,
        max_days_ahead=30,
    )
    db.add(business)
    db.add(
        User(
            email=DEMO_EMAIL, name="Demo Owner", password_hash=hash_password(DEMO_PASSWORD),
            business=business, is_demo=True,
        )
    )

    def service(name, minutes, dollars, buffer=0, description=""):
        s = Service(
            business=business, name=name, duration_minutes=minutes, price_cents=dollars * 100,
            buffer_minutes=buffer, description=description,
        )
        db.add(s)
        return s

    cut = service("Haircut", 30, 35, 5, "Scissor or clipper cut, finished with a style.")
    fade = service("Skin fade", 45, 45, 5, "Tight fade blended to the skin.")
    beard = service("Beard trim", 20, 22, 0, "Shape-up and line-up with a hot towel.")
    combo = service("Haircut + beard", 60, 55, 10, "The full works.")
    kids = service("Kids cut (under 12)", 30, 25, 5)

    morning, afternoon = (time(9), time(12, 30)), (time(13, 30), time(17))
    staff = [
        Staff(business=business, name="Sam", services=[cut, fade, beard, combo, kids],
              hours=_week([1, 2, 3, 4, 5], morning, afternoon)),
        Staff(business=business, name="Priya", services=[cut, fade, combo, kids],
              hours=_week([0, 1, 2, 3, 4], (time(10), time(18)))),
        Staff(business=business, name="Marcus", services=[cut, beard, combo],
              hours=_week([2, 3, 4, 5, 6], (time(11), time(19)))),
    ]
    db.add_all(staff)
    db.flush()

    _fill_bookings(db, business, staff, [cut, fade, beard, combo, kids], random.Random(seed))
    db.commit()
    return business


def _fill_bookings(db, business, staff, services, rng) -> None:
    """About eight weeks of history and two weeks ahead, busier on Fridays and Saturdays."""
    tz = ZoneInfo(business.timezone)
    today = clock.now().astimezone(tz).date()
    start = today - timedelta(days=today.weekday() + 7 * 7)  # Monday, seven weeks before this week
    popularity = [5, 3, 2, 2, 1]  # haircuts far outnumber kids' cuts

    # One staff member is away for a couple of days next week, to show time off in action.
    away_from = datetime_local(today + timedelta(days=8 - today.weekday()), time(0), tz)
    db.add(TimeOff(business_id=business.id, staff_id=staff[1].id, starts_at=away_from,
                   ends_at=away_from + timedelta(days=2), reason="Training course"))

    day = start
    while day <= today + timedelta(days=14):
        fullness = {4: 0.85, 5: 0.9}.get(day.weekday(), 0.55)
        if day > today:
            fullness *= 0.6 - 0.03 * (day - today).days  # the future fills up as it gets closer
        for person in staff:
            shifts = shifts_on(day, [(h.start_time, h.end_time) for h in person.hours if h.weekday == day.weekday()], tz)
            if person is staff[1] and away_from.date() <= day < away_from.date() + timedelta(days=2):
                continue
            busy: list[Interval] = []
            capacity = sum((s.end - s.start for s in shifts), timedelta()) / timedelta(minutes=40)
            for _ in range(int(capacity * max(fullness, 0))):
                service = rng.choices([s for s in services if s in person.services],
                                      [p for s, p in zip(services, popularity) if s in person.services])[0]
                starts = free_starts(
                    shifts=shifts, busy=busy, duration=timedelta(minutes=service.duration_minutes),
                    buffer=timedelta(minutes=service.buffer_minutes), step=timedelta(minutes=15),
                    earliest=datetime_local(day, time(0), tz),
                )
                if not starts:
                    break
                begin = rng.choice(starts)
                end = begin + timedelta(minutes=service.duration_minutes)
                blocked = end + timedelta(minutes=service.buffer_minutes)
                cancelled = rng.random() < 0.07
                if not cancelled:
                    busy.append(Interval(begin, blocked))
                name = rng.choice(CUSTOMERS)
                db.add(Booking(
                    business=business, service=service, staff=person, customer_name=name,
                    customer_email=name.lower().replace(" ", ".").replace("'", "") + "@example.com",
                    starts_at=begin, ends_at=end, blocked_until=blocked, price_cents=service.price_cents,
                    status=CANCELLED if cancelled else CONFIRMED,
                    cancelled_by="customer" if cancelled else None,
                    cancelled_at=begin - timedelta(days=1) if cancelled else None,
                    created_at=begin - timedelta(days=rng.randint(1, 10)),
                    manage_token_hash=hash_token(f"demo-{business.id}-{begin.isoformat()}-{person.id}-{rng.random()}"),
                ))
        day += timedelta(days=1)


def datetime_local(day: date, t: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, t, tzinfo=tz).astimezone(UTC)
