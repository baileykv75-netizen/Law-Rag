from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .legal.importer import import_manifest
from .legal.retrieval import build_retrieval_index
from .legal.store import get_summary

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO_ROOT / "legal_data" / "seed" / "manifest.json"
DEFAULT_OUTPUT = REPO_ROOT / "release" / ".build"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_public_release_assets(output_dir: Path, manifest: Path = DEFAULT_MANIFEST) -> dict[str, object]:
    output_dir = output_dir.resolve()
    legal_dir = output_dir / "public-assets" / "legal"
    legal_dir.mkdir(parents=True, exist_ok=True)
    legal_db = legal_dir / "legal.db"
    retrieval_db = legal_dir / "retrieval.db"
    report_path = output_dir / "legal-import-report.json"

    import_report = import_manifest(
        manifest.resolve(),
        legal_db,
        rebuild=True,
        report_path=report_path,
    )
    retrieval = build_retrieval_index(legal_db, retrieval_db)
    legal = get_summary(legal_db)

    metadata: dict[str, object] = {
        "schema_version": "1.0.0",
        "asset_profile": "stage11d-public-base",
        "manifest": str(manifest.resolve().relative_to(REPO_ROOT)),
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
        "import_summary": {
            "imported_records": import_report.imported_records,
            "rejected_records": import_report.rejected_records,
            "no_change_records": import_report.no_change_records,
        },
    }
    metadata_path = output_dir / "public-assets-metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Build public-only Law-Rag Stage 11D release assets.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    metadata = build_public_release_assets(args.output_dir, args.manifest)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
