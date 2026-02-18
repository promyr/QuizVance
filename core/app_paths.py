# -*- coding: utf-8 -*-
"""
Runtime paths for development and packaged app execution.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

APP_NAME = "Quiz Vance"
ANDROID_PACKAGE = "com.flet.quiz_vance_app"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _candidate_bases():
    custom = (os.getenv("QUIZVANCE_DATA_DIR") or "").strip()
    if custom:
        yield Path(custom)

    is_android = bool(os.getenv("ANDROID_DATA"))
    if is_android:
        # Prefer app-private writable paths to avoid permission issues.
        yield Path.cwd() / ".quizvance_runtime"

        flet_data = (os.getenv("FLET_APP_STORAGE_DATA") or "").strip()
        if flet_data:
            yield Path(flet_data) / APP_NAME

        yield Path("/data/user/0") / ANDROID_PACKAGE / "files" / APP_NAME
        yield Path("/data/data") / ANDROID_PACKAGE / "files" / APP_NAME
        yield Path("/sdcard/Android/data") / ANDROID_PACKAGE / "files" / APP_NAME
        yield Path(tempfile.gettempdir()) / APP_NAME
        return

    home = Path.home()
    yield home / ".local" / "share" / APP_NAME
    yield _project_root()
    yield Path.cwd()
    yield Path(tempfile.gettempdir()) / APP_NAME


def _pick_base(kind: str) -> Path:
    for base in _candidate_bases():
        try:
            target = base / kind
            target.mkdir(parents=True, exist_ok=True)
            return target
        except Exception:
            continue

    fallback = Path(tempfile.gettempdir()) / APP_NAME / kind
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    except Exception:
        return Path.cwd() / kind


def get_data_dir() -> Path:
    return _pick_base("data")


def get_logs_dir() -> Path:
    return _pick_base("logs")


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
