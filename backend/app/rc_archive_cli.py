from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import zipfile
from pathlib import Path

from .ocr_models import OcrModelIntegrityError, resolve_ocr_model_paths

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "release" / "rc-config.json"
DEFAULT_BUNDLE = REPO_ROOT / "release" / "dist" / "Law-Rag"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "release" / "rc"
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_ROOT_PRIVATE_DIR_NAMES = {"runtime", "uploads", "jobs", "logs", "data_private", "benchmark_private"}
_BANNED_OCR_CACHE_DIR_NAMES = {"model_cache", ".paddlex", ".paddleocr", "official_models"}
_APPROVED_OCR_MODEL_DIR_NAMES = {"pp-ocrv6_medium_det", "pp-ocrv6_medium_rec"}
_BANNED_FILE_NAMES = {
    ".env",
    "human-review.json",
    "pipeline.json",
    "pipeline-control.json",
    "job-architecture.json",
    "audit-plan.json",
    "issue-legal-context.json",
    "issue-primary-audit.json",
    "issue-secondary-review.json",
    "issue-review-report.json",
    "ai-audit.json",
    "secondary-review.json",
    "review-report.json",
    "source.pdf",
    "source.jpg",
    "source.jpeg",
    "source.png",
    "source.docx",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path.name}.")
    return payload


def _validate_rc_config(config: dict[str, object]) -> tuple[str, str, str]:
    rc_version = str(config.get("rc_version") or "")
    target = str(config.get("target") or "")
    basename = str(config.get("artifact_basename") or "")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+-rc[0-9]+", rc_version):
        raise ValueError("rc_version must look like 0.8.0-rc1.")
    if target != "windows-x64":
        raise ValueError("Portable RC target must remain windows-x64.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", basename):
        raise ValueError("artifact_basename contains unsafe characters.")
    return rc_version, target, basename


def _looks_like_ppocr_model_dir(name: str) -> bool:
    lower = name.lower()
    return re.fullmatch(r"pp-ocrv6.*_(det|rec)", lower) is not None


def _scan_bundle(bundle_dir: Path) -> None:
    if not (bundle_dir / "Law-Rag.exe").is_file():
        raise FileNotFoundError("Law-Rag.exe is missing from the RC source bundle.")

    for name in sorted(_ROOT_PRIVATE_DIR_NAMES):
        path = bundle_dir / name
        if path.exists():
            raise RuntimeError(f"RC source bundle contains banned private application directory: {name}")

    model_root = bundle_dir / "_internal" / "ocr-models"
    model_manifest = bundle_dir / "_internal" / "release" / "ocr-models-manifest.json"
    try:
        approved_paths = resolve_ocr_model_paths(model_root=model_root, manifest_path=model_manifest)
    except OcrModelIntegrityError as exc:
        raise RuntimeError(f"RC source bundle OCR model integrity failed: {exc}") from exc
    approved_dirs = {approved_paths.detection.resolve(), approved_paths.recognition.resolve()}

    for path in bundle_dir.rglob("*"):
        if path.is_dir():
            lower = path.name.lower()
            if lower in _BANNED_OCR_CACHE_DIR_NAMES:
                raise RuntimeError(f"RC source bundle contains banned OCR cache directory: {path.name}")
            if _looks_like_ppocr_model_dir(path.name) and path.resolve() not in approved_dirs:
                raise RuntimeError(f"RC source bundle contains unapproved OCR model directory: {path.name}")
            if path.resolve() in approved_dirs and lower not in _APPROVED_OCR_MODEL_DIR_NAMES:
                raise RuntimeError(f"RC source bundle OCR model directory name is not approved: {path.name}")
        elif path.is_file() and path.name.lower() in _BANNED_FILE_NAMES:
            raise RuntimeError(f"RC source bundle contains banned private/job file: {path.name}")


def _write_deterministic_zip(bundle_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    temp = zip_path.with_suffix(zip_path.suffix + ".tmp")
    temp.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for source in sorted((path for path in bundle_dir.rglob("*") if path.is_file()), key=lambda p: p.as_posix().lower()):
                relative = source.relative_to(bundle_dir).as_posix()
                info = zipfile.ZipInfo(filename=f"Law-Rag/{relative}", date_time=_FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                mode = 0o755 if source.suffix.lower() in {".exe", ".dll"} else 0o644
                info.external_attr = (stat.S_IFREG | mode) << 16
                info.flag_bits |= 0x800
                archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        temp.replace(zip_path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def build_rc_artifacts(
    *,
    bundle_dir: Path = DEFAULT_BUNDLE,
    config_path: Path = DEFAULT_CONFIG,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, object]:
    bundle_dir = bundle_dir.resolve()
    config = _load_json(config_path.resolve())
    rc_version, target, basename = _validate_rc_config(config)
    _scan_bundle(bundle_dir)

    release_metadata_path = bundle_dir / "_internal" / "release" / "release-metadata.json"
    public_assets_path = bundle_dir / "_internal" / "release" / "public-assets-metadata.json"
    dependency_inventory_path = bundle_dir / "_internal" / "release" / "dependency-inventory.json"
    ocr_models_manifest_path = bundle_dir / "_internal" / "release" / "ocr-models-manifest.json"
    python_notices_path = bundle_dir / "_internal" / "THIRD-PARTY-NOTICES" / "python-third-party-notices.json"
    frontend_notices_path = bundle_dir / "_internal" / "frontend-dist" / "third-party-frontend-licenses.json"
    for required in (
        release_metadata_path,
        public_assets_path,
        dependency_inventory_path,
        ocr_models_manifest_path,
        python_notices_path,
        frontend_notices_path,
    ):
        if not required.is_file():
            raise FileNotFoundError(f"Required RC metadata/notice file is missing: {required.name}")

    release_metadata = _load_json(release_metadata_path)
    public_assets = _load_json(public_assets_path)
    source_sha = str(release_metadata.get("source_commit_sha") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Bundled release metadata does not contain a valid source commit SHA.")

    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    zip_path = output_dir / f"{basename}.zip"
    _write_deterministic_zip(bundle_dir, zip_path)

    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "rc_version": rc_version,
        "application_version": release_metadata.get("application_version"),
        "source_commit_sha": source_sha,
        "target": target,
        "distribution_mode": config.get("distribution_mode"),
        "publication_state": "NOT_PUBLISHED",
        "artifact": {
            "filename": zip_path.name,
            "sha256": _sha256(zip_path),
            "size_bytes": zip_path.stat().st_size,
        },
        "toolchain": release_metadata.get("toolchain"),
        "release_metadata_sha256": _sha256(release_metadata_path),
        "dependency_inventory_sha256": _sha256(dependency_inventory_path),
        "ocr_models_manifest_sha256": _sha256(ocr_models_manifest_path),
        "python_notices_sha256": _sha256(python_notices_path),
        "frontend_notices_sha256": _sha256(frontend_notices_path),
        "public_assets": {
            "metadata_sha256": _sha256(public_assets_path),
            "legal_sha256": public_assets["legal"]["sha256"],
            "retrieval_sha256": public_assets["retrieval"]["sha256"],
            "legal_source_fingerprint": public_assets["retrieval"]["legal_source_fingerprint"],
        },
        "reproducibility": {
            "archive_order": "case-insensitive path sort",
            "archive_timestamp": "1980-01-01T00:00:00Z fixed per ZIP entry",
            "wall_clock_timestamp_embedded": False,
            "claim": "Deterministic archive from identical validated onedir bundle contents; no cross-toolchain PE byte-identity claim.",
        },
    }
    manifest_path = output_dir / "RC-MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sums_path = output_dir / "SHA256SUMS.txt"
    sums_path.write_text(
        f"{manifest['artifact']['sha256']}  {zip_path.name}\n{_sha256(manifest_path)}  {manifest_path.name}\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Law-Rag portable RC artifacts.")
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    manifest = build_rc_artifacts(bundle_dir=args.bundle_dir, config_path=args.config, output_dir=args.output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
