"""
Shared helpers used by more than one route: MAC normalization and admin auth.

Used by boot and nodes (normalize_mac); nodes only (require_admin_auth). No
route-specific logic (e.g. iPXE scripts) lives here.
"""

import hmac
import re

from flask import request

from app.config import ADMIN_API_KEY

# Six groups of two hex digits; optional colon or hyphen between groups.
MAC_PATTERN = re.compile(
    r"^([0-9a-fA-F]{2})[-:]?([0-9a-fA-F]{2})[-:]?([0-9a-fA-F]{2})[-:]?([0-9a-fA-F]{2})[-:]?([0-9a-fA-F]{2})[-:]?([0-9a-fA-F]{2})$"
)


def normalize_mac(raw: str) -> str | None:
    """
    Convert a MAC string to canonical form: lowercase hex with colons.
    Returns None if the input is not a valid 6-octet MAC (with or without separators).
    """
    if not raw or not isinstance(raw, str):
        return None
    m = MAC_PATTERN.match(raw.strip())
    if not m:
        return None
    return ":".join(g.lower() for g in m.groups())


def require_admin_auth() -> tuple[dict, int] | None:
    """
    Enforce admin auth when ADMIN_API_KEY is set: expect Bearer token in
    Authorization header. Returns (error_dict, status_code) on failure;
    None when key is unset or token matches (constant-time).
    """
    if not ADMIN_API_KEY:
        return None
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return ({"error": "Missing or invalid Authorization header (expected Bearer token)"}, 401)
    token = auth[7:].strip()
    if not hmac.compare_digest(token, ADMIN_API_KEY):
        return ({"error": "Invalid API key"}, 401)
    return None
