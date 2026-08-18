from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.rc_archive_cli import build_rc_artifacts


def _fixture_bundle(root: Path) -> Path:
    bundle = root / "Law-Rag"
    (bundle / "_internal" / "release").mkdir(parents=True)
    (bundle / "_internal" / "THIRD-PARTY-NOTICES").mkdir(parents=True)
    (bundle / "_internal" / "frontend-dist").mkdir(parents=True)
    (bundle / "Law-Rag.exe").write_bytes(b"fictional-exe-bytes")
    (bundle / "README-WINDOWS.md").write_text("fixture", encoding="utf-8")
    (bundle / "_internal" / "release" / "release-metadata.json").write_text(
        json.dumps(
            {
                "application_version": "0.8.0",
                "source_commit_sha": "a" * 40,
                "toolchain": {"python": "3.12.10", "pyinstaller": "6.22.0"},
            }
        ),
        encoding="utf-8",
    )
    (bundle / "_internal" / "release" / "public-assets-metadata.json").write_text(
        json.dumps(
            {
                "legal": {"sha256": "1" * 64},
                "retrieval": {"sha256": "2" * 64, "legal_source_fingerprint": "3" * 64},
            }
        ),
        encoding="utf-8",
    )
    (bundle / "_internal" / "release" / "dependency-inventory.json").write_text("{}", encoding="utf-8")
    (bundle / "_internal" / "THIRD-PARTY-NOTICES" / "python-third-party-notices.json").write_text(
        "{}", encoding="utf-8"
    )
    (bundle / "_internal" / "frontend-dist" / "third-party-frontend-licenses.json").write_text(
        "{}", encoding="utf-8"
    )
    return bundle


def _config(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "rc_version": "0.8.0-rc1",
                "target": "windows-x64",
                "artifact_basename": "Law-Rag-0.8.0-rc1-windows-x64",
                "distribution_mode": "portable-onedir-zip",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_rc_archive_is_deterministic_and_manifest_has_no_local_paths(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path / "input")
    config = _config(tmp_path / "rc-config.json")

    first = build_rc_artifacts(bundle_dir=bundle, config_path=config, output_dir=tmp_path / "first")
    second = build_rc_artifacts(bundle_dir=bundle, config_path=config, output_dir=tmp_path / "second")

    assert first["artifact"]["sha256"] == second["artifact"]["sha256"]
    assert first["artifact"]["size_bytes"] == second["artifact"]["size_bytes"]
    assert first["source_commit_sha"] == "a" * 40
    assert first["publication_state"] == "NOT_PUBLISHED"
    assert first["reproducibility"]["wall_clock_timestamp_embedded"] is False

    zip_path = tmp_path / "first" / "Law-Rag-0.8.0-rc1-windows-x64.zip"
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        assert "Law-Rag/Law-Rag.exe" in names
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())

    manifest_text = (tmp_path / "first" / "RC-MANIFEST.json").read_text(encoding="utf-8")
    sums = (tmp_path / "first" / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert str(tmp_path) not in manifest_text
    assert first["artifact"]["sha256"] in sums


def test_rc_archive_allows_dependency_internal_runtime_code_directory(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path / "input")
    nested_runtime = bundle / "_internal" / "paddlex" / "inference" / "runtime"
    nested_runtime.mkdir(parents=True)
    (nested_runtime / "engine.py").write_text("# dependency code", encoding="utf-8")
    config = _config(tmp_path / "rc-config.json")

    manifest = build_rc_artifacts(bundle_dir=bundle, config_path=config, output_dir=tmp_path / "out")

    assert manifest["publication_state"] == "NOT_PUBLISHED"
    with zipfile.ZipFile(tmp_path / "out" / "Law-Rag-0.8.0-rc1-windows-x64.zip") as archive:
        assert "Law-Rag/_internal/paddlex/inference/runtime/engine.py" in archive.namelist()


def test_rc_archive_rejects_private_runtime_directory_at_bundle_root(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path / "input")
    (bundle / "runtime").mkdir()
    (bundle / "runtime" / "private.json").write_text("{}", encoding="utf-8")
    config = _config(tmp_path / "rc-config.json")

    with pytest.raises(RuntimeError, match="banned private application directory: runtime"):
        build_rc_artifacts(bundle_dir=bundle, config_path=config, output_dir=tmp_path / "out")


@pytest.mark.parametrize("relative", ["_internal/paddlex/.paddlex", "_internal/paddleocr/model_cache"])
def test_rc_archive_rejects_nested_ocr_cache_directory(tmp_path: Path, relative: str) -> None:
    bundle = _fixture_bundle(tmp_path / "input")
    cache = bundle / relative
    cache.mkdir(parents=True)
    (cache / "cache.bin").write_bytes(b"not-a-real-model")
    config = _config(tmp_path / "rc-config.json")

    with pytest.raises(RuntimeError, match="banned OCR cache directory"):
        build_rc_artifacts(bundle_dir=bundle, config_path=config, output_dir=tmp_path / "out")


def test_rc_archive_rejects_nested_ocr_model_payload_directory(tmp_path: Path) -> None:
    bundle = _fixture_bundle(tmp_path / "input")
    model_dir = bundle / "_internal" / "paddlex" / "official_models" / "PP-OCRv6_mobile_det"
    model_dir.mkdir(parents=True)
    (model_dir / "inference.pdmodel").write_bytes(b"not-a-real-model")
    config = _config(tmp_path / "rc-config.json")

    with pytest.raises(RuntimeError, match="banned OCR model directory"):
        build_rc_artifacts(bundle_dir=bundle, config_path=config, output_dir=tmp_path / "out")
