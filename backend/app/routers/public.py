"""Customer-facing API: no login. A business's page is found by its slug; a booking is managed
through the secret token from the confirmation email."""

from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock, emails, schemas
from ..booking import (
    BookingError,
    booking_window,
    cancel_booking,
    create_booking,
    hash_token,
    merge_slots,
    reschedule_booking,
    slots_for_days,
)
from ..config import settings
from ..database import get_db
from ..models import CONFIRMED, Booking, Business, Service, User

router = APIRouter(prefix="/api", tags=["public"])


def _business(db: Session, slug: str) -> Business:
    business = db.scalar(select(Business).where(Business.slug == slug.lower()))
    if business is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    return business


def _service(db: Session, business: Business, service_id: int) -> Service:
    service = db.scalar(
        select(Service).where(Service.id == service_id, Service.business_id == business.id, Service.is_active)
    )
    if service is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service not found")
    return service


def _manage_url(request: Request, token: str) -> str:
    base = settings.public_url or str(request.base_url).rstrip("/")
    return f"{base}/manage/{token}"


def _public_business(b: Business) -> schemas.PublicBusiness:
    return schemas.PublicBusiness(name=b.name, slug=b.slug, description=b.description, timezone=b.timezone)


def _managed(b: Booking) -> dict:
    return dict(
        id=b.id,
        business=_public_business(b.business),
        service=schemas.ServiceOut.model_validate(b.service),
        staff=schemas.Ref(id=b.staff.id, name=b.staff.name),
        customer_name=b.customer_name,
        starts_at=b.starts_at,
        ends_at=b.ends_at,
        status=b.status,
        can_change=b.status == CONFIRMED and b.starts_at > clock.now(),
    )


# ---------- booking page ----------


@router.get("/businesses/{slug}", response_model=schemas.BookingPage)
def booking_page(slug: str, db: Session = Depends(get_db)):
    business = _business(db, slug)
    services = [s for s in business.services if s.is_active]
    active_ids = {s.id for s in services}
    staff = [
        schemas.PublicStaff(id=p.id, name=p.name, service_ids=[i for i in p.service_ids if i in active_ids])
        for p in business.staff
        if p.is_active
    ]
    return schemas.BookingPage(business=_public_business(business), services=services, staff=staff)


@router.get("/businesses/{slug}/days", response_model=schemas.OpenDays)
def open_days(
    slug: str,
    service_id: int,
    staff_id: int | None = None,
    exclude_token: str | None = Query(default=None, description="When rescheduling, the booking being moved"),
    db: Session = Depends(get_db),
):
    """Which dates in the booking window have at least one free slot (to grey out the calendar)."""
    business = _business(db, slug)
    service = _service(db, business, service_id)
    first, last = booking_window(business, clock.now())
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    exclude = _excluded_booking_id(db, exclude_token)
    by_day = slots_for_days(db, business, service, days, staff_id, exclude)
    return schemas.OpenDays(
        timezone=business.timezone, first=first, last=last, days=[d for d, slots in by_day.items() if slots]
    )


@router.get("/businesses/{slug}/availability", response_model=schemas.DayAvailability)
def availability(
    slug: str,
    service_id: int,
    day: date = Query(alias="date"),
    staff_id: int | None = None,
    exclude_token: str | None = None,
    db: Session = Depends(get_db),
):
    business = _business(db, slug)
    service = _service(db, business, service_id)
    exclude = _excluded_booking_id(db, exclude_token)
    by_staff = slots_for_days(db, business, service, [day], staff_id, exclude).get(day, {})
    return schemas.DayAvailability(
        date=day,
        timezone=business.timezone,
        slots=[schemas.Slot(start=start, staff_ids=ids) for start, ids in merge_slots(by_staff)],
    )


@router.post("/businesses/{slug}/bookings", response_model=schemas.BookingCreated, status_code=201)
def book(
    slug: str,
    payload: schemas.BookingCreate,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    business = _business(db, slug)
    service = _service(db, business, payload.service_id)
    try:
        booking, token = create_booking(
            db, business, service, payload.start, payload.staff_id,
            payload.customer_name, payload.customer_email, payload.note,
        )
    except BookingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None

    owner = db.scalar(select(User.email).where(User.business_id == business.id, User.is_demo.is_(False)))
    background.add_task(emails.send_all, emails.booking_confirmed(booking, _manage_url(request, token), owner))
    return schemas.BookingCreated(**_managed(booking), manage_token=token)


# ---------- manage link ----------


def _by_token(db: Session, token: str) -> Booking:
    booking = db.scalar(select(Booking).where(Booking.manage_token_hash == hash_token(token)))
    if booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found. Check the link in your email.")
    return booking


def _excluded_booking_id(db: Session, token: str | None) -> int | None:
    return _by_token(db, token).id if token else None


@router.get("/manage/{token}", response_model=schemas.ManagedBooking)
def view_booking(token: str, db: Session = Depends(get_db)):
    return _managed(_by_token(db, token))


@router.post("/manage/{token}/cancel", response_model=schemas.ManagedBooking)
def customer_cancel(token: str, background: BackgroundTasks, db: Session = Depends(get_db)):
    booking = _by_token(db, token)
    try:
        cancel_booking(db, booking, by="customer")
    except BookingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    background.add_task(emails.send_all, emails.booking_cancelled(booking))
    return _managed(booking)


@router.post("/manage/{token}/reschedule", response_model=schemas.ManagedBooking)
def customer_reschedule(
    token: str, payload: schemas.Reschedule, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
):
    booking = _by_token(db, token)
    try:
        reschedule_booking(db, booking, payload.start, payload.staff_id)
    except BookingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    db.refresh(booking)  # staff_id may have changed; reload the relationship for the response
    background.add_task(emails.send_all, emails.booking_rescheduled(booking, _manage_url(request, token)))
    return _managed(booking)
