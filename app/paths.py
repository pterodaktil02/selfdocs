# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "SelfDocs"


def is_frozen() -> bool:
    """Return True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """
    Return the directory containing bundled application resources.

    In a PyInstaller build this is the temporary or bundled resource
    directory exposed through sys._MEIPASS. During normal execution it is
    the project root.
    """
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled).resolve()

    return Path(__file__).resolve().parents[1]


def executable_root() -> Path:
    """
    Return the directory containing the executable or project checkout.

    This is separate from resource_root because PyInstaller resources may be
    stored under _internal while portable user data must stay beside the exe.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[1]


def data_root() -> Path:
    """
    Return the writable SelfDocs data directory.

    Priority:
    1. SELFDOCS_DATA_DIR environment variable.
    2. Portable data directory beside a frozen Windows executable.
    3. Project-local data directory for normal Linux/development execution.
    """
    explicit = os.environ.get("SELFDOCS_DATA_DIR")

    if explicit:
        path = Path(explicit).expanduser().resolve()
    elif sys.platform == "win32" and is_frozen():
        path = executable_root() / "data"
    else:
        path = executable_root() / "data"

    path.mkdir(parents=True, exist_ok=True)
    return path


RESOURCE_DIR = resource_root()
EXECUTABLE_DIR = executable_root()
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

    try:
        SIGNATURE_PATH.chmod(0o600)
    except OSError:
        # Windows не поддерживает POSIX-права в полном объеме.
        pass
