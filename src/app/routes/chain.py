"""
/chain route: bootstrap iPXE script that chains to /boot?mac=${mac} with
local-disk fallback. Point DHCP boot filename here when you need chaining.
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
    return (
        "#!ipxe\n"
        f"chain {boot_url}?mac=${{mac}} || goto fallback\n"
        ":fallback\n"
        "echo Boot server unavailable, booting local disk\n"
        "sanboot --no-describe --drive 0x80\n"
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
