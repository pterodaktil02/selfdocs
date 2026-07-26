# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import sys
from pathlib import Path


bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
dll_dir = bundle_dir / "weasyprint-dlls"

os.environ["WEASYPRINT_DLL_DIRECTORIES"] = str(dll_dir)

if hasattr(os, "add_dll_directory") and dll_dir.is_dir():
    os.add_dll_directory(str(dll_dir))
