# Multi-stage build: stage 1 produces undionly.kpxe (iPXE with embedded script); stage 2 is the Flask app plus optional TFTP.
# Build context is the repo root. Use: docker build -f docker/Dockerfile .

# Stage 1: build iPXE and bake embed.ipxe into undionly.kpxe. That script tells the client to TFTP-load boot.ipxe; we generate boot.ipxe at runtime in entrypoint.sh.
FROM debian:bookworm-slim AS ipxe
# ca-certificates for git TLS; liblzma-dev for iPXE host build (util/zbin).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential git binutils-dev liblzma-dev \
    gcc-x86-64-linux-gnu \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://git.ipxe.org/ipxe.git /ipxe
COPY tftp/embed.ipxe /ipxe/src/embed.ipxe
WORKDIR /ipxe/src
# Build legacy BIOS binary and UEFI binary in one pass so both are available in /tftpboot.
RUN make bin/undionly.kpxe EMBED=embed.ipxe && \
    make bin-x86_64-efi/ipxe.efi EMBED=embed.ipxe

# Stage 2: runtime image. Python app plus dnsmasq for optional TFTP. App and TFTP share the same container.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends dnsmasq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/requirements.txt .
RUN pip install --no-cache-dir --timeout 120 -r requirements.txt
COPY src/app/ ./app/
COPY src/run.py .
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# TFTP root: entrypoint writes boot.ipxe here when TFTP is enabled.
# Both legacy BIOS (undionly.kpxe) and UEFI (ipxe.efi) binaries are served so
# the router can send the correct filename based on client architecture.
RUN mkdir -p /tftpboot
COPY --from=ipxe /ipxe/src/bin/undionly.kpxe /tftpboot/undionly.kpxe
COPY --from=ipxe /ipxe/src/bin-x86_64-efi/ipxe.efi /tftpboot/ipxe.efi

# Defaults; overridable via -e or compose. App default for DATABASE_PATH is pxe.db (see config.py).
ENV PORT=8000

EXPOSE 8000 69/udp

VOLUME /data

# Set by the release workflow when creating a new version.
LABEL version="1.4.0"

ENTRYPOINT ["/entrypoint.sh"]
