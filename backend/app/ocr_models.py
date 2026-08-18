from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MODEL_MANIFEST_SCHEMA_VERSION = "1.0.0"
MODEL_ROOT_ENV = "LAW_RAG_OCR_MODEL_ROOT"
MODEL_MANIFEST_ENV = "LAW_RAG_OCR_MODEL_MANIFEST"
RELEASE_ASSET_ROOT_ENV = "LAW_RAG_RELEASE_ASSET_ROOT"


class OcrModelIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrModelPaths:
    detection: Path
    recognition: Path


@dataclass(frozen=True)
class OcrModelProbe:
    ready: bool
    state: str
    model_root: str | None
    manifest_path: str | None
    detection_model: str | None
    recognition_model: str | None
    detail: str
    error_type: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _asset_root() -> Path | None:
    configured = os.getenv(RELEASE_ASSET_ROOT_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root).resolve()
    return None


def default_model_root() -> Path | None:
    configured = os.getenv(MODEL_ROOT_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    asset_root = _asset_root()
    return (asset_root / "ocr-models").resolve() if asset_root else None


def default_manifest_path() -> Path:
    configured = os.getenv(MODEL_MANIFEST_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    asset_root = _asset_root()
    if asset_root:
        return (asset_root / "release" / "ocr-models-manifest.json").resolve()
    return (Path(__file__).resolve().parents[2] / "release" / "ocr-models-manifest.json").resolve()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OcrModelIntegrityError("Pinned OCR model manifest is missing.") from exc
    except Exception as exc:
        raise OcrModelIntegrityError(f"Pinned OCR model manifest is unreadable: {type(exc).__name__}.") from exc
    if payload.get("schema_version") != MODEL_MANIFEST_SCHEMA_VERSION:
        raise OcrModelIntegrityError("Pinned OCR model manifest schema version is unsupported.")
    if payload.get("distribution_policy") != "build-time-fetch-verified-package-runtime-offline":
        raise OcrModelIntegrityError("Pinned OCR model manifest has an unexpected distribution policy.")
    models = payload.get("models")
    if not isinstance(models, list) or len(models) != 2:
        raise OcrModelIntegrityError("Pinned OCR model manifest must contain exactly two models.")
    roles = [model.get("role") for model in models if isinstance(model, dict)]
    if sorted(roles) != ["text_detection", "text_recognition"]:
        raise OcrModelIntegrityError("Pinned OCR model manifest roles are invalid.")
    return payload


def _verify_model(model: dict[str, Any], model_root: Path) -> Path:
    model_name = model.get("model_name")
    packaged_dir = model.get("packaged_dir")
    required_files = model.get("required_files")
    hashes = model.get("file_sha256")
    if not isinstance(model_name, str) or not model_name:
        raise OcrModelIntegrityError("Pinned OCR model identity is invalid.")
    if not isinstance(packaged_dir, str) or not packaged_dir or Path(packaged_dir).name != packaged_dir:
        raise OcrModelIntegrityError(f"Pinned OCR model {model_name} has an unsafe packaged directory.")
    if not isinstance(required_files, list) or not required_files or not all(isinstance(item, str) for item in required_files):
        raise OcrModelIntegrityError(f"Pinned OCR model {model_name} has invalid required files.")
    if not isinstance(hashes, dict):
        raise OcrModelIntegrityError(f"Pinned OCR model {model_name} has invalid file hashes.")

    directory = (model_root / packaged_dir).resolve()
    if model_root != directory and model_root not in directory.parents:
        raise OcrModelIntegrityError(f"Pinned OCR model {model_name} resolved outside the model root.")
    if not directory.is_dir():
        raise OcrModelIntegrityError(f"Pinned OCR model directory is missing: {model_name}.")

    expected_names = set(required_files)
    actual_names = {
        str(path.relative_to(directory)).replace("\\", "/")
        for path in directory.rglob("*")
        if path.is_file()
    }
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if unexpected:
            detail.append("unexpected=" + ",".join(unexpected))
        raise OcrModelIntegrityError(f"Pinned OCR model {model_name} file set mismatch ({'; '.join(detail)}).")

    for relative in required_files:
        expected = hashes.get(relative)
        if not isinstance(expected, str) or len(expected) != 64:
            raise OcrModelIntegrityError(f"Pinned OCR model {model_name} hash is not locked for {relative}.")
        actual = _sha256_file(directory / relative)
        if actual != expected:
            raise OcrModelIntegrityError(f"Pinned OCR model {model_name} integrity check failed for {relative}.")
    return directory


def resolve_ocr_model_paths(*, model_root: Path | None = None, manifest_path: Path | None = None) -> OcrModelPaths:
    root = (model_root or default_model_root())
    manifest = (manifest_path or default_manifest_path()).resolve()
    if root is None:
        raise OcrModelIntegrityError(
            "Pinned OCR models are not configured. Packaged releases include them; source checkouts must set LAW_RAG_OCR_MODEL_ROOT."
        )
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise OcrModelIntegrityError("Pinned OCR model root is missing.")
    payload = _load_manifest(manifest)
    by_role = {model["role"]: model for model in payload["models"]}
    detection = _verify_model(by_role["text_detection"], root)
    recognition = _verify_model(by_role["text_recognition"], root)
    return OcrModelPaths(detection=detection, recognition=recognition)


def probe_ocr_models(*, model_root: Path | None = None, manifest_path: Path | None = None) -> OcrModelProbe:
    root = model_root or default_model_root()
    manifest = manifest_path or default_manifest_path()
    try:
        paths = resolve_ocr_model_paths(model_root=root, manifest_path=manifest)
    except Exception as exc:
        return OcrModelProbe(
            ready=False,
            state="MISSING" if isinstance(exc, OcrModelIntegrityError) and (root is None or not Path(root).exists()) else "CORRUPT",
            model_root=str(Path(root).resolve()) if root is not None else None,
            manifest_path=str(Path(manifest).resolve()),
            detection_model=None,
            recognition_model=None,
            detail=str(exc),
            error_type=type(exc).__name__,
        )
    return OcrModelProbe(
        ready=True,
        state="READY",
        model_root=str(Path(root).resolve()) if root is not None else None,
        manifest_path=str(Path(manifest).resolve()),
        detection_model=paths.detection.name,
        recognition_model=paths.recognition.name,
        detail="Pinned local PP-OCR model files are present and match the checked manifest SHA-256 values.",
    )
