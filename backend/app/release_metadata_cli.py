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


def build_release_metadata(
    *,
    source_commit_sha: str,
    node_version: str,
    npm_version: str,
    output_path: Path = DEFAULT_OUTPUT,
    public_assets_metadata_path: Path = DEFAULT_PUBLIC_ASSETS_METADATA,
    dependency_inventory_path: Path = DEFAULT_DEPENDENCY_INVENTORY,
    python_lock_path: Path = DEFAULT_PYTHON_LOCK,
    frontend_lock_path: Path = DEFAULT_FRONTEND_LOCK,
) -> dict[str, object]:
    source_commit_sha = source_commit_sha.strip().lower()
    if len(source_commit_sha) != 40 or any(ch not in "0123456789abcdef" for ch in source_commit_sha):
        raise ValueError("source_commit_sha must be a full 40-character lowercase/uppercase Git SHA-1 hex value.")

    public_assets = json.loads(public_assets_metadata_path.read_text(encoding="utf-8"))
    metadata: dict[str, object] = {
        "schema_version": "1.0.0",
        "release_profile": "stage11d-windows-base-onedir",
        "application_version": APP_VERSION,
        "source_commit_sha": source_commit_sha,
        "target": "windows-x64",
        "toolchain": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "node": node_version,
            "npm": npm_version,
            "pyinstaller": importlib_metadata.version("pyinstaller"),
        },
        "frontend": {
            "package_lock_sha256": _sha256(frontend_lock_path),
            "versions": _frontend_versions(frontend_lock_path),
        },
        "python_release_lock_sha256": _sha256(python_lock_path),
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
            "No wall-clock timestamp is embedded. Metadata fingerprints source/toolchain/locks/public assets; "
            "Stage 11D does not claim byte-identical PE output across arbitrary host/toolchain changes."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate safe Stage 11D Windows release reproducibility metadata.")
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
