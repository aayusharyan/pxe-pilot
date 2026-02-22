# PXE Pilot

**Steer your homelab's PXE boot.**

Minimal API that decides whether a machine reinstalls (via PXE) or boots from local disk. iPXE calls `GET /boot?mac=...` and receives a plain-text iPXE script. Supports any Linux flavor; you supply kernel, initrd, and autoinstall URLs from your own image host.

**Links:** [License](LICENSE) · [Contributing](CONTRIBUTING.md) · [Architecture](CONTRIBUTING.md#architecture) · [Security](SECURITY.md)

## Requirements

- **Quick start / production:** Docker
- **Development only:** Python 3.11+, SQLite (file on disk)

## Quick start (Docker)

**Docker Compose**

Pull the image and download the compose file from this repo; edit the compose file's `environment` block, then run.

```bash
# Pull the image (use the image name your registry publishes)
docker pull ghcr.io/aayusharyan/pxe-pilot:latest

# Download the compose file (no clone)
curl -o docker-compose.yml https://raw.githubusercontent.com/aayusharyan/pxe-pilot/main/docker-compose.example.yml
# Edit docker-compose.yml: set the environment block (PXE_UBUNTU_*_URL, PXE_AUTOINSTALL_URL, PXE_BASE_URL). See Environment variables below.

docker compose up -d
```

Server listens on `http://0.0.0.0:8000`. DB is in the `pxe-data` volume at `/data/pxe.db`. If you set `PXE_TFTP_ENABLED` (e.g. `"1"` in the compose file's `environment`), the container also serves TFTP on UDP port 69.

**Plain Docker (pull and run)**

```bash
docker pull ghcr.io/aayusharyan/pxe-pilot:latest
docker run -d \
  --name pxe-pilot \
  -p 8000:8000 \
  -p 69:69/udp \
  -v pxe-data:/data \
  -e PXE_UBUNTU_KERNEL_URL=http://image-host/ubuntu/vmlinuz \
  -e PXE_UBUNTU_INITRD_URL=http://image-host/ubuntu/initrd \
  -e PXE_AUTOINSTALL_URL=http://image-host/autoinstall.yaml \
  -e PXE_BASE_URL=http://pxe-pilot:8000 \
  ghcr.io/aayusharyan/pxe-pilot:latest
```

**TFTP in the same container (routers that need TFTP)**

If your router only supports TFTP (separate "TFTP Server" and "Filename" fields), you can run TFTP in this container too. Set `PXE_BASE_URL` and `PXE_TFTP_ENABLED: "1"`. Set the router's **TFTP Server** (and **Network boot → Server IP**) to this host's IP; **Filename** = `undionly.kpxe`.

1. In the compose file's `environment` section, set `PXE_BASE_URL` (e.g. `http://pxe-pilot:8000` or the host's LAN IP) and `PXE_TFTP_ENABLED: "1"`. The default compose file and Plain Docker example already map UDP port 69.

Two-stage flow: the container serves undionly.kpxe (stage 1; script inside only says “TFTP get boot.ipxe”). At startup we generate boot.ipxe (stage 2) with `chain PXE_BASE_URL/chain`, so the client then uses HTTP to reach this app. We generate boot.ipxe at runtime because PXE_BASE_URL comes from the container environment (e.g. compose `environment`). No separate TFTP host needed.

For development setup, see [Contributing](CONTRIBUTING.md).

## Endpoints

| Method | Path                     | Description                                                                                                                      |
|--------|--------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| GET    | `/chain`                 | iPXE bootstrap: chain to `/boot?mac=${mac}`; on failure, exit so BIOS continues with next boot device. Point DHCP filename here. |
| GET    | `/boot?mac=...`          | iPXE script: reinstall or local disk. Creates/updates node; updates last_seen.                                                   |
| GET    | `/nodes`                 | JSON list of nodes (MAC, reinstall, last_seen, created_at).                                                                      |
| POST   | `/nodes/<mac>/reinstall` | Set reinstall=true for MAC.                                                                                                      |
| DELETE | `/nodes/<mac>/reinstall` | Set reinstall=false for MAC.                                                                                                     |
| GET    | `/health`                | `{"status":"OK"}`.                                                                                                               |

MAC: colon or hyphen separated; stored as lowercase colon (e.g. `aa:bb:cc:dd:ee:ff`). Boot and chain are unauthenticated. For `/nodes` and reinstall endpoints you can set `ADMIN_API_KEY` and send `Authorization: Bearer <key>` (see [SECURITY.md](SECURITY.md)).

## How PXE boot works

Your DHCP server (option 67 / boot filename) gives the client a URL. **Point DHCP at `/chain`** (same URL for all clients; no MAC in the URL).

- DHCP filename: `http://pxe-pilot/chain` (or your host/port, e.g. `http://pxe-pilot:8000/chain`).
- The client fetches `/chain` and gets a small script that tells iPXE to fetch `/boot?mac=${mac}`; if that fails, iPXE exits so the BIOS continues with the next boot device (e.g. local disk).
- The client then requests `/boot?mac=...` and gets the real script (reinstall or local disk).

**`PXE_BASE_URL` (required)**

The `/chain` script contains a URL like `http://pxe-pilot/boot?mac=${mac}`. Set `PXE_BASE_URL` to the base URL clients use to reach this app (e.g. `http://pxe-pilot:8000` or `http://pxe-pilot`) in the compose file's `environment` or Environment variables below.

**What the chain script looks like**

```
#!ipxe
chain http://pxe-pilot/boot?mac=${mac} || goto fallback
:fallback
echo Boot server unavailable, continuing with next boot device
exit
```

## iPXE behaviour

- **Reinstall:** Load kernel and initrd from configured URLs; boot with `autoinstall ds=nocloud-net;s=<autoinstall_url>`. Kernel, initrd, and autoinstall URLs all support `${mac}` and `${ip}` (replaced with client MAC and IP, URL-encoded).
- **Local disk:** `sanboot --no-describe --drive 0x80`.

## Environment variables

Set these in the compose file's `environment` block (or with `-e` for Plain Docker). The compose file you download is the reference for names and example values.

- **Required:** `PXE_UBUNTU_KERNEL_URL`, `PXE_UBUNTU_INITRD_URL`, `PXE_AUTOINSTALL_URL`, `PXE_BASE_URL`
- **Optional:** `DATABASE_PATH` (default: pxe.db), `PXE_TFTP_ENABLED` (1/true/yes to run TFTP in container), `PORT`, `ADMIN_API_KEY`
