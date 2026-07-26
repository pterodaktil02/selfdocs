# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


project_root = Path(SPEC).resolve().parents[2]

datas = [
    (str(project_root / "app" / "templates"), "app/templates"),
    (str(project_root / "static"), "static"),
]

hiddenimports = []
binaries = []

for package in ("weasyprint", "pydyf", "tinycss2", "cssselect2", "fontTools"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

hiddenimports += collect_submodules("app")

analysis = Analysis(
    [str(project_root / "windows_launcher.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[
        str(project_root / "deploy" / "windows" / "runtime-weasyprint.py"),
    ],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SelfDocs",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="SelfDocs",
)
