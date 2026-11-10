from conftest import book, register, weekdays

from app.demo import DEMO_EMAIL, DEMO_PASSWORD, seed_demo


def test_register_validates_slug_timezone_and_duplicates(client):
    base = {"name": "A", "email": "a@example.com", "password": "correct-horse", "business_name": "A"}
    assert client.post("/api/auth/register", json={**base, "slug": "Bad Slug!"}).status_code == 422
    assert client.post("/api/auth/register", json={**base, "slug": "api"}).status_code == 422  # reserved
    assert client.post("/api/auth/register", json={**base, "slug": "fine", "timezone": "Mars/Base"}).status_code == 422
    assert client.post("/api/auth/register", json={**base, "slug": "fine"}).status_code == 201
    assert client.post("/api/auth/register", json={**base, "slug": "other"}).status_code == 409  # email taken
    taken = client.post("/api/auth/register", json={**base, "email": "b@example.com", "slug": "fine"})
    assert taken.status_code == 409 and "URL" in taken.json()["detail"]


def test_login_errors_do_not_reveal_which_emails_exist(client):
    register(client)
    wrong_password = client.post("/api/auth/token", data={"username": "owner@northside.example.com", "password": "x"})
    no_such_user = client.post("/api/auth/token", data={"username": "ghost@example.com", "password": "x"})
    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json() == no_such_user.json()


def test_admin_routes_need_a_token(client):
    assert client.get("/api/admin/services").status_code == 401
    assert client.get("/api/admin/services", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_businesses_cannot_see_or_touch_each_others_data(client, shop):
    other = register(client, slug="rival")
    sid, staff_id = shop["service"]["id"], shop["staff"][0]["id"]
    book(client, shop, "2026-11-10T13:00:00Z")

    assert client.get("/api/admin/services", headers=other).json() == []
    assert client.get("/api/admin/staff", headers=other).json() == []
    assert client.get("/api/admin/bookings", headers=other).json() == []
    assert client.patch(f"/api/admin/services/{sid}", headers=other, json={"name": "Hacked"}).status_code == 404
    assert client.delete(f"/api/admin/staff/{staff_id}", headers=other).status_code == 404
    # Can't attach someone else's service to your own staff, or block someone else's staff.
    res = client.post("/api/admin/staff", headers=other, json={"name": "X", "service_ids": [sid]})
    assert res.status_code == 422
    res = client.post("/api/admin/time-off", headers=other, json={
        "staff_id": staff_id, "starts_local": "2026-11-10T00:00", "ends_local": "2026-11-11T00:00",
    })
    assert res.status_code == 404
    booking_id = client.get("/api/admin/bookings", headers=shop["auth"]).json()[0]["id"]
    assert client.post(f"/api/admin/bookings/{booking_id}/cancel", headers=other).status_code == 404


def test_staff_hours_are_replaced_and_validated(client, shop):
    auth, staff_id = shop["auth"], shop["staff"][0]["id"]
    res = client.patch(f"/api/admin/staff/{staff_id}", headers=auth, json={"hours": weekdays("10:00", "14:00", [0])})
    assert res.json()["hours"] == [{"weekday": 0, "start_time": "10:00:00", "end_time": "14:00:00"}]
    bad = client.patch(f"/api/admin/staff/{staff_id}", headers=auth, json={"hours": weekdays("14:00", "10:00", [0])})
    assert bad.status_code == 422


def test_services_with_bookings_are_deactivated_not_deleted(client, shop):
    auth, sid = shop["auth"], shop["service"]["id"]
    book(client, shop, "2026-11-10T13:00:00Z")
    assert client.delete(f"/api/admin/services/{sid}", headers=auth).status_code == 409
    spare = client.post("/api/admin/services", headers=auth, json={"name": "Spare", "duration_minutes": 15}).json()
    assert client.delete(f"/api/admin/services/{spare['id']}", headers=auth).status_code == 204


def test_owner_sees_and_cancels_bookings_and_customer_is_emailed(client, shop, mail):
    auth = shop["auth"]
    book(client, shop, "2026-11-10T13:00:00Z")
    book(client, shop, "2026-11-20T13:00:00Z", email="later@example.com")
    week = client.get("/api/admin/bookings", headers=auth, params={"start": "2026-11-09", "days": 7}).json()
    assert [b["customer_email"] for b in week] == ["pat@example.com"]

    mail.clear()
    res = client.post(f"/api/admin/bookings/{week[0]['id']}/cancel", headers=auth)
    assert res.json()["status"] == "cancelled" and res.json()["cancelled_by"] == "business"
    assert mail[0]["To"] == "pat@example.com" and "Northside cancelled" in mail[0].get_content()
    cancelled = client.get("/api/admin/bookings", headers=auth, params={"start": "2026-11-09", "status": "cancelled"})
    assert len(cancelled.json()) == 1


def test_stats_group_by_local_week_service_and_hour(client, shop):
    auth = shop["auth"]
    book(client, shop, "2026-11-10T13:00:00Z")  # Tue 09:00 local
    book(client, shop, "2026-11-10T13:00:00Z", email="b@example.com")  # second staff member
    token = book(client, shop, "2026-11-17T18:00:00Z", email="c@example.com").json()["manage_token"]  # next week
    client.post(f"/api/manage/{token}/cancel")

    stats = client.get("/api/admin/stats", headers=auth, params={"weeks": 2}).json()
    assert [w["week_start"] for w in stats["weeks"]] == ["2026-11-02", "2026-11-09"]
    assert stats["weeks"][1] == {"week_start": "2026-11-09", "bookings": 2, "revenue_cents": 7000}
    assert stats["by_service"] == [{"service": "Haircut", "bookings": 2, "revenue_cents": 7000}]
    assert stats["by_hour"] == [{"hour": 9, "bookings": 2}]
    assert stats["upcoming"] == 2  # the cancelled one doesn't count


def test_demo_account_is_read_only(client, session_factory):
    with session_factory() as db:
        seed_demo(db)
    token = client.post("/api/auth/token", data={"username": DEMO_EMAIL, "password": DEMO_PASSWORD}).json()
    auth = {"Authorization": f"Bearer {token['access_token']}"}

    assert len(client.get("/api/admin/services", headers=auth).json()) == 5
    assert client.get("/api/admin/stats", headers=auth).json()["total_bookings"] > 100
    res = client.post("/api/admin/services", headers=auth, json={"name": "X", "duration_minutes": 10})
    assert res.status_code == 403 and "read-only" in res.json()["detail"]
    # Anyone can still book on the demo's public page.
    page = client.get("/api/businesses/demo").json()
    open_day = client.get("/api/businesses/demo/days", params={"service_id": page["services"][0]["id"]}).json()["days"][0]
    slot = client.get("/api/businesses/demo/availability",
                      params={"service_id": page["services"][0]["id"], "date": open_day}).json()["slots"][0]
    res = client.post("/api/businesses/demo/bookings", json={
        "service_id": page["services"][0]["id"], "start": slot["start"],
        "customer_name": "Visitor", "customer_email": "visitor@example.com",
    })
    assert res.status_code == 201


def test_demo_seed_can_run_twice(session_factory):
    from sqlalchemy import func, select

    from app.models import Business, User

    with session_factory() as db:
        seed_demo(db)
        seed_demo(db)  # every startup rebuilds it; there must still be exactly one
        assert db.scalar(select(func.count()).select_from(Business)) == 1
        assert db.scalar(select(func.count()).select_from(User)) == 1
