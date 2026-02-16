# -*- coding: utf-8 -*-
"""
Paths de runtime para suportar execucao em desenvolvimento e em app empacotado.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "QuizVance"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _user_data_root() -> Path:
    if sys.platform == "win32":
        base = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def get_data_dir() -> Path:
    custom = (os.getenv("QUIZVANCE_DATA_DIR") or "").strip()
    if custom:
        return Path(custom)

    source_data = _project_root() / "data"
    if source_data.exists() and os.access(source_data, os.W_OK):
        return source_data

    return _user_data_root() / "data"


def get_logs_dir() -> Path:
    custom = (os.getenv("QUIZVANCE_LOG_DIR") or "").strip()
    if custom:
        return Path(custom)

    source_logs = _project_root() / "logs"
    if source_logs.exists() and os.access(source_logs, os.W_OK):
        return source_logs

    return _user_data_root() / "logs"


def ensure_runtime_dirs() -> None:
    data_dir = get_data_dir()
    logs_dir = get_logs_dir()
    for path in [
        data_dir,
        data_dir / "cache",
        data_dir / "pdfs",
        data_dir / "library",
        logs_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def get_db_path() -> Path:
    return get_data_dir() / "elite_data_master.db"


def get_library_dir() -> Path:
    return get_data_dir() / "library"


def get_log_file_path() -> Path:
    return get_logs_dir() / "app_errors.log"

