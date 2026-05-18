#!/bin/sh
# Container entrypoint: optionally start TFTP (dnsmasq) when env is set, then run the Flask app with gunicorn.
# TFTP is for routers that only offer "TFTP server + filename": we serve the iPXE binaries and two generated
# scripts - boot.ipxe (chained by embed.ipxe via ${next-server}) and autoexec.ipxe (iPXE's built-in fallback
# when the embedded script fails, e.g. when the router doesn't populate ${next-server}/siaddr). Both scripts
# chain to this app over HTTP. Written at runtime so PXE_BASE_URL from the environment is used.

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
  # Strip trailing slash so the chain URL is clean (e.g. http://pxe-pilot/chain).
  base="${PXE_BASE_URL%/}"
  # boot.ipxe is chain-loaded by embed.ipxe via tftp://${next-server}/boot.ipxe and redirects to HTTP.
  printf '#!ipxe\nchain %s/chain\n' "$base" > /tftpboot/boot.ipxe
  # autoexec.ipxe is iPXE's built-in fallback: when the embedded script can't resolve ${next-server}
  # (e.g. the router sets option 66 but not siaddr), iPXE requests this file via TFTP automatically.
  printf '#!ipxe\nchain %s/chain\n' "$base" > /tftpboot/autoexec.ipxe
  # Run dnsmasq as TFTP server: no DHCP (-p 0), TFTP on default port, serve files from /tftpboot. Run in background so gunicorn can start.
  dnsmasq --no-daemon -p 0 --enable-tftp --tftp-root=/tftpboot --user=root &
fi

# Start the Flask app. Single worker is enough for typical homelab use; app:app is the WSGI callable.
# --access-logfile - writes HTTP request logs to stdout so docker logs captures them.
# PORT is optional (default 8000); see README Environment variables.
exec gunicorn -b "0.0.0.0:${PORT:-8000}" -w 1 --access-logfile - app:app
