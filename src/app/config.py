"""
Configuration loaded from environment variables at import time.

Required URL vars are validated here and in the Docker entrypoint so the app
fails fast when run locally without .env or in Docker with missing vars.
Optional variables use _get() with a default. All values are stripped of whitespace.
"""

import os
import sys

def _get(key: str, default: str = "") -> str:
    """
    Read an optional environment variable. Returns the default when unset
    or when the value is empty after stripping whitespace.
    """
    return (os.environ.get(key) or "").strip() or default

def _require(key: str) -> str:
    """
    Read a required environment variable. Raises SystemExit with a clear message
    if unset or empty after stripping. Keeps validation redundant with Docker entrypoint.
    """
    value = (os.environ.get(key) or "").strip()
    if not value:
        print(f"Fatal: required env var is not set: {key}. Set it in .env or the environment.", file=sys.stderr)
        sys.exit(1)
    return value

# Required URL vars: validated here and in Docker entrypoint. No fallback; fail if missing.
# URLs for kernel, initrd, and cloud-init autoinstall; may contain ${mac} and ${ip}.
PXE_UBUNTU_KERNEL_URL = _require("PXE_UBUNTU_KERNEL_URL")
PXE_UBUNTU_INITRD_URL = _require("PXE_UBUNTU_INITRD_URL")
PXE_AUTOINSTALL_URL = _require("PXE_AUTOINSTALL_URL")
PXE_BASE_URL = _require("PXE_BASE_URL")

# URL to the Ubuntu live server ISO served by pxe-image-host (e.g.
# http://HOST/ubuntu/24.04/ubuntu.iso). When set, the casper kernel cmdline includes
# ip=dhcp and url=<iso-url> so casper can locate the squashfs root filesystem at boot.
# Required for Ubuntu 24.04 casper-based PXE boot; without it casper panics with
# "VFS: Cannot open root device".
PXE_UBUNTU_ISO_URL = _get("PXE_UBUNTU_ISO_URL", "")

# URL the reinstall script tells iPXE to chain to for the Unified Kernel Image.
# Defaults to tftp://${next-server}/uki.efi, which iPXE resolves at runtime to
# whatever DHCP next-server (siaddr) the client received - the pxe-pilot TFTP
# container by definition, since the router DHCP entry already points there.
# Override when the DHCP server does not populate siaddr (e.g. some Unifi setups
# that only set option 66 as a string) or when the UKI lives on a different
# host. Plain hostnames and explicit IPs both work; the value is passed
# verbatim into the chain line.
PXE_UKI_URL = _get("PXE_UKI_URL", "tftp://${next-server}/uki.efi")

# Path to the SQLite database file. Default is pxe.db in the current directory.
DATABASE_PATH = _get("DATABASE_PATH", "pxe.db")

# When set, admin routes require Authorization: Bearer <key>. If unset, those
# routes are unprotected (not recommended in production).
ADMIN_API_KEY = _get("ADMIN_API_KEY", "")
