# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

REPO_ROOT = Path(SPECPATH).resolve().parent
BACKEND = REPO_ROOT / "backend"
BUILD_ASSETS = REPO_ROOT / "release" / ".build"


def collect_package(name: str):
    try:
        return collect_all(name)
    except Exception:
        return ([], [], [])


pypdfium_datas, pypdfium_binaries, pypdfium_hidden = collect_package("pypdfium2")
raw_datas, raw_binaries, raw_hidden = collect_package("pypdfium2_raw")

datas = [
    (str(REPO_ROOT / "frontend" / "dist"), "frontend-dist"),
    (str(BUILD_ASSETS / "public-assets"), "public-assets"),
    (str(BUILD_ASSETS / "public-assets-metadata.json"), "release"),
    (str(REPO_ROOT / "release" / "dependency-inventory.json"), "release"),
    (str(REPO_ROOT / "docs" / "WINDOWS_PACKAGING.md"), "docs"),
    (str(REPO_ROOT / ".env.example"), "."),
    *pypdfium_datas,
    *raw_datas,
]

binaries = [*pypdfium_binaries, *raw_binaries]
hiddenimports = [*pypdfium_hidden, *raw_hidden]

a = Analysis(
    [str(BACKEND / "release_entry.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "paddle",
        "paddleocr",
        "sentence_transformers",
        "torch",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Law-Rag",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Law-Rag",
)
