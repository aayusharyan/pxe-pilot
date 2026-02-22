"""
/health route: liveness/readiness probe. Returns simple JSON; no auth required.
"""

from flask import Flask


def register_health_route(app: Flask):
    """
    Register GET /health on the Flask app. Returns {"status": "OK"}.
    """

    @app.route("/health", methods=["GET"])
    def health():
        return {"status": "OK"}
