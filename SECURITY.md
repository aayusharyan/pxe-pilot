# Security

PXE Pilot has no authentication on boot or chain endpoints. It is intended for trusted internal or homelab networks only.

- Do not expose the service directly to the internet.
- To reach it across networks, use a reverse proxy or VPN and restrict access (IP or auth) at that layer.
- The database holds MAC addresses and reinstall flags; treat the SQLite file and backups accordingly.
- Optional: set `ADMIN_API_KEY` so that admin endpoints (`/nodes`, `.../reinstall`) require `Authorization: Bearer <key>`. If unset, those routes will be open.

To report a security concern, open a GitHub issue or contact the maintainers via the repository.
