from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as importlib_metadata
import json
import platform
from pathlib import Path

from .main import APP_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "release" / ".build" / "release-metadata.json"
DEFAULT_PUBLIC_ASSETS_METADATA = REPO_ROOT / "release" / ".build" / "public-assets-metadata.json"
DEFAULT_DEPENDENCY_INVENTORY = REPO_ROOT / "release" / "dependency-inventory.json"
DEFAULT_PYTHON_LOCK = REPO_ROOT / "backend" / "requirements-release-lock-windows.txt"
DEFAULT_OCR_PYTHON_LOCK = REPO_ROOT / "backend" / "requirements-release-ocr-lock-windows.txt"
DEFAULT_OCR_MODEL_MANIFEST = REPO_ROOT / "release" / "ocr-models-manifest.json"
DEFAULT_FRONTEND_LOCK = REPO_ROOT / "frontend" / "package-lock.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frontend_versions(lock_path: Path) -> dict[str, str | None]:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = payload.get("packages") or {}

    def version(name: str) -> str | None:
        entry = packages.get(f"node_modules/{name}") or {}
        value = entry.get("version")
        return str(value) if value is not None else None

    return {
        "react": version("react"),
        "react_dom": version("react-dom"),
        "typescript": version("typescript"),
        "vite": version("vite"),
    }


def _ocr_model_identity(manifest_path: Path) -> dict[str, object]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    models = payload.get("models") or []
    return {
        "manifest_sha256": _sha256(manifest_path),
        "artifact_set": payload.get("artifact_set"),
        "distribution_policy": payload.get("distribution_policy"),
        "models": [
            {
                "role": model.get("role"),
                "model_name": model.get("model_name"),
                "archive_sha256": model.get("archive_sha256"),
            }
            for model in models
            if isinstance(model, dict)
        ],
    }


def build_release_metadata(
    *,
    source_commit_sha: str,
    node_version: str,
    npm_version: str,
    output_path: Path = DEFAULT_OUTPUT,
    public_assets_metadata_path: Path = DEFAULT_PUBLIC_ASSETS_METADATA,
    dependency_inventory_path: Path = DEFAULT_DEPENDENCY_INVENTORY,
    python_lock_path: Path = DEFAULT_PYTHON_LOCK,
    ocr_python_lock_path: Path = DEFAULT_OCR_PYTHON_LOCK,
    ocr_model_manifest_path: Path = DEFAULT_OCR_MODEL_MANIFEST,
    frontend_lock_path: Path = DEFAULT_FRONTEND_LOCK,
    pyinstaller_version: str | None = None,
) -> dict[str, object]:
    source_commit_sha = source_commit_sha.strip().lower()
    if len(source_commit_sha) != 40 or any(ch not in "0123456789abcdef" for ch in source_commit_sha):
        raise ValueError("source_commit_sha must be a full 40-character Git SHA-1 hex value.")

    public_assets = json.loads(public_assets_metadata_path.read_text(encoding="utf-8"))
    resolved_pyinstaller = pyinstaller_version or importlib_metadata.version("pyinstaller")
    base_lock_sha = _sha256(python_lock_path)
    ocr_lock_sha = _sha256(ocr_python_lock_path)
    metadata: dict[str, object] = {
        "schema_version": "1.2.0",
        "release_profile": "stage14-5-windows-offline-ocr-onedir",
        "application_version": APP_VERSION,
        "source_commit_sha": source_commit_sha,
        "target": "windows-x64",
        "toolchain": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "node": node_version,
            "npm": npm_version,
            "pyinstaller": resolved_pyinstaller,
        },
        "frontend": {
            "package_lock_sha256": _sha256(frontend_lock_path),
            "versions": _frontend_versions(frontend_lock_path),
        },
        "python_release_lock_sha256": base_lock_sha,
        "python_release_locks": {
            "base_sha256": base_lock_sha,
            "ocr_sha256": ocr_lock_sha,
        },
        "ocr_models": _ocr_model_identity(ocr_model_manifest_path),
        "dependency_inventory_sha256": _sha256(dependency_inventory_path),
        "public_assets": {
            "metadata_sha256": _sha256(public_assets_metadata_path),
            "legal_sha256": public_assets["legal"]["sha256"],
            "retrieval_sha256": public_assets["retrieval"]["sha256"],
            "legal_source_fingerprint": public_assets["retrieval"]["legal_source_fingerprint"],
            "retrieval_schema_version": public_assets["retrieval"]["schema_version"],
        },
        "wall_clock_build_timestamp": None,
        "reproducible_content_policy": (
            "No wall-clock timestamp is embedded. Metadata fingerprints source/toolchain/base+OCR locks/"
            "the exact offline OCR model manifest/public assets; the release does not claim byte-identical PE output "
            "across arbitrary host/toolchain changes."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate safe Windows release reproducibility metadata.")
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--node-version", required=True)
    parser.add_argument("--npm-version", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    metadata = build_release_metadata(
        source_commit_sha=args.source_sha,
        node_version=args.node_version,
        npm_version=args.npm_version,
        output_path=args.output,
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
