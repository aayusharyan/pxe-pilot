#!/bin/sh
# Container entrypoint: optionally start TFTP (dnsmasq) when env is set, then run the Flask app with gunicorn.
# TFTP is for routers that only offer "TFTP server + filename": we serve undionly.kpxe and a generated boot.ipxe
# that chains to this app over HTTP. boot.ipxe is written at runtime so PXE_BASE_URL from .env can be used.

set -e

# All required env vars must be set when running in Docker. Fail fast with a clear message.
missing=""
[ -z "$PXE_BASE_URL" ] && missing="${missing} PXE_BASE_URL"
[ -z "$PXE_UBUNTU_KERNEL_URL" ] && missing="${missing} PXE_UBUNTU_KERNEL_URL"
[ -z "$PXE_UBUNTU_INITRD_URL" ] && missing="${missing} PXE_UBUNTU_INITRD_URL"
[ -z "$PXE_AUTOINSTALL_URL" ] && missing="${missing} PXE_AUTOINSTALL_URL"
if [ -n "$missing" ]; then
  echo "Fatal: required env vars are not set:${missing}. See https://github.com/aayusharyan/pxe-pilot/blob/main/README.md" >&2
  exit 1
fi

# If TFTP is enabled, run the two-stage TFTP setup before starting the app.
if [ -n "$PXE_TFTP_ENABLED" ]; then
  mkdir -p /tftpboot
  # Strip trailing slash so the chain URL is clean (e.g. http://host:8000/chain).
  base="${PXE_BASE_URL%/}"
  # boot.ipxe is what undionly.kpxe (embed.ipxe) chain-loads via TFTP. It tells the client to fetch the real script from this app over HTTP.
  printf '#!ipxe\nchain %s/chain\n' "$base" > /tftpboot/boot.ipxe
  # Run dnsmasq as TFTP server: no DHCP (-p 0), TFTP on default port, serve files from /tftpboot. Run in background so gunicorn can start.
  dnsmasq --no-daemon -p 0 --enable-tftp --tftp-root=/tftpboot --user=root &
fi

# Start the Flask app. Single worker is enough for typical homelab use; app:app is the WSGI callable.
exec gunicorn -b 0.0.0.0:8000 -w 1 app:app
