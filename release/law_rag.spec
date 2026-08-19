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
# executable. PaddleX also checks its ocr-core extra with
# importlib.metadata.version(...) before creating the OCR pipeline, so the
# distribution metadata for every ocr-core dependency must survive freezing
# even though the importable modules themselves are already collected.
ocr_metadata = [
    *collect_metadata("paddlepaddle"),
    *collect_metadata("paddleocr"),
    *collect_metadata("paddlex"),
    *collect_metadata("imagesize"),
    *collect_metadata("opencv-contrib-python"),
    *collect_metadata("pyclipper"),
    *collect_metadata("pypdfium2"),
    *collect_metadata("python-bidi"),
    *collect_metadata("shapely"),
]

datas = [
    (str(REPO_ROOT / "frontend" / "dist"), "frontend-dist"),
    (str(BUILD_ASSETS / "public-assets"), "public-assets"),
    (str(BUILD_ASSETS / "public-assets-metadata.json"), "release"),
    (str(BUILD_ASSETS / "release-metadata.json"), "release"),
    (str(BUILD_ASSETS / "THIRD-PARTY-NOTICES"), "THIRD-PARTY-NOTICES"),
    (str(BUILD_ASSETS / "ocr-models"), "ocr-models"),
    (str(REPO_ROOT / "release" / "ocr-models-manifest.json"), "release"),
    # Keep Law-Rag's fixed two-model PaddleX config outside PaddleX package
    # data. PaddleOcrProvider passes this path explicitly via paddlex_config,
    # so collect_all("paddlex") cannot overwrite it with PaddleX's default
    # OCR.yaml and no package-relative lookup is required at runtime.
    (
        str(REPO_ROOT / "release" / "paddlex" / "configs" / "pipelines" / "OCR.yaml"),
        "release/ocr-pipeline",
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
