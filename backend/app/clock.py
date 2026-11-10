from datetime import UTC, datetime


def now() -> datetime:
    """The current time in UTC. Kept in one place so tests can freeze it."""
    return datetime.now(UTC)
