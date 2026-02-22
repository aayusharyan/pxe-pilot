#!/bin/sh
# Container entrypoint: optionally start TFTP (dnsmasq) when env is set, then run the Flask app with gunicorn.
# TFTP is for routers that only offer "TFTP server + filename": we serve undionly.kpxe and a generated boot.ipxe
# that chains to this app over HTTP. boot.ipxe is written at runtime so PXE_BOOT_BASE_URL from .env can be used.

set -e

# If both TFTP env vars are set, run the two-stage TFTP setup before starting the app.
if [ -n "$PXE_TFTP_ENABLED" ] && [ -n "$PXE_BOOT_BASE_URL" ]; then
  mkdir -p /tftpboot
  # Strip trailing slash so the chain URL is clean (e.g. http://host:8000/chain).
  base="${PXE_BOOT_BASE_URL%/}"
  # boot.ipxe is what undionly.kpxe (embed.ipxe) chain-loads via TFTP. It tells the client to fetch the real script from this app over HTTP.
  printf '#!ipxe\nchain %s/chain\n' "$base" > /tftpboot/boot.ipxe
  # Run dnsmasq as TFTP server: no DHCP (-p 0), TFTP on default port, serve files from /tftpboot. Run in background so gunicorn can start.
  dnsmasq --no-daemon -p 0 --enable-tftp --tftp-root=/tftpboot --user=root &
fi

# Start the Flask app. Single worker is enough for typical homelab use; app:app is the WSGI callable.
exec gunicorn -b 0.0.0.0:8000 -w 1 app:app
