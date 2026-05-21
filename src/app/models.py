"""
SQLAlchemy ORM models for the app.

Defines Base (declarative base for all models) and Node. Each Node row is one
machine identified by MAC; the reinstall flag tells /boot whether to serve the
Ubuntu installer script or a local-disk boot script.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import TIMEZONE


class Base(DeclarativeBase):
    """
    Declarative base for all ORM models. Subclass this to define new tables.
    """
    pass


class UTCDateTime(TypeDecorator):
    """
    Timezone-aware DateTime that always normalises to UTC on write and
    re-stamps UTC on read. The rest of the app therefore never has to
    handle naive datetimes - input must be tz-aware, output always is.

    SQLite's datetime column has no native tz support: a plain
    DateTime(timezone=True) still strips tzinfo on write and returns
    naive values on read. This decorator converts to UTC before bind
    and reattaches UTC after fetch, giving the same observable behaviour
    as Postgres's TIMESTAMPTZ. On Postgres/MySQL the underlying
    DateTime(timezone=True) already round-trips natively, so the
    decorator's read-side is effectively a passthrough there.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        """
        Reject naive datetimes (loudly, so any caller still writing one
        gets a clear traceback instead of silently losing offset), and
        convert anything tz-aware into UTC before it touches the column.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                f"naive datetime not allowed; supply a tz-aware value (got {value!r})"
            )
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        """
        Re-stamp UTC on every value coming back. SQLite returns a naive
        datetime; Postgres returns a tz-aware one - normalise both into
        UTC so downstream code can rely on a single shape.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _iso(d: datetime | None) -> str | None:
    """
    Render a stored datetime as an ISO-8601 string with explicit offset.
    Values out of UTCDateTime are guaranteed tz-aware (UTC), so we only
    need to convert into the configured display TIMEZONE. None passes
    through unchanged.
    """
    if d is None:
        return None
    return d.astimezone(TIMEZONE).isoformat()


class Node(Base):
    """
    One machine known by its MAC address. reinstall toggles installer vs local
    boot; last_seen is updated on each /boot; created_at is set on insert.

    Datetime columns use the UTCDateTime decorator so values are stored as UTC
    on every backend and read back tz-aware, regardless of whether the
    underlying dialect supports tz-aware columns natively.
    """
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mac: Mapped[str] = mapped_column(String(17), unique=True, nullable=False, index=True)
    reinstall: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        """
        Return a JSON-serializable dict of this node (mac, reinstall, last_seen,
        created_at). Datetimes are ISO 8601 strings with an explicit offset
        (per TIMEZONE) so clients can parse them without guessing.
        """
        return {
            "mac": self.mac,
            "reinstall": self.reinstall,
            "last_seen": _iso(self.last_seen),
            "created_at": _iso(self.created_at),
        }
