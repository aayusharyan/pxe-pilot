"""
/nodes routes: list nodes (GET), set/clear reinstall (POST/DELETE), set/clear
per-node local boot script (PUT/DELETE on .../local-boot-config). Admin-only when
ADMIN_API_KEY is set. MAC in path is normalized; node is created if missing.
"""

import logging

from flask import request

from app.db import get_db
from app.models import Node
from app.routes.boot import validate_local_boot_script
from app.routes.common import normalize_mac, require_admin_auth

logger = logging.getLogger(__name__)


def register_nodes_routes(app):
    """
    Register GET /nodes, POST /nodes/<mac>/reinstall, DELETE /nodes/<mac>/reinstall,
    PUT /nodes/<mac>/local-boot-config, DELETE /nodes/<mac>/local-boot-config.
    Each handler checks admin auth and uses one DB session per request.
    """

    @app.route("/nodes", methods=["GET"])
    def list_nodes():
        """
        Return JSON list of all known nodes (mac, reinstall, local_boot_script,
        last_seen, created_at).
        """
        err = require_admin_auth()
        if err is not None:
            return err[0], err[1]
        db = next(get_db())
        try:
            nodes = db.query(Node).order_by(Node.mac).all()
            return {"nodes": [n.to_dict() for n in nodes]}
        finally:
            db.close()

    @app.route("/nodes/<path:mac_raw>/reinstall", methods=["POST"])
    def set_reinstall(mac_raw: str):
        """
        Set reinstall=True for the given MAC. Creates the node if it does not exist.
        Next /boot from that MAC will serve the installer script.
        """
        err = require_admin_auth()
        if err is not None:
            return err[0], err[1]
        mac = normalize_mac(mac_raw)
        if not mac:
            return {"error": "Invalid or missing mac"}, 400

        db = next(get_db())
        try:
            node = db.query(Node).filter(Node.mac == mac).first()
            if node is None:
                node = Node(mac=mac, reinstall=True)
                db.add(node)
            else:
                node.reinstall = True
            db.commit()
            db.refresh(node)
            logger.info("Set reinstall=True for mac=%s", mac)
            return {"mac": mac, "reinstall": True}
        finally:
            db.close()

    @app.route("/nodes/<path:mac_raw>/reinstall", methods=["DELETE"])
    def clear_reinstall(mac_raw: str):
        """
        Set reinstall=False for the given MAC. Next /boot from that MAC will
        serve the local-disk script. Creates the node if it does not exist.
        """
        err = require_admin_auth()
        if err is not None:
            return err[0], err[1]
        mac = normalize_mac(mac_raw)
        if not mac:
            return {"error": "Invalid or missing mac"}, 400

        db = next(get_db())
        try:
            node = db.query(Node).filter(Node.mac == mac).first()
            if node is None:
                node = Node(mac=mac, reinstall=False)
                db.add(node)
            else:
                node.reinstall = False
            db.commit()
            db.refresh(node)
            logger.info("Set reinstall=False for mac=%s", mac)
            return {"mac": mac, "reinstall": False}
        finally:
            db.close()

    @app.route("/nodes/<path:mac_raw>/local-boot-config", methods=["PUT"])
    def set_local_boot(mac_raw: str):
        """
        Set a per-node iPXE local boot command. Body must be JSON with a
        "script" key. Accepted values are "exit" or a sanboot command
        (see validate_local_boot_script). Returns 400 on invalid input.

        Examples:
          {"script": "sanboot --no-describe --drive 0x80"}  (legacy BIOS)
          {"script": "sanboot --no-describe --drive 0"}     (UEFI first disk)
          {"script": "sanboot --no-describe --drive 1"}     (UEFI second disk)
          {"script": "exit"}                                (UEFI fallback)
        """
        err = require_admin_auth()
        if err is not None:
            return err[0], err[1]
        mac = normalize_mac(mac_raw)
        if not mac:
            return {"error": "Invalid or missing mac"}, 400

        body = request.get_json(silent=True)
        if not body or "script" not in body:
            return {"error": "Request body must be JSON with a 'script' key"}, 400
        script = body["script"]
        if not isinstance(script, str) or not script.strip():
            return {"error": "'script' must be a non-empty string"}, 400
        script = script.strip()
        if not validate_local_boot_script(script):
            return {
                "error": (
                    "Invalid local boot script. Allowed values: 'exit', "
                    "or a sanboot command with safe options "
                    "(--no-describe, --drive <hex/int>, --filename <path>, "
                    "--extra <path>, --label <label>, --uuid <guid>, --keep)"
                )
            }, 400

        db = next(get_db())
        try:
            node = db.query(Node).filter(Node.mac == mac).first()
            if node is None:
                node = Node(mac=mac, reinstall=False, local_boot_script=script)
                db.add(node)
            else:
                node.local_boot_script = script
            db.commit()
            db.refresh(node)
            logger.info("Set local_boot_script=%r for mac=%s", script, mac)
            return {"mac": mac, "local_boot_script": script}
        finally:
            db.close()

    @app.route("/nodes/<path:mac_raw>/local-boot-config", methods=["DELETE"])
    def clear_local_boot(mac_raw: str):
        """
        Reset the per-node local boot script to None (falls back to "exit").
        Creates the node if it does not exist.
        """
        err = require_admin_auth()
        if err is not None:
            return err[0], err[1]
        mac = normalize_mac(mac_raw)
        if not mac:
            return {"error": "Invalid or missing mac"}, 400

        db = next(get_db())
        try:
            node = db.query(Node).filter(Node.mac == mac).first()
            if node is None:
                node = Node(mac=mac, reinstall=False, local_boot_script=None)
                db.add(node)
            else:
                node.local_boot_script = None
            db.commit()
            db.refresh(node)
            logger.info("Cleared local_boot_script for mac=%s", mac)
            return {"mac": mac, "local_boot_script": None}
        finally:
            db.close()
