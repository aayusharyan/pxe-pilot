"""
/boot route: iPXE entrypoint per MAC. Normalizes MAC, upserts node (create with
reinstall=False if new), updates last_seen, then returns reinstall or local-disk script.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import quote

from flask import Response, request

from app.config import (
    PXE_AUTOINSTALL_URL,
    PXE_UBUNTU_INITRD_URL,
    PXE_UBUNTU_KERNEL_URL,
)
from app.db import get_db
from app.models import Node
from app.routes.common import normalize_mac

logger = logging.getLogger(__name__)


def get_client_ip() -> str:
    """
    Derive client IP for the current request. Prefers first value in
    X-Forwarded-For when behind a proxy; otherwise request.remote_addr.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def resolve_url_template(template_url: str, mac: str, client_ip: str) -> str:
    """
    Substitute ${mac} and ${ip} in the template with URL-encoded values.
    Missing placeholders are left as-is.
    """
    out = template_url
    if "${mac}" in out:
        out = out.replace("${mac}", quote(mac, safe=""))
    if "${ip}" in out:
        out = out.replace("${ip}", quote(client_ip, safe=""))
    return out


def ipxe_script_reinstall(mac: str, client_ip: str) -> str:
    """
    Build iPXE script that boots the Ubuntu installer with cloud-init autoinstall.
    Kernel, initrd, and autoinstall URLs are resolved with the given mac and client_ip.
    """
    kernel_url = resolve_url_template(PXE_UBUNTU_KERNEL_URL, mac, client_ip)
    initrd_url = resolve_url_template(PXE_UBUNTU_INITRD_URL, mac, client_ip)
    autoinstall_url = resolve_url_template(PXE_AUTOINSTALL_URL, mac, client_ip)
    return (
        "#!ipxe\n"
        f"kernel {kernel_url} autoinstall ds=nocloud-net;s={autoinstall_url}\n"
        f"initrd {initrd_url}\n"
        "boot\n"
    )


def ipxe_script_local_disk() -> str:
    """
    iPXE script that boots from the first local disk (BIOS drive 0x80)
    instead of the network installer.
    """
    return "#!ipxe\nsanboot --no-describe --drive 0x80\n"


def register_boot_route(app):
    """
    Register GET /boot on the Flask app. Expects ?mac=...; returns 400 if invalid.
    Uses one DB session per request to upsert node and choose script.
    """

    @app.route("/boot", methods=["GET"])
    def boot():
        raw_mac = request.args.get("mac")
        mac = normalize_mac(raw_mac) if raw_mac else None
        if not mac:
            logger.warning("boot called with missing or invalid mac: %s", raw_mac)
            return Response("Invalid or missing mac\n", status=400, mimetype="text/plain")

        db = next(get_db())
        try:
            node = db.query(Node).filter(Node.mac == mac).first()
            if node is None:
                node = Node(mac=mac, reinstall=False)
                db.add(node)
                db.commit()
                db.refresh(node)
                logger.info("Created node mac=%s", mac)
            node.last_seen = datetime.now(timezone.utc)
            db.commit()

            if node.reinstall:
                client_ip = get_client_ip()
                body = ipxe_script_reinstall(mac, client_ip)
            else:
                body = ipxe_script_local_disk()
            return Response(body, status=200, mimetype="text/plain")
        finally:
            db.close()
