from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

MODEL_MANIFEST_SCHEMA_VERSION = "1.0.0"
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_MEMBER_COUNT = 64
DOWNLOAD_CHUNK = 1024 * 1024


class OcrModelAssetError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedModel:
    model_name: str
    role: str
    archive_sha256: str
    archive_root: str
    packaged_dir: str
    files: dict[str, str]

    def model_dump(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "role": self.role,
            "archive_sha256": self.archive_sha256,
            "archive_root": self.archive_root,
            "packaged_dir": self.packaged_dir,
            "files": dict(self.files),
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(DOWNLOAD_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OcrModelAssetError(f"Could not load OCR model manifest: {type(exc).__name__}.") from exc
    if payload.get("schema_version") != MODEL_MANIFEST_SCHEMA_VERSION:
        raise OcrModelAssetError("Unsupported OCR model manifest schema version.")
    models = payload.get("models")
    if not isinstance(models, list) or len(models) != 2:
        raise OcrModelAssetError("OCR model manifest must contain exactly detection and recognition models.")
    roles = {item.get("role") for item in models if isinstance(item, dict)}
    if roles != {"text_detection", "text_recognition"}:
        raise OcrModelAssetError("OCR model manifest roles are incomplete or duplicated.")
    return payload


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Law-Rag-release-builder/14.5"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
            total = 0
            while True:
                chunk = response.read(DOWNLOAD_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise OcrModelAssetError("OCR model archive exceeded the release size limit.")
                output.write(chunk)
    except OcrModelAssetError:
        raise
    except Exception as exc:
        raise OcrModelAssetError(f"Could not download approved OCR model archive: {type(exc).__name__}.") from exc


def _validated_members(archive: tarfile.TarFile) -> tuple[list[tarfile.TarInfo], str]:
    members = archive.getmembers()
    if not members or len(members) > MAX_MEMBER_COUNT:
        raise OcrModelAssetError("OCR model archive has an invalid member count.")
    total_size = 0
    roots: set[str] = set()
    validated: list[tarfile.TarInfo] = []
    for member in members:
        posix = PurePosixPath(member.name)
        if posix.is_absolute() or ".." in posix.parts or not posix.parts:
            raise OcrModelAssetError("OCR model archive contains an unsafe path.")
        if member.issym() or member.islnk() or member.ischr() or member.isblk() or member.isfifo():
            raise OcrModelAssetError("OCR model archive contains an unsupported link/device entry.")
        if not (member.isdir() or member.isfile()):
            raise OcrModelAssetError("OCR model archive contains an unsupported member type.")
        roots.add(posix.parts[0])
        if member.isfile():
            if member.size < 0:
                raise OcrModelAssetError("OCR model archive contains an invalid file size.")
            total_size += member.size
            if total_size > MAX_EXTRACTED_BYTES:
                raise OcrModelAssetError("OCR model archive exceeds the extracted size limit.")
        validated.append(member)
    if len(roots) != 1:
        raise OcrModelAssetError("OCR model archive must contain exactly one top-level directory.")
    return validated, next(iter(roots))


def _safe_extract(archive_path: Path, destination: Path) -> str:
    with tarfile.open(archive_path, mode="r:*") as archive:
        members, archive_root = _validated_members(archive)
        destination.mkdir(parents=True, exist_ok=True)
        root_resolved = destination.resolve()
        for member in members:
            target = (destination / PurePosixPath(member.name)).resolve()
            if target != root_resolved and root_resolved not in target.parents:
                raise OcrModelAssetError("OCR model archive extraction escaped the staging directory.")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise OcrModelAssetError("OCR model archive file could not be read.")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=DOWNLOAD_CHUNK)
        return archive_root


def _verify_model_tree(model: dict[str, Any], extracted_root: Path, *, probe: bool) -> PreparedModel:
    model_name = model.get("model_name")
    role = model.get("role")
    packaged_dir = model.get("packaged_dir")
    required_files = model.get("required_files")
    expected_files = model.get("file_sha256")
    if not all(isinstance(value, str) and value for value in (model_name, role, packaged_dir)):
        raise OcrModelAssetError("OCR model manifest contains an invalid model identity.")
    if not isinstance(required_files, list) or not required_files or not all(isinstance(x, str) and x for x in required_files):
        raise OcrModelAssetError(f"OCR model {model_name} has invalid required_files.")
    if not isinstance(expected_files, dict):
        raise OcrModelAssetError(f"OCR model {model_name} has invalid file_sha256.")

    actual_files: dict[str, str] = {}
    for relative in required_files:
        path = extracted_root / relative
        if not path.is_file():
            raise OcrModelAssetError(f"OCR model {model_name} is missing required file {relative}.")
        actual_files[relative] = _sha256_file(path)
        expected = expected_files.get(relative)
        if not probe and expected != actual_files[relative]:
            raise OcrModelAssetError(f"OCR model {model_name} file hash mismatch for {relative}.")

    extras = sorted(
        str(path.relative_to(extracted_root)).replace("\\", "/")
        for path in extracted_root.rglob("*")
        if path.is_file() and str(path.relative_to(extracted_root)).replace("\\", "/") not in actual_files
    )
    if extras:
        raise OcrModelAssetError(f"OCR model {model_name} contains unexpected files: {', '.join(extras)}.")

    return PreparedModel(
        model_name=model_name,
        role=role,
        archive_sha256="",
        archive_root=extracted_root.name,
        packaged_dir=packaged_dir,
        files=actual_files,
    )


def prepare_ocr_models(*, manifest_path: Path, output_dir: Path, probe: bool = False) -> list[PreparedModel]:
    manifest = _load_manifest(manifest_path)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    prepared: list[PreparedModel] = []
    with tempfile.TemporaryDirectory(prefix="law-rag-ocr-models-") as temp_name:
        temp_root = Path(temp_name)
        for index, model in enumerate(manifest["models"], start=1):
            url = model.get("archive_url")
            expected_archive_hash = model.get("archive_sha256")
            expected_archive_root = model.get("archive_root")
            if not isinstance(url, str) or not url.startswith("https://paddle-model-ecology.bj.bcebos.com/"):
                raise OcrModelAssetError("OCR model archive URL is not an approved Paddle BOS HTTPS source.")
            if not probe and (not isinstance(expected_archive_hash, str) or len(expected_archive_hash) != 64):
                raise OcrModelAssetError("OCR model archive SHA-256 is not locked in the manifest.")
            archive_path = temp_root / f"model-{index}.tar"
            extract_parent = temp_root / f"extract-{index}"
            _download(url, archive_path)
            archive_hash = _sha256_file(archive_path)
            if not probe and archive_hash != expected_archive_hash:
                raise OcrModelAssetError(f"OCR model archive hash mismatch for {model.get('model_name')}.")
            archive_root = _safe_extract(archive_path, extract_parent)
            if not probe and archive_root != expected_archive_root:
                raise OcrModelAssetError(f"OCR model archive root mismatch for {model.get('model_name')}.")
            extracted_root = extract_parent / archive_root
            item = _verify_model_tree(model, extracted_root, probe=probe)
            item = PreparedModel(
                model_name=item.model_name,
                role=item.role,
                archive_sha256=archive_hash,
                archive_root=archive_root,
                packaged_dir=item.packaged_dir,
                files=item.files,
            )
            destination = output_dir / item.packaged_dir
            shutil.copytree(extracted_root, destination)
            prepared.append(item)

    metadata = {
        "schema_version": MODEL_MANIFEST_SCHEMA_VERSION,
        "artifact_set": manifest["artifact_set"],
        "models": [item.model_dump() for item in prepared],
    }
    (output_dir / "ocr-models-resolved.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return prepared


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and verify approved Law-Rag OCR model assets.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--probe", action="store_true", help="Discover hashes/root without accepting them for release.")
    args = parser.parse_args()
    try:
        prepared = prepare_ocr_models(manifest_path=args.manifest, output_dir=args.output_dir, probe=args.probe)
    except OcrModelAssetError as exc:
        raise SystemExit(f"OCR_MODEL_ASSET_ERROR: {exc}") from exc
    for item in prepared:
        print("OCR_MODEL_PROBE=" + json.dumps(item.model_dump(), sort_keys=True))


if __name__ == "__main__":
    main()
