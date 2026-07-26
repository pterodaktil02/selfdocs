# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$VenvDir = Join-Path $ProjectRoot ".venv-windows"
$PythonExe = Join-Path $VenvDir "Scripts/python.exe"
$DistDir = Join-Path $ProjectRoot "dist"
$BuildDir = Join-Path $ProjectRoot "build"
$OutputDir = Join-Path $DistDir "SelfDocs"

Set-Location $ProjectRoot

if (-not (Test-Path $PythonExe)) {
    py -3 -m venv $VenvDir
}

& $PythonExe -m pip install --upgrade pip wheel
& $PythonExe -m pip install -r requirements-windows.txt

Remove-Item $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue

& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    deploy/windows/selfdocs.spec

if (-not (Test-Path (Join-Path $OutputDir "SelfDocs.exe"))) {
    throw "SelfDocs.exe was not created"
}

New-Item `
    -ItemType Directory `
    -Path (Join-Path $OutputDir "data") `
    -Force | Out-Null

$ZipPath = Join-Path $DistDir "SelfDocs-windows-x64.zip"

Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue

Compress-Archive `
    -Path $OutputDir `
    -DestinationPath $ZipPath `
    -CompressionLevel Optimal

Write-Host ""
Write-Host "Build completed:"
Write-Host "  Application: $OutputDir"
Write-Host "  Archive:     $ZipPath"
