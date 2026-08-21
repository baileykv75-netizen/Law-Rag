from __future__ import annotations

import json
from pathlib import Path

from app.release_assets_cli import DEFAULT_CORPUS_RELEASE, build_public_release_assets


def test_public_release_assets_build_verified_three_domain_baseline(tmp_path: Path) -> None:
    output = tmp_path / "release-build"

    metadata = build_public_release_assets(output, DEFAULT_CORPUS_RELEASE)

    legal_db = output / "public-assets" / "legal" / "legal.db"
    retrieval_db = output / "public-assets" / "legal" / "retrieval.db"
    metadata_path = output / "public-assets-metadata.json"
    assert legal_db.is_file()
    assert retrieval_db.is_file()
    assert metadata_path.is_file()
    assert metadata["schema_version"] == "2.0.0"
    assert metadata["asset_profile"] == "stage15.5-three-domain-baseline"
    assert metadata["corpus_release"]["corpus_id"] == "three-domain-core"
    assert metadata["corpus_release"]["corpus_version"] == "1.0.0"
    assert metadata["corpus_release"]["release_digest"] == (
        "4009c06967cd2281089e85bdfda64388dd4ac8fc3b86125d971bfa1c0f642b4f"
    )
    assert metadata["legal"]["ready"] is True
    assert metadata["legal"]["authority_count"] == 14
    assert metadata["legal"]["version_count"] == 15
    assert metadata["legal"]["article_count"] == 1274
    assert metadata["legal"]["excerpt_version_count"] == 0
    assert metadata["retrieval"]["ready"] is True
    assert metadata["retrieval"]["lexical_ready"] is True
    assert metadata["retrieval"]["article_count"] == 1274
    assert metadata["retrieval"]["semantic_ready"] is False
    assert metadata["build_summary"] == {
        "corpus_id": "three-domain-core",
        "corpus_version": "1.0.0",
        "pack_count": 3,
        "authority_count": 14,
        "version_count": 15,
        "article_count": 1274,
    }

    persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert persisted == metadata
    assert str(tmp_path) not in metadata_path.read_text(encoding="utf-8")


def test_public_release_asset_build_is_content_reproducible(tmp_path: Path) -> None:
    first = build_public_release_assets(tmp_path / "first", DEFAULT_CORPUS_RELEASE)
    second = build_public_release_assets(tmp_path / "second", DEFAULT_CORPUS_RELEASE)

    assert first["legal"]["sha256"] == second["legal"]["sha256"]
    assert first["retrieval"]["sha256"] == second["retrieval"]["sha256"]
    assert first["retrieval"]["legal_source_fingerprint"] == second["retrieval"]["legal_source_fingerprint"]
    assert first["corpus_release"] == second["corpus_release"]
