from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path


class ReleaseCorpusError(RuntimeError):
    pass


METADATA_RELATIVE_PATH = Path("release") / "public-assets-metadata.json"
BASELINE_LEGAL_RELATIVE_PATH = Path("public-assets") / "legal" / "legal.db"
BASELINE_RETRIEVAL_RELATIVE_PATH = Path("public-assets") / "legal" / "retrieval.db"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_metadata(asset_root: Path) -> dict:
    path = asset_root / METADATA_RELATIVE_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseCorpusError(f"Packaged corpus metadata is unavailable or invalid: {path}") from exc
    if payload.get("schema_version") != "2.0.0":
        raise ReleaseCorpusError("Unsupported packaged corpus metadata schema.")
    if payload.get("asset_profile") != "stage15.5-three-domain-baseline":
        raise ReleaseCorpusError("Packaged legal assets are not the Stage 15.5 baseline profile.")
    release = payload.get("corpus_release") or {}
    legal = payload.get("legal") or {}
    retrieval = payload.get("retrieval") or {}
    if not release.get("corpus_id") or not release.get("corpus_version") or not release.get("release_digest"):
        raise ReleaseCorpusError("Packaged corpus metadata is missing Corpus Release identity.")
    if not legal.get("sha256") or not retrieval.get("sha256"):
        raise ReleaseCorpusError("Packaged corpus metadata is missing asset hashes.")
    return payload


def verify_packaged_baseline(asset_root: Path) -> dict:
    root = asset_root.resolve()
    metadata = _load_metadata(root)
    legal_path = root / BASELINE_LEGAL_RELATIVE_PATH
    retrieval_path = root / BASELINE_RETRIEVAL_RELATIVE_PATH
    if not legal_path.is_file() or not retrieval_path.is_file():
        raise ReleaseCorpusError("Packaged baseline legal.db/retrieval.db is missing.")
    actual_legal = _sha256(legal_path)
    actual_retrieval = _sha256(retrieval_path)
    if actual_legal != metadata["legal"]["sha256"]:
        raise ReleaseCorpusError("Packaged baseline legal.db SHA-256 mismatch.")
    if actual_retrieval != metadata["retrieval"]["sha256"]:
        raise ReleaseCorpusError("Packaged baseline retrieval.db SHA-256 mismatch.")
    return metadata


def install_packaged_baseline(asset_root: Path, runtime_root: Path) -> dict[str, object]:
    """Install the immutable packaged baseline once without overwriting a runtime corpus.

    The complete legal directory is staged beside the final directory and renamed
    only after both SQLite files and their hashes have been verified. If a complete
    runtime corpus already exists, it is left untouched so Stage 15.3 updates are
    never regressed by a later application upgrade.
    """

    asset_root = asset_root.resolve()
    runtime_root = runtime_root.resolve()
    target_dir = runtime_root / "legal"
    target_legal = target_dir / "legal.db"
    target_retrieval = target_dir / "retrieval.db"

    legal_exists = target_legal.is_file()
    retrieval_exists = target_retrieval.is_file()
    if legal_exists and retrieval_exists:
        return {
            "state": "EXISTING_RUNTIME",
            "legal_db": str(target_legal),
            "retrieval_db": str(target_retrieval),
        }
    if target_dir.exists():
        raise ReleaseCorpusError(
            "Runtime legal corpus is incomplete; refusing to mix or overwrite corpus assets."
        )

    metadata = verify_packaged_baseline(asset_root)
    source_legal = asset_root / BASELINE_LEGAL_RELATIVE_PATH
    source_retrieval = asset_root / BASELINE_RETRIEVAL_RELATIVE_PATH

    runtime_root.mkdir(parents=True, exist_ok=True)
    staged = runtime_root / ".legal-baseline-install.tmp"
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir()
    try:
        staged_legal = staged / "legal.db"
        staged_retrieval = staged / "retrieval.db"
        shutil.copyfile(source_legal, staged_legal)
        shutil.copyfile(source_retrieval, staged_retrieval)
        if _sha256(staged_legal) != metadata["legal"]["sha256"]:
            raise ReleaseCorpusError("Staged baseline legal.db failed SHA-256 verification.")
        if _sha256(staged_retrieval) != metadata["retrieval"]["sha256"]:
            raise ReleaseCorpusError("Staged baseline retrieval.db failed SHA-256 verification.")
        installed_metadata = {
            "schema_version": "1.0.0",
            "installation_source": "PACKAGED_BASELINE",
            "corpus_release": metadata["corpus_release"],
            "legal_sha256": metadata["legal"]["sha256"],
            "retrieval_sha256": metadata["retrieval"]["sha256"],
        }
        (staged / "installed-corpus.json").write_text(
            json.dumps(installed_metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(staged, target_dir)
    except Exception:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)
        raise

    return {
        "state": "INSTALLED_BASELINE",
        "legal_db": str(target_legal),
        "retrieval_db": str(target_retrieval),
        "corpus_id": metadata["corpus_release"]["corpus_id"],
        "corpus_version": metadata["corpus_release"]["corpus_version"],
        "release_digest": metadata["corpus_release"]["release_digest"],
    }
