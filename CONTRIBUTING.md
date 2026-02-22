# Contributing

Contributions are welcome. This document covers setup and how to submit changes.

## Development setup

For running the app (not developing), use Docker; see README **Quick start (Docker)**.

1. Clone the repo and enter the project directory.
2. Create a venv and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r src/requirements-dev.txt
   ```
3. Copy `.env.example` to `.env` and set URLs/paths for your environment.
4. Run the app: `cd src && python run.py` (listens on `http://0.0.0.0:8000`).

## Testing

Tests use a temporary SQLite database; no existing DB or env is required for the suite.

Run the full suite:

```bash
PYTHONPATH=src pytest src/tests/ -v
```

Run with coverage (report in terminal):

```bash
PYTHONPATH=src pytest src/tests/ -v --cov=app --cov-report=term-missing
```

What’s covered: `/chain`, `/boot`, `/health`, `/nodes`, reinstall toggles (POST/DELETE), optional admin auth (`Authorization: Bearer`), and URL templating (`${mac}`, `${ip}`). Add or update tests in `src/tests/` for new or changed behaviour.

## Making changes

- Match existing style: Python 3.11+, type hints where helpful, current Flask/SQLAlchemy patterns.
- Add or update docstrings and file-level comments for new or changed code.
- Run `PYTHONPATH=src pytest src/tests/ -v` and add or update tests for new or changed behaviour.
- Manually try endpoints if needed: `/health`, `/chain`, `/boot?mac=aa:bb:cc:dd:ee:ff`, `/nodes` and reinstall endpoints.

## Submitting changes

1. Open an issue for larger changes if you want to discuss first.
2. Fork, branch, commit with clear messages.
3. Run the test suite before submitting: `PYTHONPATH=src pytest src/tests/ -v`.
4. Open a pull request; describe what changed and why.
5. Ensure the app runs with `cd src && python run.py`. If you add or change env vars, update [.env.example](.env.example) and [docker-compose.example.yml](docker-compose.example.yml) so both stay in sync (README’s Environment variables section reflects the compose file for end users).

## Architecture

How the API fits into PXE boot and how the code is structured.

**Role in PXE boot**

1. DHCP option 67 (filename) points to this API’s `/chain` URL (e.g. `http://pxe-pilot/chain`).
2. Client loads iPXE (ROM or TFTP), then fetches the chain script from `/chain`.
3. Chain script tells iPXE to load `/boot?mac=${mac}`; on failure, iPXE exits and the BIOS continues with the next boot device (e.g. local disk).
4. API serves `/boot?mac=...`: looks up MAC in the DB and returns either a reinstall iPXE script (kernel/initrd/autoinstall) or a local-disk script.
5. For reinstall, the client loads kernel and initrd from your HTTP server and boots with cloud-init autoinstall. Kernel, initrd, and autoinstall URLs all support `${mac}` and `${ip}` (replaced per boot with client MAC and IP, URL-encoded).

This API is the control plane: it decides reinstall vs local disk and serves iPXE scripts. It does not serve kernel, initrd, or autoinstall files; those come from your own image host.

**Code layout**

- **src/app/__init__.py** – Flask app factory: creates app, init_db(), registers routes.
- **src/app/config.py** – Reads settings from environment (PXE URLs, DB path). No hardcoded URLs.
- **src/app/db.py** – SQLite engine and session factory; init_db() creates tables; get_db() yields a request-scoped session.
- **src/app/models.py** – SQLAlchemy Node model (mac, reinstall, last_seen, created_at).
- **src/app/routes/** – HTTP handlers: **chain.py** (/chain), **boot.py** (/boot), **nodes.py** (/nodes, POST/DELETE .../reinstall), **health.py** (/health). **common.py** has MAC normalization, admin auth, and URL templating (${mac}, ${ip}) used by boot and nodes.
- **src/run.py** – Dev entrypoint; production uses gunicorn with app:app.
- **tftp/embed.ipxe** – Stage 1 (build time): embedded in undionly.kpxe. Tells the client to TFTP-load boot.ipxe from the same server; does not reference the HTTP app.
- **docker/entrypoint.sh** – Requires PXE_BASE_URL; when PXE_TFTP_ENABLED is set, generates boot.ipxe (stage 2) with the HTTP /chain URL and starts dnsmasq (TFTP).

**TFTP two-stage flow (optional)**
When the router only offers TFTP: client loads undionly.kpxe via TFTP (embed.ipxe inside says “TFTP get boot.ipxe”). We generate boot.ipxe at container start with “chain PXE_BASE_URL/chain”, so the client then hits the HTTP API. Two stages so the HTTP URL can come from .env at runtime, not build time.

Data flow: request → route → get_db() → query/update Node → return iPXE text or JSON. No background jobs; state is only in SQLite.

**Database**

Single table `nodes`: columns id, mac (unique), reinstall (boolean), last_seen, created_at. Tables created on first run via Base.metadata.create_all.

**Security**

No authentication on boot/chain. For trusted internal or homelab use only. See [SECURITY.md](SECURITY.md).

## Scope

PXE Pilot targets homelab and internal PXE control. PRs that keep the scope minimal (SQLite, plain iPXE, optional admin auth) are preferred; larger features may be better as separate projects or discussed in an issue first.
