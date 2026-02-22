"""
SQLAlchemy ORM models for the app.

Defines Base (declarative base for all models) and Node. Each Node row is one
machine identified by MAC; the reinstall flag tells /boot whether to serve the
Ubuntu installer script or a local-disk boot script.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Declarative base for all ORM models. Subclass this to define new tables.
    """
    pass


class Node(Base):
    """
    One machine known by its MAC address. reinstall toggles installer vs local
    boot; last_seen is updated on each /boot; created_at is set on insert.
    """
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mac: Mapped[str] = mapped_column(String(17), unique=True, nullable=False, index=True)
    reinstall: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        """
        Return a JSON-serializable dict of this node (mac, reinstall, last_seen,
        created_at). Datetimes are ISO 8601 strings; last_seen may be None.
        """
        return {
            "mac": self.mac,
            "reinstall": self.reinstall,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "created_at": self.created_at.isoformat(),
        }
