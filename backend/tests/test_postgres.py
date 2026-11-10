"""Concurrency tests that only mean something on a real Postgres server.

Run with:  TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/slotbook_test pytest tests/test_postgres.py
(CI starts a Postgres service and sets this.) The database is wiped.
"""

import os
import threading
from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.booking import BookingError, create_booking
from app.database import Base, _normalise_url
from app.models import Booking, Business, Service, Staff, WorkingHours

URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="set TEST_DATABASE_URL to run Postgres tests")

TUE_9AM = datetime(2026, 11, 10, 13, 0, tzinfo=UTC)


@pytest.fixture()
def pg():
    engine = create_engine(_normalise_url(URL), pool_size=10)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)  # also creates the exclusion constraint
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        business = Business(name="PG", slug="pg", timezone="America/Halifax")
        service = Service(business=business, name="Cut", duration_minutes=30, price_cents=1000)
        staff = Staff(business=business, name="Sam", services=[service],
                      hours=[WorkingHours(weekday=1, start_time=time(9), end_time=time(17))])
        db.add_all([business, service, staff])
        db.commit()
        ids = (business.id, service.id, staff.id)
    yield Session, ids
    engine.dispose()


def test_database_rejects_overlapping_bookings_even_without_app_checks(pg):
    Session, (business_id, service_id, staff_id) = pg

    def raw(start, token, status="confirmed"):
        return Booking(
            business_id=business_id, service_id=service_id, staff_id=staff_id, customer_name="x",
            customer_email="x@example.com", starts_at=start, ends_at=start + timedelta(minutes=30),
            blocked_until=start + timedelta(minutes=30), price_cents=0, status=status, manage_token_hash=token,
        )

    with Session() as db:
        db.add(raw(TUE_9AM, "a"))
        db.commit()
        db.add(raw(TUE_9AM + timedelta(minutes=30), "b"))  # touching, not overlapping: allowed
        db.add(raw(TUE_9AM, "c", status="cancelled"))  # cancelled rows don't count
        db.commit()
        db.add(raw(TUE_9AM + timedelta(minutes=15), "d"))
        with pytest.raises(IntegrityError):
            db.commit()


def test_simultaneous_requests_for_one_slot_produce_one_booking(pg):
    Session, (business_id, service_id, staff_id) = pg
    workers = 8
    barrier = threading.Barrier(workers)
    results = []

    def attempt(n):
        with Session() as db:
            business, service = db.get(Business, business_id), db.get(Service, service_id)
            barrier.wait()  # release every thread at the same moment
            try:
                create_booking(db, business, service, TUE_9AM, staff_id, f"P{n}", f"p{n}@example.com")
                results.append("ok")
            except BookingError:
                results.append("refused")

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results) == ["ok"] + ["refused"] * (workers - 1)
