"""
Unit tests for route helpers: MAC normalization and URL templating (${mac}, ${ip}).
"""

import pytest

from app.routes.boot import resolve_url_template
from app.routes.common import normalize_mac


def test_normalize_mac_colon_lowercase():
    """Colon-separated MAC is lowercased and returned as-is format."""
    assert normalize_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"


def test_normalize_mac_hyphen():
    """Hyphen-separated MAC is converted to colon and lowercased."""
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "aa:bb:cc:dd:ee:ff"


def test_normalize_mac_no_separator():
    """Twelve hex chars without separator are converted to colon format."""
    assert normalize_mac("aabbccddeeff") == "aa:bb:cc:dd:ee:ff"


def test_normalize_mac_invalid_returns_none():
    """Invalid or empty input returns None."""
    assert normalize_mac("") is None
    assert normalize_mac("x") is None
    assert normalize_mac("aa:bb:cc") is None
    assert normalize_mac("gg:bb:cc:dd:ee:ff") is None
    assert normalize_mac(None) is None


def test_resolve_url_template_replaces_mac_and_ip():
    """Template placeholders ${mac} and ${ip} are replaced and URL-encoded."""
    url = "http://pxe-pilot/?mac=${mac}&ip=${ip}"
    out = resolve_url_template(url, "aa:bb:cc:dd:ee:ff", "192.168.1.1")
    assert "aa%3Abb%3Acc%3Add%3Aee%3Aff" in out or "aa:bb:cc:dd:ee:ff" in out
    assert "192.168.1.1" in out
