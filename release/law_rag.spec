# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata

REPO_ROOT = Path(SPECPATH).resolve().parent
BACKEND = REPO_ROOT / "backend"
BUILD_ASSETS = REPO_ROOT / "release" / ".build"


def collect_package(name: str):
    try:
        return collect_all(name)
    except Exception:
        return ([], [], [])


def collect_metadata(name: str):
    try:
        return copy_metadata(name)
    except Exception:
        return []


pypdfium_datas, pypdfium_binaries, pypdfium_hidden = collect_package("pypdfium2")
raw_datas, raw_binaries, raw_hidden = collect_package("pypdfium2_raw")
paddle_datas, paddle_binaries, paddle_hidden = collect_package("paddle")
paddleocr_datas, paddleocr_binaries, paddleocr_hidden = collect_package("paddleocr")
paddlex_datas, paddlex_binaries, paddlex_hidden = collect_package("paddlex")

# Runtime versions are validated through importlib.metadata inside the frozen
# executable. Keep distribution metadata alongside collected Python/native code.
ocr_metadata = [
    *collect_metadata("paddlepaddle"),
    *collect_metadata("paddleocr"),
    *collect_metadata("paddlex"),
]

datas = [
    (str(REPO_ROOT / "frontend" / "dist"), "frontend-dist"),
    (str(BUILD_ASSETS / "public-assets"), "public-assets"),
    (str(BUILD_ASSETS / "public-assets-metadata.json"), "release"),
    (str(BUILD_ASSETS / "release-metadata.json"), "release"),
    (str(BUILD_ASSETS / "THIRD-PARTY-NOTICES"), "THIRD-PARTY-NOTICES"),
    (str(BUILD_ASSETS / "ocr-models"), "ocr-models"),
    (str(REPO_ROOT / "release" / "ocr-models-manifest.json"), "release"),
    # PaddleX resolves its default OCR pipeline relative to paddlex.__file__.
    # PyInstaller may not preserve that package data path automatically, so
    # place Law-Rag's fixed two-model config at the exact path PaddleX 3.7
    # expects. This avoids any runtime model/config download fallback.
    (
        str(REPO_ROOT / "release" / "paddlex" / "configs" / "pipelines" / "OCR.yaml"),
        "paddlex/configs/pipelines",
    ),
    (str(REPO_ROOT / "release" / "dependency-inventory.json"), "release"),
    (str(REPO_ROOT / "docs" / "WINDOWS_PACKAGING.md"), "docs"),
    (str(REPO_ROOT / ".env.example"), "."),
    *pypdfium_datas,
    *raw_datas,
    *paddle_datas,
    *paddleocr_datas,
    *paddlex_datas,
    *ocr_metadata,
]

binaries = [
    *pypdfium_binaries,
    *raw_binaries,
    *paddle_binaries,
    *paddleocr_binaries,
    *paddlex_binaries,
]
hiddenimports = [
    *pypdfium_hidden,
    *raw_hidden,
    *paddle_hidden,
    *paddleocr_hidden,
    *paddlex_hidden,
]

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
    hide_console="hide-early",
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
