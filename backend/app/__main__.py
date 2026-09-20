from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.core.paths import default_data_dir, ensure_layout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("aetherqore")


def prepare_runtime(create_config: bool = False) -> Path:
    """Load production-local env from the data directory before importing settings."""
    backend_root = Path(__file__).resolve().parents[1]
    os.chdir(backend_root)
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    layout = ensure_layout(default_data_dir())
    env_path = layout["config"] / "app.env"
    if create_config and not env_path.exists():
        from app.serve import init_config

        init_config()
    if env_path.exists():
        os.environ["AETHERQORE_ENV_FILE"] = str(env_path)
        load_dotenv(env_path, override=True)
        logger.info("loaded config %s", env_path)
    elif os.environ.get("ENVIRONMENT") == "production":
        raise SystemExit(f"Missing {env_path}. Run: python -m app init-config")
    return layout["root"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app", description="AetherQore local production tools")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-config", help="Generate SECRET_KEY and app.env in the data directory")
    sub.add_parser("migrate", help="Run Alembic migrations")
    sub.add_parser("bootstrap", help="Create RBAC, settings, and the first admin if missing")
    sub.add_parser("serve", help="Migrate, bootstrap, then serve FastAPI on localhost")
    sub.add_parser("backup", help="Write a verified SQLite backup")
    restore = sub.add_parser("restore", help="Restore the live database from a backup file")
    restore.add_argument("path")
    verify = sub.add_parser("verify", help="Run SQLite integrity_check")
    verify.add_argument("path", nargs="?")
    args = parser.parse_args(argv)

    if args.cmd == "init-config":
        prepare_runtime(create_config=True)
        from app.serve import init_config

        path = init_config()
        print(f"Wrote {path}")
        print(f"First login file: {path.parent / 'FIRST_LOGIN.txt'}")
        return 0

    prepare_runtime(create_config=False)

    if args.cmd == "migrate":
        from app.serve import run_migrations

        run_migrations()
        return 0
    if args.cmd == "bootstrap":
        from app.serve import bootstrap

        created = bootstrap()
        print("ok" if not created else created)
        return 0
    if args.cmd == "serve":
        from app.serve import run_server

        run_server()
        return 0
    if args.cmd == "backup":
        from app.core.backup import rotating_backup, sqlite_file_from_url
        from app.core.config import get_settings

        settings = get_settings()
        source = sqlite_file_from_url(settings.resolved_database_url)
        if source is None:
            raise SystemExit("Backups are only implemented for a file-backed SQLite database")
        layout = ensure_layout(settings.resolved_data_dir)
        path = rotating_backup(source, layout["backups"], keep=settings.backup_keep)
        print(path)
        return 0
    if args.cmd == "restore":
        from app.core.backup import restore_sqlite, sqlite_file_from_url
        from app.core.config import get_settings

        settings = get_settings()
        dest = sqlite_file_from_url(settings.resolved_database_url)
        if dest is None:
            raise SystemExit("Restore is only implemented for a file-backed SQLite database")
        restore_sqlite(Path(args.path), dest)
        print(f"Restored {dest}")
        return 0
    if args.cmd == "verify":
        from app.core.backup import sqlite_file_from_url, verify_sqlite
        from app.core.config import get_settings

        settings = get_settings()
        path = Path(args.path) if args.path else sqlite_file_from_url(settings.resolved_database_url)
        if path is None:
            raise SystemExit("No SQLite file to verify")
        print(verify_sqlite(path))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
