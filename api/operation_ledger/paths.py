"""Machine-local paths for private operation-ledger records."""

import os
from pathlib import Path


def private_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), "AppData", "Local")
    return Path(base) / "CanvasExpert" / "workbench" / "private"


def receipts_file() -> Path:
    return private_root() / "receipts.v1.json"


def operations_file() -> Path:
    return private_root() / "operations.v1.json"


def claims_file() -> Path:
    return private_root() / "claims.v1.json"


def quarantine_dir() -> Path:
    return private_root() / "quarantine"


def curve_events_file() -> Path:
    return private_root() / "curve_events.v1.json"


def curve_migration_backups_dir() -> Path:
    return private_root() / "migration-backups"
