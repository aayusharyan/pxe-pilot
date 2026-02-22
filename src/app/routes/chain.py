"""
/chain route: bootstrap iPXE script that chains to /boot?mac=${mac} with
local-disk fallback. Set DHCP boot filename to this URL, e.g. http://pxe-pilot/chain or
http://pxe-pilot:8000/chain .
"""

from flask import Response

from app.config import PXE_BASE_URL


def ipxe_script_chain_with_fallback(boot_base_url: str) -> str:
    """
    Bootstrap iPXE script: chain to /boot?mac=${mac}; on error, fall back to
    booting from local disk. Intended as the DHCP filename so clients still
    boot when the server is down.
    """
    boot_url = boot_base_url.rstrip("/") + "/boot"
    # Fallback: exit so BIOS/firmware continues with next device in boot order.
    return (
        "#!ipxe\n"
        f"chain {boot_url}?mac=${{mac}} || goto fallback\n"
        ":fallback\n"
        "echo Boot server unavailable, continuing with next boot device configured in BIOS\n"
        "exit\n"
    )


def register_chain_route(app):
    """
    Register GET /chain on the Flask app. Returns plain-text iPXE script that
    tells the client to chain to /boot?mac=${mac}; on failure, boot local disk.
    """

    @app.route("/chain", methods=["GET"])
    def chain():
        base = PXE_BASE_URL.rstrip("/")
        body = ipxe_script_chain_with_fallback(base)
        return Response(body, status=200, mimetype="text/plain")
