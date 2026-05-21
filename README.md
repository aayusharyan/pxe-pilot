# PXE Pilot

![PXE Pilot header](.github/header.png)

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
  -e PXE_AUTOINSTALL_URL=http://image-host/autoinstall/\${mac} \
  -e PXE_BASE_URL=http://pxe-pilot:8000 \
  ghcr.io/aayusharyan/pxe-pilot:latest
```

**TFTP in the same container (routers that need TFTP)**

If your router only supports TFTP (separate "TFTP Server" and "Filename" fields), you can run TFTP in this container too. Set `PXE_BASE_URL` and `PXE_TFTP_ENABLED: "1"`. Set the router's **TFTP Server** (and **Network boot → Server IP**) to this host's IP.

1. In the compose file's `environment` section, set `PXE_BASE_URL` (e.g. `http://pxe-pilot:8000` or the host's LAN IP) and `PXE_TFTP_ENABLED: "1"`. The default compose file and Plain Docker example already map UDP port 69.

Two-stage flow: the container serves the iPXE binary via TFTP (stage 1; embedded script tries `tftp://${next-server}/boot.ipxe`). At startup we generate `boot.ipxe` and `autoexec.ipxe` (stage 2) - both contain `chain PXE_BASE_URL/chain` - so the client reaches this app over HTTP. Generated at runtime because `PXE_BASE_URL` comes from the container environment. No separate TFTP host needed.

`${next-server}` is the DHCP `siaddr` field. Some routers (e.g. Unifi UDM) do not populate `siaddr` and only set option 66 as a string - in that case the `boot.ipxe` chain fails silently and iPXE automatically falls back to requesting `autoexec.ipxe` via TFTP. Both files contain identical content so either path reaches the app.

**UEFI HTTP stack and macvlan: use two containers**

iPXE running in UEFI mode has a separate network stack from the installed OS. In deployments where the TFTP server runs as a Docker macvlan container (dedicated LAN IP, e.g. `192.168.10.151`), iPXE's UEFI HTTP stack cannot reliably reach that macvlan IP via TCP - TFTP (UDP) works, but HTTP chains time out. The host machine's own bridge IP (e.g. `192.168.10.2`) is reachable.

To handle this, run two containers that share one database volume:

- **`pxe-pilot`** - macvlan on the first VIP (e.g. `192.168.10.151`), `PXE_TFTP_ENABLED: "1"`. Serves iPXE binaries and TFTP boot scripts. Router DHCP `next-server` points here. Set `PXE_BASE_URL` to the second VIP so TFTP scripts chain there.
- **`pxe-pilot-http`** - macvlan on a second VIP (e.g. `192.168.10.152`), `PORT: "80"`. HTTP API only (no TFTP). Shares the same `pxe-data` volume so both containers use the same SQLite database.

**Why two IPs, not host networking:** iPXE's UEFI HTTP stack can reach other devices on the same physical network segment (macvlan), but cannot reach the Docker host's own IP - the host is not on the macvlan bridge from iPXE's perspective. Port 80 is mandatory; UEFI HTTP implementations skip non-standard ports.

**Why explicit `dhcp` in embed.ipxe:** the UEFI firmware handles TFTP (step 1) using its own network stack. When `ipxe.efi` starts, it has its own fresh network stack with no IP. Without an explicit `dhcp` call in the embedded script, HTTP chains fail with "Network unreachable" even though TFTP worked.

Both containers share the same `pxe-data` volume so they use the same SQLite database. The admin API (POST/DELETE `/nodes/<mac>/reinstall`) is available at the host IP port.

**Choosing the right TFTP filename (BIOS vs UEFI)**

The container ships three binaries in `/tftpboot/`. The router only ever points at the first stage (`undionly.kpxe` or `ipxe.efi`); the third (`uki.efi`) is chained by the per-MAC reinstall script.

| Filename        | Stage   | Firmware    | Purpose                                                                                                                         |
| --------------- | ------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `undionly.kpxe` | Stage 1 | Legacy BIOS | x86 real-mode iPXE; will not execute on UEFI machines                                                                           |
| `ipxe.efi`      | Stage 1 | UEFI        | PE32+ iPXE; embed.ipxe inside it chains to the HTTP API                                                                         |
| `uki.efi`       | Stage 3 | UEFI        | Unified Kernel Image: Ubuntu kernel + initrd + systemd-stub bundled in one PE binary; chained by the reinstall script over TFTP |

Most routers apply one Stage 1 filename globally per network/VLAN. If all your machines are UEFI (the common case for modern homelab hardware), set the filename to `ipxe.efi`.

**Why a UKI for stage 3:** old HP OEM UEFI firmware (~2012–2014) has two bugs that break the standard "iPXE → kernel + initrd" handoff:

1. **Initrd handoff bug** - kernel never sees the initrd loaded via `EFI_LOAD_FILE2_PROTOCOL`; boot panics with `VFS: Cannot open root device`.
2. **Cmdline truncation/loss** - the kernel command line is not preserved across the EFI hand-off; casper ends up with no `url=`/`autoinstall`/`ds=` and drops to the interactive netboot prompt.

The UKI is a single PE/EFI executable built with `systemd-stub` + `objcopy` that bundles the kernel, initrd, an `os-release` blurb, and a fallback cmdline into one binary the firmware can load like any normal EFI app. This sidesteps both protocol bugs. The runtime cmdline is passed by iPXE as **chain arguments** (which become EFI `LoadOptions`); `systemd-stub` uses `LoadOptions` over the embedded `.cmdline` when non-empty, so the per-MAC autoinstall parameters always reach casper.

**Secure Boot must be disabled.** None of these binaries (iPXE or the UKI) are signed by a trusted UEFI CA. UEFI firmware with Secure Boot enabled will download the binary and immediately abort - the symptom in TFTP logs is `error 0 TFTP Aborted received` right after a successful send. Disable Secure Boot in the machine's BIOS/UEFI settings before PXE booting.

For development setup, see [Contributing](CONTRIBUTING.md).

## Endpoints

| Method | Path                     | Description                                                                                                                      |
| ------ | ------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
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

- **Reinstall:** Chain to the bundled `uki.efi` over TFTP and pass the autoinstall cmdline as iPXE chain arguments. The installer fetches `<autoinstall_url>/user-data` and `<autoinstall_url>/meta-data` (nocloud-net). The autoinstall URL supports `${mac}`, `${mac_hyphen}`, and `${ip}` (replaced with client MAC, hyphen-separated MAC, and IP, URL-encoded). `PXE_UBUNTU_KERNEL_URL` and `PXE_UBUNTU_INITRD_URL` are not used by the UKI flow but are kept in the config schema for callers that build their own non-UKI scripts.

  Ubuntu 24.04 casper PXE cmdline (matches the top answer on [askubuntu Q1513081](https://askubuntu.com/questions/1513081/pxe-booting-ubuntu-24-04-lts-autoinstall) and Ubuntu's own ISO grub.cfg):
  - `ip=dhcp` - configures networking inside the initrd so casper can download the ISO.
  - `url=<iso_url>` - tells casper where to fetch the live ISO to mount the squashfs root. Set `PXE_UBUNTU_ISO_URL` to enable.
  - `netboot=url` - forces casper down the `do_urlmount` path. Redundant when `url=*.iso` matches (which also sets `NETBOOT=url`), but kept explicit so an apex/redirect URL does not silently fall back to the local-medium scan.
  - `cloud-config-url=/dev/null` - prevents the installer from hanging at `systemd-update-done.service`.
  - `autoinstall ds=nocloud-net;s=<autoinstall_url>/` - drives a fully unattended install, fetching user-data and meta-data from the seed URL. **Trailing `/` is mandatory** - cloud-init concatenates filenames directly with no path separator.

  Do **not** add `root=/dev/ram0`, `ramdisk_size=...`, or `boot=casper`. Older docs and some answers suggest them, but the Ubuntu 24.04 stable kernel does not build `CONFIG_BLK_DEV_RAM` in, so `/dev/ram0` does not exist at early boot - the kernel panics with `VFS: Cannot open root device "/dev/ram0", error -6` before the initrd even runs. Ubuntu's own ISO grub.cfg uses `linux /casper/vmlinuz ---` with no `root=` parameter; casper auto-detects itself from the initrd's `/init`.

  The script also runs `imgfree` before `chain` to clear any previously loaded image. Without it, `systemd-stub` trips on a stale `EFI_LOAD_FILE2_PROTOCOL` registration from iPXE and refuses to start with `Error registering initrd: Already started`.

- **Local disk:** `sanboot --no-describe --drive 0x80`.

## Environment variables

Set these in the compose file's `environment` block (or with `-e` for Plain Docker). The compose file you download is the reference for names and example values.

- **Required:** `PXE_UBUNTU_KERNEL_URL`, `PXE_UBUNTU_INITRD_URL`, `PXE_AUTOINSTALL_URL`, `PXE_BASE_URL`
- **Optional:** `PXE_UBUNTU_ISO_URL` (URL to the Ubuntu live-server ISO; required for Ubuntu 24.04 casper boot), `PXE_UKI_URL` (where iPXE chains the UKI from; default `tftp://${next-server}/uki.efi`, override when DHCP siaddr is not populated - e.g. some Unifi setups), `DATABASE_PATH` (default: pxe.db), `PXE_TFTP_ENABLED` (1/true/yes to run TFTP in container), `PORT`, `ADMIN_API_KEY`, `TIMEZONE` (IANA name used to render `last_seen`/`created_at` in API responses; storage stays UTC; default `UTC`; e.g. `Asia/Tokyo` yields `+09:00`; invalid name aborts startup)
