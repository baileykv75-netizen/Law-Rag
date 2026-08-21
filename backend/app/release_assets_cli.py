from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .legal.corpus_release import load_corpus_release, rebuild_legal_store_from_release
from .legal.retrieval import build_retrieval_index
from .legal.store import get_summary

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_ROOT = REPO_ROOT / "legal_data"
DEFAULT_CORPUS_RELEASE = (
    DEFAULT_CORPUS_ROOT / "releases" / "three-domain-core" / "1.0.0" / "release.json"
)
DEFAULT_SOURCE_REGISTRY = DEFAULT_CORPUS_ROOT / "source_registry.json"
DEFAULT_OUTPUT = REPO_ROOT / "release" / ".build"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.name


def build_public_release_assets(
    output_dir: Path,
    release_path: Path = DEFAULT_CORPUS_RELEASE,
    *,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    source_registry_path: Path = DEFAULT_SOURCE_REGISTRY,
) -> dict[str, object]:
    """Build the verified offline legal baseline shipped in the Windows bundle."""

    output_dir = output_dir.resolve()
    legal_dir = output_dir / "public-assets" / "legal"
    legal_dir.mkdir(parents=True, exist_ok=True)
    legal_db = legal_dir / "legal.db"
    retrieval_db = legal_dir / "retrieval.db"

    release = load_corpus_release(release_path.resolve())
    rebuilt = rebuild_legal_store_from_release(
        release,
        corpus_root=corpus_root.resolve(),
        db_path=legal_db,
        source_registry_path=source_registry_path.resolve(),
    )
    retrieval = build_retrieval_index(legal_db, retrieval_db)
    legal = get_summary(legal_db)

    expected = release["summary"]
    actual = {
        "authority_count": legal.authority_count,
        "version_count": legal.version_count,
        "article_count": legal.article_count,
    }
    wanted = {
        "authority_count": expected["authority_count"],
        "version_count": expected["version_count"],
        "article_count": expected["article_count"],
    }
    if actual != wanted:
        raise RuntimeError(f"Packaged corpus summary mismatch: expected {wanted}, found {actual}")
    if retrieval.article_count != expected["article_count"] or not retrieval.lexical_ready:
        raise RuntimeError("Packaged retrieval index does not cover the complete Corpus Release.")

    metadata: dict[str, object] = {
        "schema_version": "2.0.0",
        "asset_profile": "stage15.5-three-domain-baseline",
        "corpus_release": {
            "path": _repo_relative(release_path),
            "corpus_id": release["corpus_id"],
            "corpus_version": release["corpus_version"],
            "released_on": release["released_on"],
            "release_digest": release["release_digest"],
            "pack_count": release["summary"]["pack_count"],
        },
        "legal": {
            "ready": legal.ready,
            "authority_count": legal.authority_count,
            "version_count": legal.version_count,
            "article_count": legal.article_count,
            "excerpt_version_count": legal.excerpt_version_count,
            "sha256": _sha256(legal_db),
        },
        "retrieval": {
            "ready": retrieval.ready,
            "schema_version": retrieval.schema_version,
            "legal_source_fingerprint": retrieval.legal_source_fingerprint,
            "lexical_ready": retrieval.lexical_ready,
            "lexical_tokenizer": retrieval.lexical_tokenizer,
            "article_count": retrieval.article_count,
            "semantic_ready": retrieval.semantic_ready,
            "sha256": _sha256(retrieval_db),
        },
        "build_summary": rebuilt,
    }
    metadata_path = output_dir / "public-assets-metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the verified three-domain Corpus Release assets for the Windows bundle."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--release", type=Path, default=DEFAULT_CORPUS_RELEASE)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE_REGISTRY)
    args = parser.parse_args()

    metadata = build_public_release_assets(
        args.output_dir,
        args.release,
        corpus_root=args.corpus_root,
        source_registry_path=args.source_registry,
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
