"""
/nodes routes: list nodes (GET), set reinstall (POST/DELETE on .../reinstall).
Admin-only when ADMIN_API_KEY is set. MAC in path is normalized; node is created if missing.
"""

import logging

from app.db import get_db
from app.models import Node
from app.routes.common import normalize_mac, require_admin_auth

logger = logging.getLogger(__name__)


def register_nodes_routes(app):
    """
    Register GET /nodes, POST /nodes/<mac>/reinstall, DELETE /nodes/<mac>/reinstall.
    Each handler checks admin auth and uses one DB session per request.
    """

    @app.route("/nodes", methods=["GET"])
    def list_nodes():
        """
        Return JSON list of all known nodes (mac, reinstall, last_seen, created_at).
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
