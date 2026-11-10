from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import clock, emails
from app.config import settings
from app.database import Base, get_db
from app.main import app

# Monday 9 November 2026, 12:00 UTC = 08:00 in Halifax (standard time, UTC-4).
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: NOW)
    return NOW


@pytest.fixture(autouse=True)
def mail(monkeypatch):
    monkeypatch.setattr(settings, "email_backend", "memory")
    emails.outbox.clear()
    return emails.outbox


@pytest.fixture()
def session_factory():
    # In-memory SQLite shared across threads; a fresh database for every test.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # Not `with TestClient(app)`: that would run the lifespan against the real database.
    yield TestClient(app)
    app.dependency_overrides.clear()


def register(client, slug="northside", email=None, tz="America/Halifax"):
    email = email or f"owner@{slug}.example.com"
    res = client.post(
        "/api/auth/register",
        json={
            "name": "Owner", "email": email, "password": "correct-horse",
            "business_name": slug.title(), "slug": slug, "timezone": tz,
        },
    )
    assert res.status_code == 201, res.text
    token = client.post("/api/auth/token", data={"username": email, "password": "correct-horse"}).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


def weekdays(start="09:00", end="17:00", days=range(5)):
    return [{"weekday": d, "start_time": start, "end_time": end} for d in days]


@pytest.fixture()
def shop(client):
    """A business with one 30-minute service and two staff working Mon-Fri 9-17 Halifax time."""
    auth = register(client)
    cut = client.post(
        "/api/admin/services", headers=auth,
        json={"name": "Haircut", "duration_minutes": 30, "price_cents": 3500},
    ).json()
    staff = [
        client.post(
            "/api/admin/staff", headers=auth,
            json={"name": name, "service_ids": [cut["id"]], "hours": weekdays()},
        ).json()
        for name in ("Sam", "Priya")
    ]
    return {"auth": auth, "slug": "northside", "service": cut, "staff": staff}


def book(client, shop, start, staff_id=None, email="pat@example.com", service_id=None):
    return client.post(
        f"/api/businesses/{shop['slug']}/bookings",
        json={
            "service_id": service_id or shop["service"]["id"], "staff_id": staff_id, "start": start,
            "customer_name": "Pat Doe", "customer_email": email,
        },
    )
