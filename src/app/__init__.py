"""
Application factory for the Flask web app.

This module creates the Flask instance, ensures the database schema exists,
and registers all HTTP routes (/boot, /nodes, /health, /chain). Entry points:
run.py for development, or gunicorn with wsgi:app / app:create_app().
"""

import logging

from flask import Flask

from app.config import ADMIN_API_KEY
from app.db import init_db
from app.routes import register_routes

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """
    Build and return the Flask app. Sets JSON key order, creates DB tables,
    and mounts routes. Logs a security warning if ADMIN_API_KEY is unset.
    """
    app = Flask(__name__)
    app.json.sort_keys = False
    if not ADMIN_API_KEY:
        logger.warning(
            "ADMIN_API_KEY is not set; admin endpoints (/nodes, .../reinstall) are unprotected. This is less secure."
        )
    init_db()
    register_routes(app)
    return app


app = create_app()
