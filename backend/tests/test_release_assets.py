from __future__ import annotations

import json
from pathlib import Path

from app.release_assets_cli import DEFAULT_MANIFEST, build_public_release_assets


def test_public_release_assets_build_only_verified_lexical_base(tmp_path: Path) -> None:
    output = tmp_path / "release-build"

    metadata = build_public_release_assets(output, DEFAULT_MANIFEST)

    legal_db = output / "public-assets" / "legal" / "legal.db"
    retrieval_db = output / "public-assets" / "legal" / "retrieval.db"
    metadata_path = output / "public-assets-metadata.json"
    assert legal_db.is_file()
    assert retrieval_db.is_file()
    assert metadata_path.is_file()
    assert metadata["legal"]["ready"] is True
    assert metadata["legal"]["authority_count"] == 2
    assert metadata["legal"]["article_count"] == 15
    assert metadata["retrieval"]["ready"] is True
    assert metadata["retrieval"]["lexical_ready"] is True
    assert metadata["retrieval"]["semantic_ready"] is False
    assert metadata["import_summary"]["rejected_records"] == 0

    persisted = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert persisted == metadata
    assert str(tmp_path) not in metadata_path.read_text(encoding="utf-8")


def test_public_release_asset_build_is_content_reproducible(tmp_path: Path) -> None:
    first = build_public_release_assets(tmp_path / "first", DEFAULT_MANIFEST)
    second = build_public_release_assets(tmp_path / "second", DEFAULT_MANIFEST)

    assert first["legal"]["sha256"] == second["legal"]["sha256"]
    assert first["retrieval"]["sha256"] == second["retrieval"]["sha256"]
    assert first["retrieval"]["legal_source_fingerprint"] == second["retrieval"]["legal_source_fingerprint"]
