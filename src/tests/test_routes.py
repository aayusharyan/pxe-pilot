"""
Tests for HTTP endpoints and route helpers: /health, /chain, /boot, /nodes,
reinstall toggles, and admin auth. Uses fixtures from conftest (client, reset_db).
"""

import pytest


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
    assert "sanboot" in body and "0x80" in body
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


def test_boot_with_reinstall_true_returns_kernel_script(client):
    """When node has reinstall=True, GET /boot returns Ubuntu installer iPXE script."""
    mac = "11:22:33:44:55:66"
    client.post(f"/nodes/{mac}/reinstall")
    r = client.get("/boot", query_string={"mac": mac})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "kernel" in body and "initrd" in body and "autoinstall" in body


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
