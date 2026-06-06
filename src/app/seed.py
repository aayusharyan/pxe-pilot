"""
Database seeding from a YAML file.

Reads a user-supplied YAML at SEED_FILE on startup and inserts any listed
node that does not already exist in the database. The DB always wins: rows
that are already present are never touched. This file is separate from db.py
to avoid a circular import (boot.py imports db.py; seed.py can safely import
both without creating a cycle).

YAML format (example /config/seed.yml):

    nodes:
      - mac: "3c:52:82:57:ac:ed"
        reinstall: false
        local_boot_script: "sanboot --no-describe --drive 0x80"
      - mac: "40:b0:34:43:b5:e7"
        reinstall: false
        # local_boot_script omitted: defaults to null → "exit" at boot time
"""

import logging
import os

import yaml

from app.config import SEED_FILE
from app.db import SessionLocal
from app.models import AppConfig, Node
from app.routes.boot import validate_local_boot_script
from app.routes.common import normalize_mac

logger = logging.getLogger(__name__)


def seed_db() -> None:
    """
    Populate the database with the initial node state from SEED_FILE.

    Only inserts nodes whose MAC is not already in the database. Silently
    skips when SEED_FILE is unset, missing, or empty. Logs and skips
    individual entries with invalid MACs or disallowed boot scripts so a
    bad entry never blocks the rest of the seed from applying.
    """
    if not SEED_FILE:
        return

    if not os.path.exists(SEED_FILE):
        logger.info("seed: SEED_FILE=%s not found; skipping seed", SEED_FILE)
        return

    try:
        with open(SEED_FILE, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        logger.warning("seed: failed to parse %s: %s", SEED_FILE, exc)
        return

    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        logger.warning("seed: %s must contain a top-level 'nodes' list; skipping", SEED_FILE)
        return

    db = SessionLocal()
    try:
        if db.query(AppConfig).filter(AppConfig.key == "is_seed_executed").first() is not None:
            logger.info("seed: already applied on a previous run; skipping")
            return

        inserted = 0
        skipped_existing = 0
        skipped_invalid = 0

        for entry in data["nodes"]:
            raw_mac = entry.get("mac", "") if isinstance(entry, dict) else ""
            mac = normalize_mac(str(raw_mac))

            if not mac:
                logger.warning("seed: invalid mac %r; skipping entry", raw_mac)
                skipped_invalid += 1
                continue

            # DB wins: never overwrite an existing row.
            if db.query(Node).filter(Node.mac == mac).first() is not None:
                skipped_existing += 1
                continue

            reinstall = bool(entry.get("reinstall", False))

            script_raw = entry.get("local_boot_script") or None
            script: str | None = None
            if script_raw is not None:
                if validate_local_boot_script(str(script_raw)):
                    script = str(script_raw)
                else:
                    logger.warning(
                        "seed: invalid local_boot_script %r for %s; falling back to default (exit)",
                        script_raw,
                        mac,
                    )
                    skipped_invalid += 1

            db.add(Node(mac=mac, reinstall=reinstall, local_boot_script=script))
            inserted += 1

        db.add(AppConfig(key="is_seed_executed", value="1"))
        db.commit()
        logger.info(
            "seed: done - inserted %d, skipped %d existing, %d invalid entries",
            inserted,
            skipped_existing,
            skipped_invalid,
        )
    except Exception as exc:
        db.rollback()
        logger.warning("seed: failed to apply seed: %s", exc)
    finally:
        db.close()
