from datetime import UTC, datetime

from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator

from .config import settings


def _normalise_url(url: str) -> str:
    # Hosts like Neon hand out "postgres://" URLs; point SQLAlchemy at the psycopg 3 driver.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _normalise_url(settings.database_url)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    # FastAPI runs sync routes in a thread pool, so SQLite must allow cross-thread use.
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    # Replace connections a hosted Postgres closed while the app slept.
    pool_pre_ping=not IS_SQLITE,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """A timestamp that is always timezone-aware UTC in Python.

    Postgres stores timestamptz natively, but SQLite drops the offset and hands back naive
    datetimes. Normalising here means the rest of the code never mixes naive and aware times.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to the database; use UTC-aware datetimes")
        value = value.astimezone(UTC)
        # SQLite compares timestamps as text, so store them all in one naive-UTC format.
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def ensure_schema(bind) -> None:
    """Create any missing tables. Switch to Alembic migrations once the schema starts changing."""
    from . import models  # noqa: F401  (registers the tables on Base.metadata)

    Base.metadata.create_all(bind=bind)


def get_db():
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
