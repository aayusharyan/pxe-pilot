"""
Database connection and session management.

Provides a SQLite engine and a session factory (SessionLocal). init_db() creates
all ORM-defined tables on first run. migrate_db() applies schema changes to an
existing database (ALTER TABLE for new columns). get_db() is a generator used
per request; callers should consume one session per request and not reuse across.
"""

from sqlalchemy import create_engine, text
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


def migrate_db() -> None:
    """
    Apply incremental schema changes to an existing database. Uses PRAGMA
    table_info to detect missing columns; ALTER TABLE to add them. Safe to
    call at startup after init_db() - the check is idempotent and a no-op
    when the schema is already current.

    Must be extended whenever a new column is added to an ORM model so that
    existing deployments pick up the change on the next container start
    without a full DB wipe.
    """
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(nodes)"))
        existing_columns = {row[1] for row in result}

        # local_boot_script: per-node iPXE command used for local disk boot
        if "local_boot_script" not in existing_columns:
            conn.execute(text("ALTER TABLE nodes ADD COLUMN local_boot_script TEXT"))
            conn.commit()


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
