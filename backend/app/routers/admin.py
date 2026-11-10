"""The business owner's API. Every query is filtered by the signed-in user's business_id, and
lookups by id use _owned(), which returns 404 for another tenant's rows (not 403, so ids can't
be probed)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import clock, emails, schemas
from ..availability import local_day_bounds
from ..booking import BookingError, cancel_booking
from ..database import get_db
from ..models import Booking, Service, Staff, TimeOff, User, WorkingHours
from ..security import get_current_user, get_editor
from ..stats import business_stats

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _owned(db: Session, model, obj_id: int, user: User):
    obj = db.scalar(select(model).where(model.id == obj_id, model.business_id == user.business_id))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def _services_by_id(db: Session, user: User, ids: list[int]) -> list[Service]:
    services = list(db.scalars(select(Service).where(Service.id.in_(ids), Service.business_id == user.business_id)))
    if len(services) != len(set(ids)):
        raise HTTPException(422, "Unknown service id")
    return services


# ---------- business settings ----------


@router.get("/business", response_model=schemas.BusinessOut)
def get_business(user: User = Depends(get_current_user)):
    return user.business


@router.patch("/business", response_model=schemas.BusinessOut)
def update_business(payload: schemas.BusinessUpdate, db: Session = Depends(get_db), user: User = Depends(get_editor)):
    business = user.business
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(business, field, value)
    db.commit()
    return business


# ---------- services ----------


@router.get("/services", response_model=list[schemas.ServiceOut])
def list_services(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(Service).where(Service.business_id == user.business_id).order_by(Service.id)).all()


@router.post("/services", response_model=schemas.ServiceOut, status_code=201)
def create_service(payload: schemas.ServiceIn, db: Session = Depends(get_db), user: User = Depends(get_editor)):
    service = Service(**payload.model_dump(), business_id=user.business_id)
    db.add(service)
    db.commit()
    return service


@router.patch("/services/{service_id}", response_model=schemas.ServiceOut)
def update_service(
    service_id: int, payload: schemas.ServiceUpdate, db: Session = Depends(get_db), user: User = Depends(get_editor)
):
    service = _owned(db, Service, service_id, user)
    for field, value in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(service, field, value)
    db.commit()
    return service


@router.delete("/services/{service_id}", status_code=204)
def delete_service(service_id: int, db: Session = Depends(get_db), user: User = Depends(get_editor)):
    service = _owned(db, Service, service_id, user)
    if db.scalar(select(Booking.id).where(Booking.service_id == service.id).limit(1)):
        # Deleting would orphan booking history and break the stats; hiding it is what owners want.
        raise HTTPException(status.HTTP_409_CONFLICT, "This service has bookings. Turn it off instead of deleting it.")
    db.delete(service)
    db.commit()
    return Response(status_code=204)


# ---------- staff and weekly hours ----------


def _staff_query(user: User):
    return (
        select(Staff)
        .where(Staff.business_id == user.business_id)
        .options(selectinload(Staff.services), selectinload(Staff.hours))
        .order_by(Staff.id)
    )


def _apply_staff(db: Session, user: User, staff: Staff, data: dict) -> None:
    if "service_ids" in data:
        staff.services = _services_by_id(db, user, data.pop("service_ids"))
    if "hours" in data:
        staff.hours = [WorkingHours(**shift) for shift in data.pop("hours")]
    for field, value in data.items():
        setattr(staff, field, value)


@router.get("/staff", response_model=list[schemas.StaffOut])
def list_staff(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(_staff_query(user)).all()


@router.post("/staff", response_model=schemas.StaffOut, status_code=201)
def create_staff(payload: schemas.StaffIn, db: Session = Depends(get_db), user: User = Depends(get_editor)):
    staff = Staff(business_id=user.business_id, name=payload.name)
    _apply_staff(db, user, staff, payload.model_dump())
    db.add(staff)
    db.commit()
    return staff


@router.patch("/staff/{staff_id}", response_model=schemas.StaffOut)
def update_staff(
    staff_id: int, payload: schemas.StaffUpdate, db: Session = Depends(get_db), user: User = Depends(get_editor)
):
    staff = _owned(db, Staff, staff_id, user)
    _apply_staff(db, user, staff, payload.model_dump(exclude_unset=True, exclude_none=True))
    db.commit()
    return staff


@router.delete("/staff/{staff_id}", status_code=204)
def delete_staff(staff_id: int, db: Session = Depends(get_db), user: User = Depends(get_editor)):
    staff = _owned(db, Staff, staff_id, user)
    if db.scalar(select(Booking.id).where(Booking.staff_id == staff.id).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "This person has bookings. Mark them inactive instead.")
    db.delete(staff)
    db.commit()
    return Response(status_code=204)


# ---------- time off ----------


def _as_local(moment: datetime, tz: ZoneInfo) -> datetime:
    """A naive time means local wall-clock time; an explicit offset is respected."""
    return moment.replace(tzinfo=tz) if moment.tzinfo is None else moment


@router.get("/time-off", response_model=list[schemas.TimeOffOut])
def list_time_off(
    include_past: bool = False, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    stmt = select(TimeOff).where(TimeOff.business_id == user.business_id).order_by(TimeOff.starts_at)
    if not include_past:
        stmt = stmt.where(TimeOff.ends_at > clock.now())
    return db.scalars(stmt).all()


@router.post("/time-off", response_model=schemas.TimeOffOut, status_code=201)
def create_time_off(payload: schemas.TimeOffIn, db: Session = Depends(get_db), user: User = Depends(get_editor)):
    if payload.staff_id is not None:
        _owned(db, Staff, payload.staff_id, user)
    tz = ZoneInfo(user.business.timezone)
    block = TimeOff(
        business_id=user.business_id,
        staff_id=payload.staff_id,
        # The owner typed local wall-clock times; store the real instants.
        starts_at=_as_local(payload.starts_local, tz),
        ends_at=_as_local(payload.ends_local, tz),
        reason=payload.reason.strip(),
    )
    db.add(block)
    db.commit()
    return block


@router.delete("/time-off/{block_id}", status_code=204)
def delete_time_off(block_id: int, db: Session = Depends(get_db), user: User = Depends(get_editor)):
    db.delete(_owned(db, TimeOff, block_id, user))
    db.commit()
    return Response(status_code=204)


# ---------- bookings ----------


@router.get("/bookings", response_model=list[schemas.BookingOut])
def list_bookings(
    start: date | None = Query(default=None, description="First local date (default: today)"),
    days: int = Query(default=7, ge=1, le=93),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(confirmed|cancelled)$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tz = ZoneInfo(user.business.timezone)
    first = start or clock.now().astimezone(tz).date()
    span_start = local_day_bounds(first, tz).start
    span_end = local_day_bounds(first + timedelta(days=days - 1), tz).end
    stmt = (
        select(Booking)
        .where(Booking.business_id == user.business_id, Booking.starts_at >= span_start, Booking.starts_at < span_end)
        .options(selectinload(Booking.service), selectinload(Booking.staff))
        .order_by(Booking.starts_at)
    )
    if status_filter:
        stmt = stmt.where(Booking.status == status_filter)
    return db.scalars(stmt).all()


@router.post("/bookings/{booking_id}/cancel", response_model=schemas.BookingOut)
def admin_cancel(
    booking_id: int, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(get_editor)
):
    booking = _owned(db, Booking, booking_id, user)
    try:
        cancel_booking(db, booking, by="business")
    except BookingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    background.add_task(emails.send_all, emails.booking_cancelled(booking))
    return booking


# ---------- dashboard ----------


@router.get("/stats", response_model=schemas.Stats)
def stats(
    weeks: int = Query(default=8, ge=1, le=52), db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    return business_stats(db, user.business, weeks)
