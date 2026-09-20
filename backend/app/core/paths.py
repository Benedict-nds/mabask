from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "AetherQore"


def default_data_dir() -> Path:
    override = os.environ.get("AETHERQORE_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "aetherqore"
    return Path.home() / ".local" / "share" / "aetherqore"


def sqlite_url(path: Path) -> str:
    return "sqlite:///" + path.resolve().as_posix()


def ensure_layout(root: Path | None = None) -> dict[str, Path]:
    root = (root or default_data_dir()).resolve()
    dirs = {
        "root": root,
        "data": root / "data",
        "backups": root / "backups",
        "logs": root / "logs",
        "config": root / "config",
        "uploads": root / "uploads",
        "run": root / "run",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs
