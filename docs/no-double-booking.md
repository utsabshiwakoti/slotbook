# How SlotBook makes double-booking impossible

A booking app has one promise it can't break: two people never get the same slot. This is how I kept that promise in SlotBook, and how I proved it.

## The bug you get for free

The obvious way to book a slot is two steps:

1. Check that the slot is free.
2. Insert the booking.

That works every time you test it by hand, because you are one person clicking one button. It breaks when two requests arrive close together:

```
Request A: is 9:00 free?  -> yes
Request B: is 9:00 free?  -> yes      (A hasn't inserted yet)
Request A: insert booking -> ok
Request B: insert booking -> ok       (two bookings, one slot)
```

Nothing in either request is wrong on its own. The problem is the gap between the check and the insert. Any fix has to close that gap.

## Layer 1: lock, then check again

Before a booking is created, the staff member's row is locked with `SELECT ... FOR UPDATE`, and availability is checked a second time while holding the lock:

```python
for sid in candidates:
    db.execute(select(Staff.id).where(Staff.id == sid).with_for_update())
    still_free = slots_for_days(db, business, service, [day], sid, exclude_booking_id)[day]
    if start in still_free.get(sid, []):
        return sid
raise BookingError("That time is no longer available. Please pick another slot.")
```

The lock makes requests for the same staff member take turns. Request B waits until A has committed, then runs its check, sees A's booking, and gets a normal "no longer available" message.

Two details matter here:

- **The second check is the one that counts.** The first check (before the lock) only narrows down which staff to try. A check made before taking the lock can be out of date by the time the lock is granted.
- **I lock the staff row, not the slot.** A slot isn't a row in the database; it's worked out from working hours, time off and existing bookings. The staff member is the thing two bookings actually compete for, so that's what gets locked. Bookings for different staff don't wait on each other.

Listing slots and claiming one also go through the same function (`slots_for_days`), so the API can never accept a time it wouldn't have offered.

## Layer 2: the database refuses overlaps

Layer 1 lives in application code, and application code can have bugs: a new endpoint that forgets the lock, a script that writes to the table directly. So the rule is also written into the database itself, as a Postgres exclusion constraint:

```sql
ALTER TABLE bookings ADD CONSTRAINT bookings_no_overlap
EXCLUDE USING gist (
    staff_id WITH =,
    tstzrange(starts_at, blocked_until) WITH &&
) WHERE (status = 'confirmed');
```

In plain words: no two confirmed bookings may have the same staff member and overlapping time ranges. A unique index can't express this, because it only catches identical values; a 9:00–9:30 booking and a 9:15–9:45 booking have different start times but still collide. `&&` is the range "overlaps" operator, and `btree_gist` lets one index combine it with a plain equality on `staff_id`.

The `WHERE` clause means cancelled bookings don't block anything, so a cancelled slot can be booked again.

The range ends at `blocked_until`, not the end of the appointment. That's the end time plus the service's clean-up buffer, saved on the booking when it's made. If the owner changes the buffer later, old bookings keep the buffer they were made with, so an edit can never make existing bookings overlap.

If the constraint ever fires, the commit raises `IntegrityError`. The code turns that into the same "no longer available" message, so the customer sees one consistent answer whichever layer caught it.

## Layer 3: a test that actually races

A test that books a slot and then books it again proves nothing about concurrency: the two requests run one after the other. To test a race you have to create one.

```python
def test_simultaneous_requests_for_one_slot_produce_one_booking(pg):
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
    ...
    assert sorted(results) == ["ok"] + ["refused"] * (workers - 1)
```

Eight threads each open their own database connection, then wait at a `threading.Barrier`. When the last one arrives, all eight are released at once and try to book the same slot. The test passes only if exactly one succeeds and seven are refused.

A second test skips the application checks completely and inserts two overlapping rows directly, to prove the constraint works on its own.

Both tests need a real Postgres, because SQLite has no row locks and no exclusion constraints. They are skipped locally unless `TEST_DATABASE_URL` is set, and CI starts a Postgres container on every push so they always run there.

## What I'd do differently at larger scale

- Locking the staff row serialises every booking for that person, including ones for different days. That's fine for a barber shop. For a very busy calendar I'd lock something narrower, such as an advisory lock on staff plus day.
- The lock is held while availability is recalculated. I'd measure that under load before assuming it's fast enough.
- I'd add retries with a short backoff for the rare case where the constraint fires on a slot the customer could still get with a different staff member.

## The short version

- Check-then-insert has a gap. Close it with a lock and re-check inside the lock.
- Put the rule in the database too, so no code path can skip it.
- Prove it with a test that really runs requests at the same time, against the real database.
