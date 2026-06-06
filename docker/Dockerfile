# Multi-stage build:
#   ipxe  - builds undionly.kpxe (legacy BIOS) and ipxe.efi (UEFI) with embed.ipxe baked in.
#   uki   - builds uki.efi (Unified Kernel Image) bundling Ubuntu kernel + initrd + systemd-stub.
#   final - Flask app plus dnsmasq for TFTP, with all three binaries in /tftpboot.
# Build context is the repo root: docker build -f docker/Dockerfile .

# Stage 1: build iPXE binaries with embed.ipxe baked in. embed.ipxe runs an explicit
# dhcp then chains to tftp://${next-server}/boot.ipxe; boot.ipxe is generated at runtime
# by the entrypoint using PXE_BASE_URL and chains to the HTTP /chain endpoint.
FROM debian:bookworm-slim AS ipxe
# ca-certificates for git TLS; liblzma-dev for iPXE host build (util/zbin).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential git binutils-dev liblzma-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://git.ipxe.org/ipxe.git /ipxe
COPY tftp/embed.ipxe /ipxe/src/embed.ipxe
WORKDIR /ipxe/src
# Build legacy BIOS binary and UEFI binary in one pass so both are available in /tftpboot.
RUN make bin/undionly.kpxe EMBED=embed.ipxe && \
    make bin-x86_64-efi/ipxe.efi EMBED=embed.ipxe

# Stage 2: build the UKI (Unified Kernel Image) - a single PE/EFI binary that
# bundles the Ubuntu netboot kernel, netboot initrd, an os-release blurb, and a
# fallback kernel cmdline. The UKI works around two firmware-era bugs on old HP
# OEM UEFI (~2012–2014) that broke the earlier "iPXE → kernel + initrd" flow:
#   1. EFI_LOAD_FILE2_PROTOCOL initrd handoff bug - kernel never sees the
#      initrd loaded by iPXE/EFI, then panics with "VFS: Cannot open root device".
#   2. Kernel cmdline truncation/loss across EFI hand-off.
# systemd-stub bundles kernel + initrd + cmdline into one signed PE binary that
# firmware loads like any normal EFI app, sidestepping both protocol bugs.
#
# At runtime iPXE chains to uki.efi over TFTP and passes the real autoinstall
# cmdline as chain arguments - iPXE concatenates the image name with extra args
# and sets the result as EFI LoadOptions. systemd-stub uses LoadOptions when
# non-empty (it does NOT append), so the embedded .cmdline below is only a
# fallback for direct firmware boots without iPXE. See app/routes/boot.py for
# the full rationale.
#
# Why Debian trixie: systemd-stub before 256 has an iPXE-systemd protocol
# conflict that returns "Error registering initrd: Already started" on chain.
# Debian trixie ships systemd 257.x with the fix. Bookworm (systemd 252) and
# Ubuntu 24.04 noble (systemd 255) both still hit the bug.
FROM debian:trixie-slim AS uki

# Ubuntu point release pinned for reproducibility. Bump together with the
# pxe-image-host Dockerfile so both sources use the same kernel/initrd pair.
ARG UBUNTU_POINT=24.04.4

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates binutils systemd-boot-efi \
    && rm -rf /var/lib/apt/lists/*

# Fetch the same netboot kernel + initrd that pxe-image-host serves. The
# netboot tarball ships a kernel and initrd built specifically for PXE/iPXE
# handoff; the casper kernel/initrd inside the live-server ISO are built
# for ISO-resident boot and panic when handed off over the network.
RUN mkdir -p /uki && cd /uki && \
    curl -fL --retry 5 --retry-delay 10 --retry-all-errors -o netboot.tar.gz \
      "https://releases.ubuntu.com/24.04/ubuntu-${UBUNTU_POINT}-netboot-amd64.tar.gz" && \
    tar -xzf netboot.tar.gz ./amd64/linux ./amd64/initrd && \
    mv amd64/linux ./linux && \
    mv amd64/initrd ./initrd && \
    rm -rf amd64 netboot.tar.gz

# os-release and fallback cmdline written verbatim into the UKI as section data. The
# major.minor version is derived from UBUNTU_POINT so it stays consistent with the kernel
# and initrd that were fetched above. Runtime iPXE LoadOptions override the cmdline; this
# fallback only matters if someone boots uki.efi directly from firmware (no iPXE chain).
RUN cd /uki && \
    UBUNTU_VERSION=$(echo "${UBUNTU_POINT}" | cut -d. -f1,2) && \
    printf "ID=ubuntu\nNAME=\"Ubuntu Server (PXE installer)\"\nVERSION=\"${UBUNTU_VERSION}\"\nVERSION_ID=\"${UBUNTU_VERSION}\"\nPRETTY_NAME=\"Ubuntu Server ${UBUNTU_VERSION} (PXE)\"\n" > os-release && \
    printf 'console=tty0' > cmdline

# Attach .osrel/.cmdline/.linux/.initrd sections to the systemd-stub PE binary
# at well-separated VMAs so they do not collide with the stub's own .text/.data
# regions. The VMAs match the canonical systemd-ukify layout: low addresses
# for metadata, high addresses for the kernel and initrd payload.
RUN cd /uki && \
    cp /usr/lib/systemd/boot/efi/linuxx64.efi.stub stub.efi && \
    objcopy \
      --add-section   .osrel=os-release             --change-section-vma .osrel=0x16df00000   --set-section-flags .osrel=data,readonly \
      --add-section   .cmdline=cmdline              --change-section-vma .cmdline=0x16df10000 --set-section-flags .cmdline=data,readonly \
      --add-section   .linux=linux                  --change-section-vma .linux=0x16e000000   --set-section-flags .linux=code,readonly \
      --add-section   .initrd=initrd                --change-section-vma .initrd=0x16f000000  --set-section-flags .initrd=data,readonly \
      stub.efi uki.efi

# Stage 3: runtime image. Python app plus dnsmasq for optional TFTP. App and TFTP share the same container.
# tzdata populates /usr/share/zoneinfo so zoneinfo.ZoneInfo(<IANA name>) resolves at runtime;
# without it the TIMEZONE env var (see app/config.py) would fail-fast on any non-UTC value.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends dnsmasq tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/requirements.txt .
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt
COPY src/app/ ./app/
COPY src/run.py .
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# TFTP root: entrypoint writes boot.ipxe here when TFTP is enabled.
# Three binaries are served so the router can send the correct one per architecture
# and the per-MAC iPXE script can chain to the UKI for the install flow:
#   undionly.kpxe - legacy BIOS clients
#   ipxe.efi      - UEFI clients (chains to http://pxe-pilot-http/chain via embed.ipxe)
#   uki.efi       - Unified Kernel Image chained to by the per-MAC reinstall script
RUN mkdir -p /tftpboot
COPY --from=ipxe /ipxe/src/bin/undionly.kpxe /tftpboot/undionly.kpxe
COPY --from=ipxe /ipxe/src/bin-x86_64-efi/ipxe.efi /tftpboot/ipxe.efi
COPY --from=uki  /uki/uki.efi /tftpboot/uki.efi

# Defaults; overridable via -e or compose. DATABASE_PATH points into the declared volume so
# the DB survives container recreation. PORT is the gunicorn bind port. TIMEZONE controls the
# offset embedded in serialised timestamps (storage stays UTC); override to e.g. Asia/Tokyo.
ENV PORT=8000
ENV DATABASE_PATH=/data/pxe.db
ENV TIMEZONE=UTC

EXPOSE 8000 69/udp

VOLUME /data

# Set by the release workflow when creating a new version.
LABEL version="3.0.0"

ENTRYPOINT ["/entrypoint.sh"]
