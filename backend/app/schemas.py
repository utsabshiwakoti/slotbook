import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED_SLUGS = {"admin", "api", "login", "signup", "manage", "demo-admin"}


def _check_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Unknown time zone; use an IANA name such as America/Halifax") from None
    return value


def _aware(value: datetime) -> datetime:
    # A bare "2026-11-17T09:00" is ambiguous; clients must say which offset they mean.
    if value.tzinfo is None:
        raise ValueError("Include a UTC offset, e.g. 2026-11-17T13:00:00Z")
    return value


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------


class Register(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    business_name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=3, max_length=40, description="Public booking URL: /b/<slug>")
    timezone: str = "America/Halifax"

    @field_validator("slug")
    @classmethod
    def slug_ok(cls, v: str) -> str:
        v = v.lower()
        if not SLUG.match(v) or v in RESERVED_SLUGS:
            raise ValueError("Use lowercase letters, numbers and single dashes, e.g. northside-cuts")
        return v

    @field_validator("timezone")
    @classmethod
    def tz_ok(cls, v: str) -> str:
        return _check_timezone(v)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class BusinessOut(ORM):
    id: int
    name: str
    slug: str
    description: str
    timezone: str
    slot_interval_minutes: int
    min_notice_minutes: int
    max_days_ahead: int


class BusinessUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    timezone: str | None = None
    slot_interval_minutes: int | None = Field(default=None, ge=5, le=120)
    min_notice_minutes: int | None = Field(default=None, ge=0, le=10080)
    max_days_ahead: int | None = Field(default=None, ge=1, le=365)

    @field_validator("timezone")
    @classmethod
    def tz_ok(cls, v: str | None) -> str | None:
        return None if v is None else _check_timezone(v)


class Me(ORM):
    id: int
    name: str
    email: str
    is_demo: bool
    business: BusinessOut


# ---------- services and staff ----------


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    duration_minutes: int = Field(ge=5, le=480)
    buffer_minutes: int = Field(default=0, ge=0, le=120)
    price_cents: int = Field(default=0, ge=0, le=10_000_000)
    is_active: bool = True


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    buffer_minutes: int | None = Field(default=None, ge=0, le=120)
    price_cents: int | None = Field(default=None, ge=0, le=10_000_000)
    is_active: bool | None = None


class ServiceOut(ORM):
    id: int
    name: str
    description: str
    duration_minutes: int
    buffer_minutes: int
    price_cents: int
    is_active: bool


class Shift(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    start_time: time
    end_time: time

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def ordered(self):
        if self.end_time <= self.start_time:
            raise ValueError("A shift must end after it starts")
        return self


class StaffIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True
    service_ids: list[int] = []
    hours: list[Shift] = []


class StaffUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None
    service_ids: list[int] | None = None
    hours: list[Shift] | None = None  # replaces the whole weekly schedule


class StaffOut(ORM):
    id: int
    name: str
    is_active: bool
    service_ids: list[int]
    hours: list[Shift]


class TimeOffIn(BaseModel):
    """Times are wall-clock times in the business's time zone, as the owner thinks of them."""

    staff_id: int | None = Field(default=None, description="Leave empty to close the whole business")
    starts_local: datetime
    ends_local: datetime
    reason: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def ordered(self):
        if self.ends_local <= self.starts_local:
            raise ValueError("Time off must end after it starts")
        return self


class TimeOffOut(ORM):
    id: int
    staff_id: int | None
    starts_at: datetime
    ends_at: datetime
    reason: str


# ---------- bookings ----------


class Ref(ORM):
    id: int
    name: str


class BookingOut(ORM):
    id: int
    service: Ref
    staff: Ref
    customer_name: str
    customer_email: str
    note: str
    starts_at: datetime
    ends_at: datetime
    price_cents: int
    status: str
    created_at: datetime
    cancelled_by: str | None


class BookingCreate(BaseModel):
    service_id: int
    staff_id: int | None = Field(default=None, description="Leave empty for anyone available")
    start: datetime
    customer_name: str = Field(min_length=1, max_length=100)
    customer_email: EmailStr
    note: str = Field(default="", max_length=500)

    @field_validator("start")
    @classmethod
    def start_aware(cls, v: datetime) -> datetime:
        return _aware(v)


class Reschedule(BaseModel):
    start: datetime
    staff_id: int | None = None

    @field_validator("start")
    @classmethod
    def start_aware(cls, v: datetime) -> datetime:
        return _aware(v)


class PublicBusiness(BaseModel):
    name: str
    slug: str
    description: str
    timezone: str


class ManagedBooking(BaseModel):
    """What a customer sees through their manage link."""

    id: int
    business: PublicBusiness
    service: ServiceOut
    staff: Ref
    customer_name: str
    starts_at: datetime
    ends_at: datetime
    status: str
    can_change: bool


class BookingCreated(ManagedBooking):
    manage_token: str  # returned once; the server only keeps its hash


# ---------- public booking page ----------


class PublicStaff(BaseModel):
    id: int
    name: str
    service_ids: list[int]


class BookingPage(BaseModel):
    business: PublicBusiness
    services: list[ServiceOut]
    staff: list[PublicStaff]


class Slot(BaseModel):
    start: datetime
    staff_ids: list[int]


class DayAvailability(BaseModel):
    date: date
    timezone: str
    slots: list[Slot]


class OpenDays(BaseModel):
    timezone: str
    first: date
    last: date
    days: list[date]


# ---------- stats ----------


class WeekStat(BaseModel):
    week_start: date
    bookings: int
    revenue_cents: int


class ServiceStat(BaseModel):
    service: str
    bookings: int
    revenue_cents: int


class HourStat(BaseModel):
    hour: int
    bookings: int


class Stats(BaseModel):
    weeks: list[WeekStat]
    by_service: list[ServiceStat]
    by_hour: list[HourStat]
    upcoming: int
    total_bookings: int
    total_revenue_cents: int
    cancellation_rate: float
