"""
Routes package: registers /chain, /boot, /nodes, /health on the Flask app.

Each route group lives in its own module (chain, boot, nodes, health). Shared
helpers (MAC normalization, auth, iPXE scripts) are in common. Entry point is
register_routes(app), used by the app factory.
"""

from flask import Flask


def register_routes(app: Flask) -> None:
    """
    Register all HTTP routes on the given Flask app: /chain, /boot, /nodes, /health.
    Each route module uses get_db() for one session per request where needed.
    """
    from app.routes.boot import register_boot_route
    from app.routes.chain import register_chain_route
    from app.routes.health import register_health_route
    from app.routes.nodes import register_nodes_routes

    register_chain_route(app)
    register_boot_route(app)
    register_nodes_routes(app)
    register_health_route(app)
