"""
/boot route: iPXE entrypoint per MAC. Normalizes MAC, upserts node (create with
reinstall=False if new), updates last_seen, then returns reinstall or local-disk script.
validate_local_boot_script() is exported for use by the nodes route when a
caller sets a per-node local boot command via PUT /nodes/<mac>/local-boot.
"""

import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote

from flask import Response, request

from app.config import (
    PXE_AUTOINSTALL_URL,
    PXE_UBUNTU_INITRD_URL,
    PXE_UBUNTU_ISO_URL,
    PXE_UBUNTU_KERNEL_URL,
    PXE_UKI_URL,
)
from app.db import get_db
from app.models import Node
from app.routes.common import normalize_mac

logger = logging.getLogger(__name__)


def get_client_ip() -> str:
    """
    Derive client IP for the current request. Prefers first value in
    X-Forwarded-For when behind a proxy; otherwise request.remote_addr.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def resolve_url_template(template_url: str, mac: str, client_ip: str) -> str:
    """
    Substitute ${mac}, ${mac_hyphen}, and ${ip} in the template with URL-encoded values.
    ${mac} produces the canonical colon form (e.g. aa:bb:cc:dd:ee:ff, colons URL-encoded).
    ${mac_hyphen} produces hyphen-separated form (e.g. aa-bb-cc-dd-ee-ff) needed by
    pxe-image-host, whose nginx regex and file storage both expect hyphens, not colons.
    Missing placeholders are left as-is.
    """
    out = template_url
    if "${mac}" in out:
        out = out.replace("${mac}", quote(mac, safe=""))
    if "${mac_hyphen}" in out:
        out = out.replace("${mac_hyphen}", quote(mac.replace(":", "-"), safe=""))
    if "${ip}" in out:
        out = out.replace("${ip}", quote(client_ip, safe=""))
    return out


def ipxe_script_reinstall(mac: str, client_ip: str) -> str:
    """
    Build iPXE script that chains to a Unified Kernel Image (UKI) hosted on
    TFTP and passes the autoinstall cmdline as chain arguments.

    The UKI is a single PE/EFI executable that bundles the Ubuntu kernel,
    initrd, and a fallback cmdline (built via systemd-stub + objcopy). It exists
    to work around two firmware-era bugs that broke our earlier "iPXE kernel +
    initrd" flow on old HP OEM UEFI (circa 2012-2014): the initrd handoff bug
    (kernel never sees the initrd loaded via EFI_LOAD_FILE2_PROTOCOL), and the
    cmdline-truncation/loss bug (kernel cmdline isn't passed correctly across
    EFI hand-off). Bundling everything into one signed PE binary lets the
    firmware load it like any normal EFI app and the systemd-stub then does the
    Linux setup itself.

    Critical: the cmdline MUST be passed as iPXE chain arguments, not relied
    on from the UKI's embedded .cmdline section. iPXE concatenates the image
    name with any extra args and sets the result as the EFI LoadOptions for
    the chained binary. When LoadOptions are non-empty, systemd-stub uses them
    INSTEAD of the embedded .cmdline (it does not append). With no chain args,
    iPXE passes just "uki.efi" as LoadOptions, which contains none of casper's
    expected tokens (url=, netboot=, ip=, autoinstall, ds=) - so casper sees an
    empty NETBOOT, skips the network mount, scans the local SSD, finds no live
    medium, and drops to the "Attempt interactive netboot from a URL?" prompt.
    See ipxe/ipxe discussion #1367 and the systemd-stub man page.

    Parameters:
    - url=<iso-url>: tells casper to download the live-server ISO via HTTP and
      loop-mount it as the live medium. Must end in ".iso" (casper case glob).
    - netboot=url: forces casper down the do_urlmount path. Redundant when url=
      is matched (url=*.iso sets NETBOOT=url too) but kept explicit for clarity.
    - ip=dhcp: configures initrd networking so casper can fetch the ISO.
    - cloud-config-url=/dev/null: prevents the installer from hanging at
      systemd-update-done.service waiting for an unused cloud-config datasource.
    - autoinstall + ds=nocloud-net;s=<seed>/: drives a fully unattended install.
      Trailing slash is mandatory; cloud-init concatenates filenames directly.

    "imgfree" before chain clears any previously loaded image so systemd-stub
    doesn't trip on a stale EFI_LOAD_FILE2_PROTOCOL registration.
    """
    autoinstall_url = resolve_url_template(PXE_AUTOINSTALL_URL, mac, client_ip)
    if not autoinstall_url.endswith("/"):
        autoinstall_url += "/"

    iso_param = f"url={PXE_UBUNTU_ISO_URL} " if PXE_UBUNTU_ISO_URL else ""
    # PXE_UKI_URL defaults to tftp://${next-server}/uki.efi which iPXE resolves
    # at runtime to whatever DHCP next-server the client received. Operators
    # whose DHCP does not set siaddr override it via env var.
    return (
        "#!ipxe\n"
        "imgfree\n"
        f"chain --replace --autofree {PXE_UKI_URL} "
        f"{iso_param}netboot=url ip=dhcp cloud-config-url=/dev/null "
        f"autoinstall ds=nocloud-net;s={autoinstall_url}\n"
    )


def validate_local_boot_script(script: str) -> bool:
    """
    Return True when script is a safe, recognised iPXE local-boot command.

    Allowed forms:
      - "exit"                              (return control to UEFI firmware)
      - "sanboot [flags]"                   (directly boot a local or SAN disk)

    For sanboot the accepted flags are:
      --no-describe          suppress iBFT table generation
      --keep                 don't detach the SAN drive on failure
      --drive      <value>   0x80..0xff (BIOS drive number) or 0..255 decimal (UEFI)
      --filename   <path>    Windows EFI path, e.g. \\EFI\\ubuntu\\grubx64.efi
      --extra      <path>    same format; selects partition containing this path
      --label      <text>    volume label (alphanumeric, spaces, hyphens, underscores)
      --uuid       <guid>    GPT partition GUID

    Unknown tokens or anything other than-1- "exit" / "sanboot" are rejected to
    prevent arbitrary iPXE code injection via the API.
    """
    if script == "exit":
        return True

    parts = script.split()
    if not parts or parts[0] != "sanboot":
        return False

    # Flags that stand alone (no following value).
    standalone_flags = {"--no-describe", "--keep"}
    # Flags that take one following argument; each maps to a validation pattern.
    arg_flags = {
        "--drive": re.compile(r"^(?:0x[0-9a-fA-F]{1,2}|[0-9]{1,3})$"),
        "--filename": re.compile(r"^\\[A-Za-z0-9\\._\-]{1,127}$"),
        "--extra": re.compile(r"^\\[A-Za-z0-9\\._\-]{1,127}$"),
        "--label": re.compile(r"^[A-Za-z0-9][A-Za-z0-9_ \-]{0,30}$"),
        "--uuid": re.compile(
            r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$"
        ),
    }

    i = 1
    while i < len(parts):
        token = parts[i]
        if token in standalone_flags:
            i += 1
        elif token in arg_flags:
            if i + 1 >= len(parts):
                return False  # flag with no value
            if not arg_flags[token].match(parts[i + 1]):
                return False  # value failed format check
            i += 2
        else:
            return False  # unknown token

    return True


def ipxe_script_local_disk(local_boot_script: str | None) -> str:
    """
    Build the iPXE script served to a node that does not need reinstalling.

    When local_boot_script is None (default), returns a plain "exit" so the
    UEFI Boot Manager advances to the next BootOrder entry (the OS). When a
    per-node script is set (e.g. "sanboot --no-describe --drive 0x80"), that
    command is used instead - useful on firmware where a clean "exit" stalls
    at a boot menu or on legacy BIOS machines that need an explicit drive target.
    """
    cmd = local_boot_script if local_boot_script is not None else "exit"
    return f"#!ipxe\n{cmd}\n"


def register_boot_route(app):
    """
    Register GET /boot on the Flask app. Expects ?mac=...; returns 400 if invalid.
    Uses one DB session per request to upsert node and choose script.
    """

    @app.route("/boot", methods=["GET"])
    def boot():
        raw_mac = request.args.get("mac")
        mac = normalize_mac(raw_mac) if raw_mac else None
        if not mac:
            logger.warning("boot called with missing or invalid mac: %s", raw_mac)
            return Response("Invalid or missing mac\n", status=400, mimetype="text/plain")

        db = next(get_db())
        try:
            node = db.query(Node).filter(Node.mac == mac).first()
            if node is None:
                node = Node(mac=mac, reinstall=False)
                db.add(node)
                db.commit()
                db.refresh(node)
                logger.info("Created node mac=%s", mac)
            node.last_seen = datetime.now(timezone.utc)
            db.commit()

            if node.reinstall:
                client_ip = get_client_ip()
                body = ipxe_script_reinstall(mac, client_ip)
            else:
                body = ipxe_script_local_disk(node.local_boot_script)
            return Response(body, status=200, mimetype="text/plain")
        finally:
            db.close()
