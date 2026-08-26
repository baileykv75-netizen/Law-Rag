from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.release_corpus import ReleaseCorpusError, install_packaged_baseline, verify_packaged_baseline


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_packaged_assets(
    root: Path, *, asset_profile: str = "stage15.5-three-domain-baseline"
) -> tuple[Path, Path]:
    legal_dir = root / "public-assets" / "legal"
    metadata_dir = root / "release"
    legal_dir.mkdir(parents=True)
    metadata_dir.mkdir(parents=True)
    legal = legal_dir / "legal.db"
    retrieval = legal_dir / "retrieval.db"
    legal.write_bytes(b"verified-three-domain-legal-db")
    retrieval.write_bytes(b"verified-three-domain-retrieval-db")
    metadata = {
        "schema_version": "2.0.0",
        "asset_profile": asset_profile,
        "corpus_release": {
            "path": "legal_data/releases/three-domain-core/1.0.0/release.json",
            "corpus_id": "three-domain-core",
            "corpus_version": "1.0.0",
            "released_on": "2026-08-20",
            "release_digest": "4009c06967cd2281089e85bdfda64388dd4ac8fc3b86125d971bfa1c0f642b4f",
            "pack_count": 3,
        },
        "legal": {"sha256": _sha256(legal)},
        "retrieval": {"sha256": _sha256(retrieval)},
    }
    (metadata_dir / "public-assets-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    return legal, retrieval


def test_packaged_baseline_is_verified_and_installed_as_one_runtime_directory(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    source_legal, source_retrieval = _fake_packaged_assets(asset_root)
    runtime = tmp_path / "runtime"

    metadata = verify_packaged_baseline(asset_root)
    result = install_packaged_baseline(asset_root, runtime)

    assert metadata["corpus_release"]["corpus_version"] == "1.0.0"
    assert result["state"] == "INSTALLED_BASELINE"
    assert (runtime / "legal" / "legal.db").read_bytes() == source_legal.read_bytes()
    assert (runtime / "legal" / "retrieval.db").read_bytes() == source_retrieval.read_bytes()
    installed = json.loads((runtime / "legal" / "installed-corpus.json").read_text(encoding="utf-8"))
    assert installed["installation_source"] == "PACKAGED_BASELINE"
    assert installed["corpus_release"]["release_digest"] == metadata["corpus_release"]["release_digest"]
    assert not (runtime / ".legal-baseline-install.tmp").exists()


def test_competition_construction_baseline_profile_is_supported(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    _fake_packaged_assets(asset_root, asset_profile="stage15.5-competition-construction-baseline")

    metadata = verify_packaged_baseline(asset_root)

    assert metadata["asset_profile"] == "stage15.5-competition-construction-baseline"


def test_application_upgrade_never_overwrites_complete_runtime_corpus(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    _fake_packaged_assets(asset_root)
    runtime_legal = tmp_path / "runtime" / "legal"
    runtime_legal.mkdir(parents=True)
    legal = runtime_legal / "legal.db"
    retrieval = runtime_legal / "retrieval.db"
    legal.write_bytes(b"newer-user-corpus")
    retrieval.write_bytes(b"newer-user-index")

    result = install_packaged_baseline(asset_root, tmp_path / "runtime")

    assert result["state"] == "EXISTING_RUNTIME"
    assert legal.read_bytes() == b"newer-user-corpus"
    assert retrieval.read_bytes() == b"newer-user-index"


def test_incomplete_runtime_corpus_fails_closed_instead_of_mixing_versions(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    _fake_packaged_assets(asset_root)
    runtime_legal = tmp_path / "runtime" / "legal"
    runtime_legal.mkdir(parents=True)
    (runtime_legal / "legal.db").write_bytes(b"possibly-updated-user-corpus")

    with pytest.raises(ReleaseCorpusError, match="incomplete"):
        install_packaged_baseline(asset_root, tmp_path / "runtime")

    assert (runtime_legal / "legal.db").read_bytes() == b"possibly-updated-user-corpus"
    assert not (runtime_legal / "retrieval.db").exists()


def test_tampered_packaged_asset_is_rejected_before_runtime_install(tmp_path: Path) -> None:
    asset_root = tmp_path / "assets"
    _, retrieval = _fake_packaged_assets(asset_root)
    retrieval.write_bytes(b"tampered")

    with pytest.raises(ReleaseCorpusError, match="SHA-256 mismatch"):
        install_packaged_baseline(asset_root, tmp_path / "runtime")

    assert not (tmp_path / "runtime" / "legal").exists()
