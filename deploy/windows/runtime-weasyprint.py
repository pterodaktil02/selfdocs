# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import sys
from pathlib import Path


_DLL_DIRECTORY_HANDLES: list[object] = []

bundle_dir = Path(
    getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)
)
dll_dir = bundle_dir / "weasyprint-dlls"

if dll_dir.is_dir():
    dll_path = str(dll_dir)

    os.environ["WEASYPRINT_DLL_DIRECTORIES"] = dll_path
    os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")

    if hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.append(
            os.add_dll_directory(dll_path)
        )
