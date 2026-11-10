"""Transactional email. Messages are plain text and sent after the response (BackgroundTasks),
so a slow mail server never slows down booking."""

import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from .config import settings
from .models import Booking

log = logging.getLogger("slotbook.email")
outbox: list[EmailMessage] = []  # filled when EMAIL_BACKEND=memory, which the tests use


def send(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    if settings.email_backend == "memory":
        outbox.append(msg)
    elif settings.email_backend == "smtp":
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException):
            # The booking is already saved; a failed email must not turn into a failed request.
            log.exception("Could not send email to %s", to)
    else:
        print(f"\n--- email to {to} ---\nSubject: {subject}\n\n{body}\n--- end ---\n", flush=True)


def format_local(moment: datetime, tz_name: str) -> str:
    """'Tuesday, November 17 at 9:30 AM' in the business's time zone (portable, no %-d)."""
    local = moment.astimezone(ZoneInfo(tz_name))
    hour = local.hour % 12 or 12
    return f"{local:%A, %B} {local.day} at {hour}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def _summary(b: Booking) -> str:
    when = format_local(b.starts_at, b.business.timezone)
    return (
        f"{b.service.name} with {b.staff.name}\n"
        f"{when} ({b.business.timezone})\n"
        f"{b.business.name}"
    )


# The builders below run inside the request (while the database session is open) and return
# (to, subject, body) tuples; only the slow part, sending, happens in the background.
Message = tuple[str, str, str]


def send_all(messages: list[Message]) -> None:
    for to, subject, body in messages:
        send(to, subject, body)


def booking_confirmed(b: Booking, manage_url: str, owner_email: str | None) -> list[Message]:
    messages = [
        (
            b.customer_email,
            f"Booked: {b.service.name} at {b.business.name}",
            f"Hi {b.customer_name},\n\nYou're booked in.\n\n{_summary(b)}\n\n"
            f"Need to change or cancel? Use this link (keep it private):\n{manage_url}\n",
        )
    ]
    if owner_email:
        messages.append(
            (
                owner_email,
                f"New booking: {b.customer_name}, {format_local(b.starts_at, b.business.timezone)}",
                f"{b.customer_name} <{b.customer_email}> booked:\n\n{_summary(b)}\n\nNote: {b.note or '(none)'}\n",
            )
        )
    return messages


def booking_rescheduled(b: Booking, manage_url: str) -> list[Message]:
    return [
        (
            b.customer_email,
            f"Moved: {b.service.name} at {b.business.name}",
            f"Hi {b.customer_name},\n\nYour appointment has moved to:\n\n{_summary(b)}\n\n"
            f"Manage it here:\n{manage_url}\n",
        )
    ]


def booking_cancelled(b: Booking) -> list[Message]:
    who = "You cancelled" if b.cancelled_by == "customer" else f"{b.business.name} cancelled"
    return [
        (
            b.customer_email,
            f"Cancelled: {b.service.name} at {b.business.name}",
            f"Hi {b.customer_name},\n\n{who} this appointment:\n\n{_summary(b)}\n",
        )
    ]

