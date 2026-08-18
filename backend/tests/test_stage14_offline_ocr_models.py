from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import types
from pathlib import Path

import pytest

from app.ocr import PaddleOcrProvider
from app.ocr_model_assets import OcrModelAssetError, _validated_members
from app.ocr_models import OcrModelIntegrityError, probe_ocr_models, resolve_ocr_model_paths


MODEL_FILES = {
    "inference.json": b'{"fixture":true}\n',
    "inference.pdiparams": b"fictional-parameters",
    "inference.yml": b"Global:\n  model_name: fixture\n",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixture_models(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "ocr-models"
    models = []
    for role, model_name in (
        ("text_detection", "PP-OCRv6_medium_det"),
        ("text_recognition", "PP-OCRv6_medium_rec"),
    ):
        directory = root / model_name
        directory.mkdir(parents=True)
        for name, payload in MODEL_FILES.items():
            (directory / name).write_bytes(payload)
        models.append(
            {
                "role": role,
                "model_name": model_name,
                "archive_url": f"https://paddle-model-ecology.bj.bcebos.com/{model_name}.tar",
                "archive_sha256": "a" * 64,
                "archive_root": model_name + "_infer",
                "packaged_dir": model_name,
                "required_files": list(MODEL_FILES),
                "file_sha256": {name: _sha(payload) for name, payload in MODEL_FILES.items()},
            }
        )
    manifest = tmp_path / "ocr-models-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "artifact_set": "fixture",
                "distribution_policy": "build-time-fetch-verified-package-runtime-offline",
                "models": models,
            }
        ),
        encoding="utf-8",
    )
    return root, manifest


def test_checked_in_model_manifest_is_fully_locked() -> None:
    manifest_path = Path(__file__).resolve().parents[2] / "release" / "ocr-models-manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0.0"
    assert payload["license"] == "Apache-2.0"
    assert [item["model_name"] for item in payload["models"]] == [
        "PP-OCRv6_medium_det",
        "PP-OCRv6_medium_rec",
    ]
    for model in payload["models"]:
        assert len(model["archive_sha256"]) == 64
        assert model["archive_root"].endswith("_infer")
        assert set(model["required_files"]) == {"inference.json", "inference.pdiparams", "inference.yml"}
        assert set(model["file_sha256"]) == set(model["required_files"])
        assert all(len(value) == 64 for value in model["file_sha256"].values())


def test_frozen_paddlex_ocr_config_uses_only_approved_models() -> None:
    config_path = (
        Path(__file__).resolve().parents[2]
        / "release"
        / "paddlex"
        / "configs"
        / "pipelines"
        / "OCR.yaml"
    )
    text = config_path.read_text(encoding="utf-8")

    assert "pipeline_name: OCR" in text
    assert "use_doc_preprocessor: false" in text
    assert "use_textline_orientation: false" in text
    assert text.count("model_name:") == 2
    assert "model_name: PP-OCRv6_medium_det" in text
    assert "model_name: PP-OCRv6_medium_rec" in text
    assert "UVDoc" not in text
    assert "PP-LCNet" not in text


def test_model_resolver_requires_exact_files_and_hashes(tmp_path: Path) -> None:
    root, manifest = _fixture_models(tmp_path)
    paths = resolve_ocr_model_paths(model_root=root, manifest_path=manifest)
    assert paths.detection.name == "PP-OCRv6_medium_det"
    assert paths.recognition.name == "PP-OCRv6_medium_rec"
    assert probe_ocr_models(model_root=root, manifest_path=manifest).state == "READY"

    (paths.detection / "inference.pdiparams").write_bytes(b"tampered")
    with pytest.raises(OcrModelIntegrityError, match="integrity check failed"):
        resolve_ocr_model_paths(model_root=root, manifest_path=manifest)
    probe = probe_ocr_models(model_root=root, manifest_path=manifest)
    assert not probe.ready
    assert probe.state == "CORRUPT"


def test_model_resolver_rejects_unexpected_model_payload(tmp_path: Path) -> None:
    root, manifest = _fixture_models(tmp_path)
    extra = root / "PP-OCRv6_medium_rec" / "download-marker.txt"
    extra.write_text("not approved", encoding="utf-8")
    with pytest.raises(OcrModelIntegrityError, match="file set mismatch"):
        resolve_ocr_model_paths(model_root=root, manifest_path=manifest)


def test_paddle_provider_passes_verified_local_directories_without_download_fallback(tmp_path: Path, monkeypatch) -> None:
    root, manifest = _fixture_models(tmp_path)
    captured: dict[str, object] = {}

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def predict(self, image_path: str):
            return []

    monkeypatch.setitem(sys.modules, "paddleocr", types.SimpleNamespace(PaddleOCR=FakePaddleOCR))
    provider = PaddleOcrProvider(
        model_root=root,
        model_manifest_path=manifest,
        provider_version="3.7.0-test",
    )
    provider.recognize(Path("fixture.png"), 1)

    assert captured["text_detection_model_name"] == "PP-OCRv6_medium_det"
    assert captured["text_recognition_model_name"] == "PP-OCRv6_medium_rec"
    assert captured["text_detection_model_dir"] == str((root / "PP-OCRv6_medium_det").resolve())
    assert captured["text_recognition_model_dir"] == str((root / "PP-OCRv6_medium_rec").resolve())
    assert captured["engine"] == "paddle_static"
    assert captured["device"] == "cpu"


def test_fake_pipeline_factory_does_not_require_release_models() -> None:
    class FakePipeline:
        def predict(self, image_path: str):
            return []

    provider = PaddleOcrProvider(pipeline_factory=lambda: FakePipeline(), provider_version="test")
    assert provider.recognize(Path("fixture.png"), 1) == []


def test_archive_validation_rejects_traversal_and_links() -> None:
    traversal = io.BytesIO()
    with tarfile.open(fileobj=traversal, mode="w") as archive:
        info = tarfile.TarInfo("../escape.txt")
        payload = b"x"
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    traversal.seek(0)
    with tarfile.open(fileobj=traversal, mode="r") as archive:
        with pytest.raises(OcrModelAssetError, match="unsafe path"):
            _validated_members(archive)

    linked = io.BytesIO()
    with tarfile.open(fileobj=linked, mode="w") as archive:
        info = tarfile.TarInfo("model/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "target"
        archive.addfile(info)
    linked.seek(0)
    with tarfile.open(fileobj=linked, mode="r") as archive:
        with pytest.raises(OcrModelAssetError, match="link/device"):
            _validated_members(archive)
