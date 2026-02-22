"""
Configuration loaded from environment variables at import time.

Required variables are read with _require(); if missing, the process exits so the
app does not run with wrong defaults. Optional variables use _get() with a default.
All values are stripped of leading/trailing whitespace.
"""

import os
import sys


def _require(key: str) -> str:
    """
    Read a required environment variable. Exits the process with a clear
    stderr message if the value is unset or empty.
    """
    value = (os.environ.get(key) or "").strip()
    if not value:
        print(f"Fatal: required env {key} is not set or empty.", file=sys.stderr)
        sys.exit(1)
    return value


def _get(key: str, default: str = "") -> str:
    """
    Read an optional environment variable. Returns the default when unset
    or when the value is empty after stripping whitespace.
    """
    return (os.environ.get(key) or "").strip() or default


# URLs for Ubuntu kernel, initrd, and cloud-init autoinstall. Used to build the
# iPXE reinstall script. May contain ${mac} and ${ip}; replaced per boot with
# client MAC and IP (URL-encoded).
PXE_UBUNTU_KERNEL_URL = _require("PXE_UBUNTU_KERNEL_URL")
PXE_UBUNTU_INITRD_URL = _require("PXE_UBUNTU_INITRD_URL")
PXE_AUTOINSTALL_URL = _require("PXE_AUTOINSTALL_URL")

# Only relevant when using /chain. Base URL to put in the chain script so the client
# is told to request our /boot; that way the client sends mac (in the URL) and we
# get its IP from the request. Set when behind proxy/Docker/NAT so the URL in the
# script matches what DHCP gives clients; leave empty if the request Host is correct.
PXE_CHAIN_BASE_URL = _get("PXE_CHAIN_BASE_URL", "")

# Path to the SQLite database file. Default is pxe.db in the current directory.
DATABASE_PATH = _get("DATABASE_PATH", "pxe.db")

# When set, admin routes require Authorization: Bearer <key>. If unset, those
# routes are unprotected (not recommended in production).
ADMIN_API_KEY = _get("ADMIN_API_KEY", "")
