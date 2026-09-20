from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine.url import make_url

logger = logging.getLogger("aetherqore.backup")

BACKUP_PREFIX = "aetherqore-"
BACKUP_SUFFIX = ".db"


class BackupError(RuntimeError):
    pass


def sqlite_file_from_url(url: str) -> Path | None:
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite"):
        return None
    database = parsed.database
    if not database or database == ":memory:":
        return None
    return Path(database)


def verify_sqlite(path: Path) -> str:
    if not path.is_file():
        raise BackupError(f"Database file not found: {path}")
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        status = result[0] if result else "failed"
        if status != "ok":
            raise BackupError(f"Integrity check failed for {path}: {status}")
        return status
    finally:
        conn.close()


def backup_sqlite(source: Path, destination: Path) -> Path:
    """Copy a live SQLite database using the backup API (safe with WAL)."""
    source = source.resolve()
    destination = destination.resolve()
    if not source.is_file():
        raise BackupError(f"Live database not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
            dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            dst.close()
    finally:
        src.close()
    verify_sqlite(tmp)
    tmp.replace(destination)
    logger.info("wrote backup %s", destination)
    return destination


def restore_sqlite(backup: Path, destination: Path) -> Path:
    backup = backup.resolve()
    destination = destination.resolve()
    verify_sqlite(backup)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".restore-tmp")
    if tmp.exists():
        tmp.unlink()
    src = sqlite3.connect(str(backup))
    try:
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    verify_sqlite(tmp)
    # Remove leftover WAL/SHM from the previous live database.
    for extra in (destination.with_name(destination.name + "-wal"), destination.with_name(destination.name + "-shm")):
        if extra.exists():
            extra.unlink()
    tmp.replace(destination)
    logger.info("restored %s from %s", destination, backup)
    return destination


def rotating_backup(source: Path, backup_dir: Path, keep: int = 14) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"{BACKUP_PREFIX}{stamp}{BACKUP_SUFFIX}"
    backup_sqlite(source, destination)
    prune_backups(backup_dir, keep=keep)
    return destination


def prune_backups(backup_dir: Path, keep: int = 14) -> None:
    files = sorted(backup_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in files[keep:]:
        stale.unlink(missing_ok=True)
        logger.info("pruned backup %s", stale)


def latest_backup(backup_dir: Path) -> Path | None:
    files = sorted(backup_dir.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def maybe_daily_backup(source: Path, backup_dir: Path, keep: int = 14) -> Path | None:
    if not source.is_file():
        return None
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    existing = list(backup_dir.glob(f"{BACKUP_PREFIX}{today}-*{BACKUP_SUFFIX}"))
    if existing:
        return existing[-1]
    return rotating_backup(source, backup_dir, keep=keep)
