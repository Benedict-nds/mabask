from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.backup import maybe_daily_backup, sqlite_file_from_url
from app.core.paths import ensure_layout, sqlite_url

logger = logging.getLogger("aetherqore")

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler = logging.FileHandler(log_dir / "aetherqore.log", encoding="utf-8")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "").endswith("aetherqore.log") for h in root.handlers):
        root.addHandler(handler)
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    root.setLevel(logging.INFO)


def write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = []
    for key, value in values.items():
        if any(ch in value for ch in ' \t#="\''):
            encoded = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        else:
            encoded = value
        lines.append(f"{key}={encoded}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def init_config() -> Path:
    settings_preview_dir = os.environ.get("AETHERQORE_HOME", "").strip()
    layout = ensure_layout()
    env_path = layout["config"] / "app.env"
    db_url = sqlite_url(layout["data"] / "aetherqore.db")
    if env_path.exists():
        logger.info("config already exists at %s", env_path)
        return env_path

    secret = secrets.token_urlsafe(48)
    admin_password = os.environ.get("AETHERQORE_ADMIN_PASSWORD", "").strip() or secrets.token_urlsafe(12)
    os.environ["AETHERQORE_ADMIN_PASSWORD"] = admin_password
    values = {
        "APP_NAME": "AetherQore POS",
        "ENVIRONMENT": "production",
        "DEBUG": "false",
        "SECRET_KEY": secret,
        "ACCESS_TOKEN_EXPIRE_MINUTES": "720",
        "REFRESH_TOKEN_EXPIRE_DAYS": "14",
        "DATABASE_URL": db_url,
        "DATA_DIR": str(layout["root"]),
        "HOST": "127.0.0.1",
        "PORT": "8000",
        "FRONTEND_URL": "http://127.0.0.1:3000",
        "CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
        "BACKUP_KEEP": "14",
        "AI_PROVIDER": "",
        "AI_API_KEY": "",
        "AI_MODEL": "gpt-4o-mini",
        "AETHERQORE_PHARMACY_NAME": os.environ.get("AETHERQORE_PHARMACY_NAME", "Pharmacy"),
        "AETHERQORE_ADMIN_EMAIL": os.environ.get("AETHERQORE_ADMIN_EMAIL", "admin@pharmacy.local"),
        "AETHERQORE_ADMIN_NAME": os.environ.get("AETHERQORE_ADMIN_NAME", "Pharmacy Admin"),
        "AETHERQORE_ADMIN_PASSWORD": admin_password,
    }
    write_env_file(env_path, values)
    login_note = layout["config"] / "FIRST_LOGIN.txt"
    login_note.write_text(
        "AetherQore first login (change this password after signing in)\n"
        f"Email: {values['AETHERQORE_ADMIN_EMAIL']}\n"
        f"Password: {admin_password}\n"
        f"Data directory: {layout['root']}\n",
        encoding="utf-8",
    )
    logger.info("wrote %s (home=%s)", env_path, settings_preview_dir or layout["root"])
    return env_path


def run_migrations() -> None:
    ini = BACKEND_ROOT / "alembic.ini"
    if not ini.is_file():
        raise RuntimeError(f"alembic.ini not found at {ini}")
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(cfg, "head")
    logger.info("database migrations are up to date")


def bootstrap() -> dict[str, str]:
    from app.bootstrap import bootstrap_pharmacy
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        created = bootstrap_pharmacy(db)
        if created:
            logger.info("bootstrap created: %s", ", ".join(created))
        else:
            logger.info("bootstrap: existing pharmacy data left unchanged")
        return created
    except Exception:
        db.rollback()
        logger.exception("bootstrap failed")
        raise
    finally:
        db.close()


def run_daily_backup() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    path = sqlite_file_from_url(settings.resolved_database_url)
    if path is None:
        return
    layout = ensure_layout(settings.resolved_data_dir)
    maybe_daily_backup(path, layout["backups"], keep=settings.backup_keep)


def run_server() -> None:
    from app.core.config import WEAK_SECRETS, get_settings

    settings = get_settings()
    if settings.environment == "production" and settings.secret_key in WEAK_SECRETS:
        raise SystemExit("SECRET_KEY must be a generated value in production")
    layout = ensure_layout(settings.resolved_data_dir)
    configure_logging(layout["logs"])
    logger.info("starting %s (%s) data_dir=%s", settings.app_name, settings.environment, layout["root"])
    try:
        run_migrations()
        bootstrap()
        run_daily_backup()
    except Exception:
        logger.exception("startup failed before the API was bound")
        raise
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="debug" if settings.debug else "info",
        access_log=settings.debug,
    )
