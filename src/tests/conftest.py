"""
Pytest configuration and shared fixtures.

Sets required env vars before app import so the app starts in tests; provides
test client and clean DB per test.
"""

import os
import tempfile

import pytest


# Set required env vars before app or config are imported (config exits if unset).
os.environ.setdefault("PXE_UBUNTU_KERNEL_URL", "http://pxe-pilot/vmlinuz")
os.environ.setdefault("PXE_UBUNTU_INITRD_URL", "http://pxe-pilot/initrd")
os.environ.setdefault("PXE_AUTOINSTALL_URL", "http://pxe-pilot/autoinstall")
os.environ.setdefault("PXE_BASE_URL", "http://pxe-pilot")
os.environ.setdefault("DATABASE_PATH", os.path.join(tempfile.gettempdir(), f"pxe_test_{os.getpid()}.db"))

from app import create_app
from app.db import engine
from app.models import Base


@pytest.fixture(autouse=True)
def reset_db():
    """Drop and recreate all tables before each test so tests see a clean DB."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    """Flask test client for the app (fresh app per test, DB already reset)."""
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c
