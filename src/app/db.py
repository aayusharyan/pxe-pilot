"""
Database connection and session management.

Provides a SQLite engine and a session factory (SessionLocal). init_db() creates
all ORM-defined tables on first run. get_db() is a generator used per request;
callers should consume one session per request and not reuse across requests.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import DATABASE_PATH
from app.models import Base

# Single engine for the process; check_same_thread=False allows use from
# multiple threads (e.g. Flask request handlers).
engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """
    Create all tables defined on Base-derived models. Idempotent; safe to
    call at startup every time.
    """
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """
    Generator that yields one DB session per call. Caller should use it in a
    try/finally and close when done; do not hold the session across requests.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
