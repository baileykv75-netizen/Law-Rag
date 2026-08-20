from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .corpus_inventory import (
    CatalogEntryState,
    OfficialCorpusCatalog,
    PlannedLegalVersion,
    load_official_corpus_catalog,
)
from .fulltext_snapshot import FullTextSnapshotError, build_full_text_manifest_record
from .models import LegalManifest
from .parser import normalize_snapshot_text
from .snapshot_targets import SnapshotTargetState, SnapshotTargetsError, load_snapshot_targets
from .source_registry import LegalSourceRegistryError, load_source_registry

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG = REPO_ROOT / "legal_data" / "catalog" / "three-domain-core.json"
DEFAULT_SOURCE_REGISTRY = REPO_ROOT / "legal_data" / "source_registry.json"
SNAPSHOT_FILENAME = "snapshot.txt"
MANIFEST_FILENAME = "manifest.json"


class FullTextSnapshotFreezeError(RuntimeError):
    pass


def _read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FullTextSnapshotFreezeError(f"Source file must be valid UTF-8 text: {path}") from exc
    except OSError as exc:
        raise FullTextSnapshotFreezeError(f"Unable to read source file {path}: {exc}") from exc


def _existing_conflict(path: Path, expected: str) -> bool:
    if not path.exists():
        return False
    try:
        return path.read_text(encoding="utf-8") != expected
    except OSError as exc:
        raise FullTextSnapshotFreezeError(f"Unable to inspect existing output {path}: {exc}") from exc


def _write_utf8_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _version_links(
    catalog: OfficialCorpusCatalog,
    entry: PlannedLegalVersion,
) -> tuple[str | None, str | None]:
    """Derive adjacent version links only when effective intervals touch exactly.

    Stage 15 catalog ordering is the provenance source for version transitions. A gap
    must not be silently represented as a supersession relationship, and BLOCKED
    versions are excluded because they are not uniformly representable Authority
    Versions in the current legal store.
    """

    versions = sorted(
        (
            item
            for item in catalog.entries
            if item.authority.authority_id == entry.authority.authority_id
            and item.catalog_state != CatalogEntryState.BLOCKED
        ),
        key=lambda item: (item.effective_date, item.version_id),
    )
    matches = [index for index, item in enumerate(versions) if item.version_id == entry.version_id]
    if len(matches) != 1:
        raise FullTextSnapshotFreezeError(
            f"Catalog version timeline could not resolve {entry.authority.authority_id}:{entry.version_id} exactly once."
        )

    index = matches[0]
    supersedes_version_id: str | None = None
    superseded_by_version_id: str | None = None

    if index > 0:
        previous = versions[index - 1]
        if previous.end_date_exclusive == entry.effective_date:
            supersedes_version_id = previous.version_id

    if index + 1 < len(versions):
        following = versions[index + 1]
        if entry.end_date_exclusive == following.effective_date:
            superseded_by_version_id = following.version_id

    return supersedes_version_id, superseded_by_version_id


def freeze_full_text_snapshot(
    *,
    catalog_path: Path,
    source_registry_path: Path,
    target_set_path: Path,
    authority_id: str,
    version_id: str,
    source_file: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Freeze one already-obtained official UTF-8 legal text into deterministic corpus inputs.

    Network fetching and HTML extraction are intentionally outside this function. The
    caller supplies the exact plain-text source bytes. This function validates the
    Stage 15 source target, full contiguous article sequence, source role policy and
    then writes a normalized snapshot plus one-record Stage 6 LegalManifest.
    """

    catalog_path = catalog_path.resolve()
    source_registry_path = source_registry_path.resolve()
    target_set_path = target_set_path.resolve()
    source_file = source_file.resolve()
    output_dir = output_dir.resolve()

    try:
        registry = load_source_registry(source_registry_path)
        catalog = load_official_corpus_catalog(
            catalog_path,
            registry=registry,
            corpus_root=catalog_path.parent.parent,
        )
        targets = load_snapshot_targets(target_set_path, catalog=catalog, registry=registry)
    except (LegalSourceRegistryError, SnapshotTargetsError, RuntimeError) as exc:
        if isinstance(exc, FullTextSnapshotFreezeError):
            raise
        raise FullTextSnapshotFreezeError(f"Unable to load Stage 15 snapshot metadata: {exc}") from exc

    matches = [
        item
        for item in targets.targets
        if item.authority_id == authority_id and item.version_id == version_id
    ]
    if len(matches) != 1:
        raise FullTextSnapshotFreezeError(
            f"Snapshot target {authority_id}:{version_id} was not found exactly once in {target_set_path}."
        )
    target = matches[0]
    if target.state != SnapshotTargetState.READY_FOR_FREEZE:
        raise FullTextSnapshotFreezeError(
            f"Snapshot target {authority_id}:{version_id} is {target.state.value}, not READY_FOR_FREEZE."
        )
    if target.snapshot_source_url is None or target.expected_article_count is None:
        raise FullTextSnapshotFreezeError("READY_FOR_FREEZE target is missing source URL or article count")

    catalog_matches = [
        item
        for item in catalog.entries
        if item.authority.authority_id == authority_id and item.version_id == version_id
    ]
    if len(catalog_matches) != 1:
        raise FullTextSnapshotFreezeError(
            f"Catalog identity {authority_id}:{version_id} was not found exactly once."
        )
    entry = catalog_matches[0]
    source_text = _read_utf8(source_file)

    try:
        record = build_full_text_manifest_record(
            entry,
            snapshot_text=source_text,
            snapshot_path=SNAPSHOT_FILENAME,
            snapshot_source_url=str(target.snapshot_source_url),
            supplemental_source_ref=target.supplemental_source_ref,
            expected_article_count=target.expected_article_count,
            registry=registry,
            verified_on=targets.verified_on,
        )
    except FullTextSnapshotError as exc:
        raise FullTextSnapshotFreezeError(str(exc)) from exc

    supersedes_version_id, superseded_by_version_id = _version_links(catalog, entry)
    record = record.model_copy(
        update={
            "supersedes_version_id": supersedes_version_id,
            "superseded_by_version_id": superseded_by_version_id,
        }
    )

    normalized_snapshot = normalize_snapshot_text(source_text)
    manifest = LegalManifest(records=[record])
    manifest_text = manifest.model_dump_json(indent=2) + "\n"
    snapshot_path = output_dir / SNAPSHOT_FILENAME
    manifest_path = output_dir / MANIFEST_FILENAME

    conflicts = [
        str(path)
        for path, expected in (
            (snapshot_path, normalized_snapshot),
            (manifest_path, manifest_text),
        )
        if _existing_conflict(path, expected)
    ]
    if conflicts:
        raise FullTextSnapshotFreezeError(
            "Refusing to overwrite different frozen corpus output(s): " + ", ".join(conflicts)
        )

    if not snapshot_path.exists():
        _write_utf8_atomic(snapshot_path, normalized_snapshot)
    if not manifest_path.exists():
        _write_utf8_atomic(manifest_path, manifest_text)

    return {
        "authority_id": authority_id,
        "version_id": version_id,
        "snapshot_path": str(snapshot_path),
        "manifest_path": str(manifest_path),
        "source_sha256": record.expected_source_sha256,
        "article_count": record.expected_article_count,
        "source_url": str(target.snapshot_source_url),
        "supplemental_text_source": target.supplemental_source_ref is not None,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze one vetted Stage 15 official full-text source into deterministic legal corpus inputs."
    )
    parser.add_argument("--target-set", required=True, type=Path)
    parser.add_argument("--authority-id", required=True)
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--source-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--source-registry", type=Path, default=DEFAULT_SOURCE_REGISTRY)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        result = freeze_full_text_snapshot(
            catalog_path=args.catalog,
            source_registry_path=args.source_registry,
            target_set_path=args.target_set,
            authority_id=args.authority_id,
            version_id=args.version_id,
            source_file=args.source_file,
            output_dir=args.output_dir,
        )
    except FullTextSnapshotFreezeError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
