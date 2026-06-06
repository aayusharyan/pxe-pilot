"""
Tests for the SEED_FILE database seeding feature.

Each test writes a fresh YAML file, patches SEED_FILE, resets the DB, then
calls seed_db() directly so the seed runs in isolation without creating a
full Flask app.
"""

import os
import tempfile

import pytest

from app.db import SessionLocal
from app.models import AppConfig, Base, Node
from app.db import engine


@pytest.fixture(autouse=True)
def clean_db():
    """Drop and recreate tables before every test in this module."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _write_seed(content: str) -> str:
    """Write seed YAML to a temp file and return its path."""
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False)
    fh.write(content)
    fh.flush()
    fh.close()
    return fh.name


def test_seed_inserts_new_nodes(monkeypatch):
    """Nodes in seed YAML that are absent from the DB are inserted."""
    path = _write_seed(
        "nodes:\n"
        "  - mac: '3c:52:82:57:ac:ed'\n"
        "    reinstall: false\n"
        "    local_boot_script: 'sanboot --no-describe --drive 0x80'\n"
        "  - mac: '40:b0:34:43:b5:e7'\n"
        "    reinstall: false\n"
    )
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        nodes = db.query(Node).order_by(Node.mac).all()
        assert len(nodes) == 2
        assert nodes[0].mac == "3c:52:82:57:ac:ed"
        assert nodes[0].reinstall is False
        assert nodes[0].local_boot_script == "sanboot --no-describe --drive 0x80"
        assert nodes[1].mac == "40:b0:34:43:b5:e7"
        assert nodes[1].local_boot_script is None
    finally:
        db.close()
    os.unlink(path)


def test_seed_does_not_overwrite_existing_node(monkeypatch):
    """A node already in the DB is never updated by the seed."""
    db = SessionLocal()
    try:
        db.add(Node(mac="3c:52:82:57:ac:ed", reinstall=True, local_boot_script="exit"))
        db.commit()
    finally:
        db.close()

    path = _write_seed(
        "nodes:\n"
        "  - mac: '3c:52:82:57:ac:ed'\n"
        "    reinstall: false\n"
        "    local_boot_script: 'sanboot --no-describe --drive 0x80'\n"
    )
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        node = db.query(Node).filter(Node.mac == "3c:52:82:57:ac:ed").first()
        # Values from the DB (reinstall=True, script=exit) must be preserved.
        assert node.reinstall is True
        assert node.local_boot_script == "exit"
    finally:
        db.close()
    os.unlink(path)


def test_seed_skipped_when_no_seed_file_set(monkeypatch):
    """seed_db() is a no-op when SEED_FILE is empty string."""
    monkeypatch.setattr("app.seed.SEED_FILE", "")

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        assert db.query(Node).count() == 0
    finally:
        db.close()


def test_seed_skipped_when_file_missing(monkeypatch):
    """seed_db() is a no-op when SEED_FILE path does not exist on disk."""
    monkeypatch.setattr("app.seed.SEED_FILE", "/tmp/does_not_exist_pxe_seed.yml")

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        assert db.query(Node).count() == 0
    finally:
        db.close()


def test_seed_skips_invalid_mac(monkeypatch):
    """Entries with invalid MACs are skipped; valid entries still insert."""
    path = _write_seed(
        "nodes:\n"
        "  - mac: 'not-a-mac'\n"
        "    reinstall: false\n"
        "  - mac: 'aa:bb:cc:dd:ee:ff'\n"
        "    reinstall: false\n"
    )
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        nodes = db.query(Node).all()
        assert len(nodes) == 1
        assert nodes[0].mac == "aa:bb:cc:dd:ee:ff"
    finally:
        db.close()
    os.unlink(path)


def test_seed_invalid_script_falls_back_to_none(monkeypatch):
    """An invalid local_boot_script is discarded; the node is still inserted with script=None."""
    path = _write_seed(
        "nodes:\n"
        "  - mac: 'aa:bb:cc:dd:ee:ff'\n"
        "    reinstall: false\n"
        "    local_boot_script: 'kernel http://evil.example/linux'\n"
    )
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        node = db.query(Node).filter(Node.mac == "aa:bb:cc:dd:ee:ff").first()
        assert node is not None
        assert node.local_boot_script is None
    finally:
        db.close()
    os.unlink(path)


def test_seed_normalizes_mac_formats(monkeypatch):
    """Seed MACs in hyphen and no-separator form are stored as lowercase colon-separated."""
    path = _write_seed(
        "nodes:\n"
        "  - mac: 'AA-BB-CC-DD-EE-FF'\n"
        "    reinstall: false\n"
        "  - mac: '112233445566'\n"
        "    reinstall: true\n"
    )
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        macs = {n.mac for n in db.query(Node).all()}
        assert "aa:bb:cc:dd:ee:ff" in macs
        assert "11:22:33:44:55:66" in macs
    finally:
        db.close()
    os.unlink(path)


def test_seed_reinstall_defaults_to_false(monkeypatch):
    """When 'reinstall' is omitted from a seed entry it defaults to False."""
    path = _write_seed(
        "nodes:\n"
        "  - mac: 'aa:bb:cc:dd:ee:ff'\n"
    )
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        node = db.query(Node).filter(Node.mac == "aa:bb:cc:dd:ee:ff").first()
        assert node.reinstall is False
    finally:
        db.close()
    os.unlink(path)


def test_seed_mixed_existing_and_new(monkeypatch):
    """Seed only inserts new MACs; pre-existing MACs are left untouched."""
    db = SessionLocal()
    try:
        db.add(Node(mac="aa:bb:cc:dd:ee:ff", reinstall=True))
        db.commit()
    finally:
        db.close()

    path = _write_seed(
        "nodes:\n"
        "  - mac: 'aa:bb:cc:dd:ee:ff'\n"
        "    reinstall: false\n"
        "  - mac: '11:22:33:44:55:66'\n"
        "    reinstall: false\n"
        "    local_boot_script: 'sanboot --no-describe --drive 0x80'\n"
    )
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        existing = db.query(Node).filter(Node.mac == "aa:bb:cc:dd:ee:ff").first()
        new = db.query(Node).filter(Node.mac == "11:22:33:44:55:66").first()
        assert existing.reinstall is True  # unchanged
        assert new is not None
        assert new.local_boot_script == "sanboot --no-describe --drive 0x80"
    finally:
        db.close()
    os.unlink(path)


def test_seed_only_runs_once(monkeypatch):
    """Seed is skipped on subsequent container starts; deleted nodes are not re-inserted."""
    path = _write_seed(
        "nodes:\n"
        "  - mac: 'aa:bb:cc:dd:ee:ff'\n"
        "    reinstall: false\n"
    )
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db

    # First run inserts the node.
    seed_db()
    db = SessionLocal()
    try:
        assert db.query(Node).count() == 1
        # Simulate intentional deletion.
        db.query(Node).delete()
        db.commit()
    finally:
        db.close()

    # Second run (container restart) must not re-insert the deleted node.
    seed_db()
    db = SessionLocal()
    try:
        assert db.query(Node).count() == 0
        flag = db.query(AppConfig).filter(AppConfig.key == "is_seed_executed").first()
        assert flag is not None
        assert flag.value == "1"
    finally:
        db.close()
    os.unlink(path)


def test_seed_bad_yaml_is_skipped(monkeypatch):
    """Unparseable YAML causes seed to log and skip without crashing."""
    path = _write_seed("{ bad yaml: [unclosed")
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db
    seed_db()  # must not raise

    db = SessionLocal()
    try:
        assert db.query(Node).count() == 0
    finally:
        db.close()
    os.unlink(path)


def test_seed_wrong_top_level_structure_skipped(monkeypatch):
    """YAML without a top-level 'nodes' list causes seed to skip cleanly."""
    path = _write_seed("machines:\n  - mac: 'aa:bb:cc:dd:ee:ff'\n")
    monkeypatch.setattr("app.seed.SEED_FILE", path)

    from app.seed import seed_db
    seed_db()

    db = SessionLocal()
    try:
        assert db.query(Node).count() == 0
    finally:
        db.close()
    os.unlink(path)
