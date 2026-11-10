"""Public booking flow. Halifax is UTC-4 in November, so 09:00 local = 13:00Z.
The clock is frozen at Monday 9 Nov 2026, 08:00 local (see conftest)."""

from conftest import book

TUE_9AM = "2026-11-10T13:00:00Z"


def slots(client, shop, day="2026-11-10", staff_id=None, **extra):
    params = {"service_id": shop["service"]["id"], "date": day, **extra}
    if staff_id:
        params["staff_id"] = staff_id
    return client.get(f"/api/businesses/{shop['slug']}/availability", params=params).json()["slots"]


def test_booking_page_lists_active_services_and_staff(client, shop):
    page = client.get("/api/businesses/northside").json()
    assert page["business"]["timezone"] == "America/Halifax"
    assert [s["name"] for s in page["services"]] == ["Haircut"]
    assert {p["name"] for p in page["staff"]} == {"Sam", "Priya"}
    assert client.get("/api/businesses/nope").status_code == 404


def test_slots_follow_local_working_hours(client, shop):
    result = slots(client, shop)
    assert result[0]["start"] == "2026-11-10T13:00:00Z"  # 09:00 Halifax
    assert result[-1]["start"] == "2026-11-10T20:30:00Z"  # last 30-min start before 17:00
    assert len(result[0]["staff_ids"]) == 2
    assert slots(client, shop, day="2026-11-14") == []  # Saturday: nobody works


def test_minimum_notice_and_booking_window(client, shop):
    # It's 08:00 now. With three hours' notice the first slot today is 11:00, not 09:00.
    client.patch("/api/admin/business", headers=shop["auth"], json={"min_notice_minutes": 180})
    today = slots(client, shop, day="2026-11-09")
    assert today[0]["start"] == "2026-11-09T15:00:00Z"
    assert slots(client, shop, day="2026-11-08") == []  # the past
    assert slots(client, shop, day="2026-12-10") == []  # more than 30 days ahead
    days = client.get("/api/businesses/northside/days", params={"service_id": shop["service"]["id"]}).json()
    assert days["first"] == "2026-11-09" and days["last"] == "2026-12-09"
    assert "2026-11-14" not in days["days"] and "2026-11-16" in days["days"]


def test_booking_a_slot_removes_it_for_that_staff_member_only(client, shop, mail):
    sam, priya = (s["id"] for s in shop["staff"])
    res = book(client, shop, TUE_9AM, staff_id=sam)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["staff"]["name"] == "Sam" and body["status"] == "confirmed" and body["manage_token"]

    nine = next(s for s in slots(client, shop) if s["start"] == TUE_9AM)
    assert nine["staff_ids"] == [priya]

    # Two emails: the customer's confirmation (with the private link) and the owner's notice.
    assert [m["To"] for m in mail] == ["pat@example.com", "owner@northside.example.com"]
    assert f"/manage/{body['manage_token']}" in mail[0].get_content()


def test_double_booking_the_same_person_is_refused(client, shop):
    sam = shop["staff"][0]["id"]
    assert book(client, shop, TUE_9AM, staff_id=sam).status_code == 201
    second = book(client, shop, TUE_9AM, staff_id=sam, email="other@example.com")
    assert second.status_code == 409
    assert "no longer available" in second.json()["detail"]


def test_overlapping_but_not_identical_start_is_refused(client, shop):
    sam = shop["staff"][0]["id"]
    assert book(client, shop, TUE_9AM, staff_id=sam).status_code == 201
    assert book(client, shop, "2026-11-10T13:15:00Z", staff_id=sam).status_code == 409
    assert book(client, shop, "2026-11-10T13:30:00Z", staff_id=sam).status_code == 201  # back-to-back is fine


def test_anyone_spreads_bookings_then_runs_out(client, shop):
    first = book(client, shop, TUE_9AM).json()["staff"]["name"]
    second = book(client, shop, TUE_9AM).json()["staff"]["name"]
    assert {first, second} == {"Sam", "Priya"}
    assert book(client, shop, TUE_9AM).status_code == 409  # both are now busy


def test_times_that_were_never_offered_are_refused(client, shop):
    assert book(client, shop, "2026-11-10T12:00:00Z").status_code == 409  # 08:00, before opening
    assert book(client, shop, "2026-11-10T13:05:00Z").status_code == 409  # not on the 15-minute grid
    assert book(client, shop, "2026-11-14T15:00:00Z").status_code == 409  # Saturday
    naive = book(client, shop, "2026-11-10T09:00:00")
    assert naive.status_code == 422  # no offset: ambiguous


def test_buffer_time_is_respected(client, shop):
    auth = shop["auth"]
    client.patch(f"/api/admin/services/{shop['service']['id']}", headers=auth, json={"buffer_minutes": 15})
    sam = shop["staff"][0]["id"]
    assert book(client, shop, TUE_9AM, staff_id=sam).status_code == 201
    # 09:00-09:30 plus 15 minutes of clean-up: Sam's next start is 09:45.
    sams = [s["start"] for s in slots(client, shop, staff_id=sam)]
    assert "2026-11-10T13:30:00Z" not in sams and sams[0] == "2026-11-10T13:45:00Z"


def test_time_off_for_one_person_and_whole_business_closures(client, shop):
    auth = shop["auth"]
    sam, priya = (s["id"] for s in shop["staff"])
    client.post("/api/admin/time-off", headers=auth, json={
        "staff_id": sam, "starts_local": "2026-11-10T00:00", "ends_local": "2026-11-11T00:00", "reason": "Dentist",
    })
    assert all(s["staff_ids"] == [priya] for s in slots(client, shop))

    # Remembrance Day: the whole shop is closed.
    client.post("/api/admin/time-off", headers=auth, json={
        "starts_local": "2026-11-11T00:00", "ends_local": "2026-11-12T00:00", "reason": "Holiday",
    })
    assert slots(client, shop, day="2026-11-11") == []
    assert book(client, shop, "2026-11-11T13:00:00Z").status_code == 409


def test_inactive_service_cannot_be_booked(client, shop):
    client.patch(f"/api/admin/services/{shop['service']['id']}", headers=shop["auth"], json={"is_active": False})
    assert client.get("/api/businesses/northside").json()["services"] == []
    assert book(client, shop, TUE_9AM).status_code == 404


def test_manage_link_view_cancel_and_slot_reopens(client, shop, mail):
    sam = shop["staff"][0]["id"]
    token = book(client, shop, TUE_9AM, staff_id=sam).json()["manage_token"]

    view = client.get(f"/api/manage/{token}").json()
    assert view["can_change"] and view["service"]["name"] == "Haircut"
    assert client.get("/api/manage/not-a-real-token").status_code == 404

    mail.clear()
    cancelled = client.post(f"/api/manage/{token}/cancel").json()
    assert cancelled["status"] == "cancelled" and not cancelled["can_change"]
    assert mail[0]["Subject"].startswith("Cancelled")
    assert client.post(f"/api/manage/{token}/cancel").status_code == 409  # already cancelled

    nine = next(s for s in slots(client, shop) if s["start"] == TUE_9AM)
    assert sam in nine["staff_ids"]  # the slot is free again


def test_reschedule_moves_the_booking_and_frees_the_old_time(client, shop):
    sam = shop["staff"][0]["id"]
    token = book(client, shop, TUE_9AM, staff_id=sam).json()["manage_token"]
    # The booking's own slot is offered back while picking a new time.
    own = slots(client, shop, staff_id=sam, exclude_token=token)
    assert own[0]["start"] == TUE_9AM

    moved = client.post(f"/api/manage/{token}/reschedule", json={"start": "2026-11-12T15:00:00Z", "staff_id": sam})
    assert moved.status_code == 200, moved.text
    assert moved.json()["starts_at"] == "2026-11-12T15:00:00Z"
    assert moved.json()["ends_at"] == "2026-11-12T15:30:00Z"
    assert any(s["start"] == TUE_9AM and sam in s["staff_ids"] for s in slots(client, shop))


def test_cannot_reschedule_onto_someone_else(client, shop):
    sam = shop["staff"][0]["id"]
    book(client, shop, "2026-11-12T15:00:00Z", staff_id=sam, email="first@example.com")
    token = book(client, shop, TUE_9AM, staff_id=sam).json()["manage_token"]
    res = client.post(f"/api/manage/{token}/reschedule", json={"start": "2026-11-12T15:00:00Z", "staff_id": sam})
    assert res.status_code == 409


def test_customers_cannot_cancel_past_appointments(client, shop, monkeypatch, frozen_clock):
    from datetime import timedelta

    from app import clock

    token = book(client, shop, TUE_9AM).json()["manage_token"]
    monkeypatch.setattr(clock, "now", lambda: frozen_clock + timedelta(days=2))
    assert client.get(f"/api/manage/{token}").json()["can_change"] is False
    assert client.post(f"/api/manage/{token}/cancel").status_code == 409
