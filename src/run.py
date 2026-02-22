"""
Development server entrypoint. Runs Flask on 0.0.0.0:8000.
Production should use gunicorn (see Dockerfile and README).
"""

import logging
import os

from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = create_app()

# Start development server when run as main module; production uses gunicorn.
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    logger.info("Starting dev server on port %s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
