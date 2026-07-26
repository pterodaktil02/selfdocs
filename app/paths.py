# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "SelfDocs"


def resource_root() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parents[1]


def data_root() -> Path:
    explicit = os.environ.get("SELFDOCS_DATA_DIR")
    if explicit:
        path = Path(explicit).expanduser().resolve()
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / APP_NAME
    else:
        path = resource_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path

RESOURCE_DIR = resource_root()
DATA_DIR = data_root()
TEMPLATE_DIR = RESOURCE_DIR / "app" / "templates"
STATIC_DIR = RESOURCE_DIR / "static"
PRIVATE_DIR = DATA_DIR / "private"
PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "selfdocs.sqlite3"
SIGNATURE_PATH = PRIVATE_DIR / "signature.png"

# Однократная миграция подписи из старой серверной раскладки.
legacy_signature = RESOURCE_DIR / "private" / "signature.png"
if not SIGNATURE_PATH.exists() and legacy_signature.exists():
    shutil.copyfile(legacy_signature, SIGNATURE_PATH)
    SIGNATURE_PATH.chmod(0o600)
