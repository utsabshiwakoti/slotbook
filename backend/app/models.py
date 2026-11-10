from datetime import datetime, time

from sqlalchemy import (
    DDL,
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    Time,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import clock
from .database import Base, UTCDateTime

CONFIRMED = "confirmed"
CANCELLED = "cancelled"


class Business(Base):
    """A tenant. Every other row belongs to exactly one business."""

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(40), unique=True, index=True)  # public URL: /b/<slug>
    description: Mapped[str] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(String(64), default="America/Halifax")
    # Booking rules
    slot_interval_minutes: Mapped[int] = mapped_column(default=15)  # start times are offered every N minutes
    min_notice_minutes: Mapped[int] = mapped_column(default=60)  # no bookings starting sooner than this
    max_days_ahead: Mapped[int] = mapped_column(default=30)  # how far ahead customers can book
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.now)

    services: Mapped[list["Service"]] = relationship(back_populates="business", order_by="Service.id")
    staff: Mapped[list["Staff"]] = relationship(back_populates="business", order_by="Staff.id")


class User(Base):
    """A business owner who signs in to the admin dashboard. Customers don't need accounts."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)  # the shared demo login is read-only
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.now)

    business: Mapped[Business] = relationship()


# Which staff members can perform which services.
staff_services = Table(
    "staff_services",
    Base.metadata,
    Column("staff_id", ForeignKey("staff.id", ondelete="CASCADE"), primary_key=True),
    Column("service_id", ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int]
    buffer_minutes: Mapped[int] = mapped_column(default=0)  # clean-up time kept free after each booking
    price_cents: Mapped[int] = mapped_column(default=0)  # integer cents: no floating-point money
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    business: Mapped[Business] = relationship(back_populates="services")
    staff: Mapped[list["Staff"]] = relationship(secondary=staff_services, back_populates="services")


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    business: Mapped[Business] = relationship(back_populates="staff")
    services: Mapped[list[Service]] = relationship(secondary=staff_services, back_populates="staff")
    hours: Mapped[list["WorkingHours"]] = relationship(
        cascade="all, delete-orphan", order_by="(WorkingHours.weekday, WorkingHours.start_time)"
    )

    @property
    def service_ids(self) -> list[int]:
        return [s.id for s in self.services]


class WorkingHours(Base):
    """A weekly recurring shift in the business's local time. Several per day allow split shifts."""

    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int]  # 0 = Monday ... 6 = Sunday, same as date.weekday()
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)


class TimeOff(Base):
    """A blocked period. staff_id NULL means the whole business is closed (e.g. a holiday)."""

    __tablename__ = "time_off"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime)
    reason: Mapped[str] = mapped_column(String(200), default="")

    staff: Mapped[Staff | None] = relationship()


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"))
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    customer_name: Mapped[str] = mapped_column(String(100))
    customer_email: Mapped[str] = mapped_column(String(255))
    note: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime)
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # ends_at plus the service's buffer. Overlap checks use this, so a buffer can't be booked over
    # even if the service's buffer is changed later.
    blocked_until: Mapped[datetime] = mapped_column(UTCDateTime)
    price_cents: Mapped[int]  # copied at booking time; later price changes don't rewrite history
    status: Mapped[str] = mapped_column(String(20), default=CONFIRMED)
    # Customers manage their booking through an emailed link. Only a hash is stored, like a password.
    manage_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.now)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[str | None] = mapped_column(String(20))  # "customer" or "business"

    business: Mapped[Business] = relationship()
    service: Mapped[Service] = relationship()
    staff: Mapped[Staff] = relationship()

    __table_args__ = (Index("ix_bookings_staff_start", "staff_id", "starts_at"),)


# Last line of defence against double-booking, on Postgres only: the database itself refuses two
# confirmed bookings for the same staff member whose [starts_at, blocked_until) ranges overlap.
# The application also checks under a row lock (see booking.py), which gives a friendly error;
# this constraint guarantees correctness even if that code has a bug.
event.listen(
    Booking.__table__,
    "before_create",
    DDL("CREATE EXTENSION IF NOT EXISTS btree_gist").execute_if(dialect="postgresql"),
)
event.listen(
    Booking.__table__,
    "after_create",
    DDL(
        "ALTER TABLE bookings ADD CONSTRAINT bookings_no_overlap EXCLUDE USING gist "
        "(staff_id WITH =, tstzrange(starts_at, blocked_until) WITH &&) WHERE (status = 'confirmed')"
    ).execute_if(dialect="postgresql"),
)
