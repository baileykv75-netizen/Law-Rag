from __future__ import annotations

from datetime import date
from pathlib import PurePosixPath

from .corpus_inventory import CatalogEntryState, PlannedLegalVersion
from .models import CoverageType, ManifestRecord, OfficialSourceRef, SourceRole
from .parser import LegalParseError, normalize_snapshot_text, parse_chinese_articles, sha256_text
from .source_registry import LegalSourceRegistry, LegalSourceRegistryError, validate_official_source_ref


class FullTextSnapshotError(RuntimeError):
    pass


FULL_TEXT_SOURCE_ROLES = {SourceRole.PRIMARY, SourceRole.TEXT}


def _normalize_url(value: str) -> str:
    return value.rstrip("/")


def _validate_snapshot_path(snapshot_path: str) -> str:
    if not snapshot_path or "\\" in snapshot_path:
        raise FullTextSnapshotError("snapshot_path must be a non-empty POSIX relative path")
    path = PurePosixPath(snapshot_path)
    parts = path.parts
    if not parts or path.is_absolute() or ":" in parts[0] or ".." in parts:
        raise FullTextSnapshotError("snapshot_path must stay relative to its manifest directory")
    if any(part in {"", "."} for part in parts):
        raise FullTextSnapshotError("snapshot_path contains an invalid path component")
    return path.as_posix()


def _snapshot_source_ref(
    entry: PlannedLegalVersion,
    snapshot_source_url: str,
    supplemental_source_ref: OfficialSourceRef | None,
) -> tuple[OfficialSourceRef, list[OfficialSourceRef]]:
    target = _normalize_url(snapshot_source_url)
    matching_refs = [ref for ref in entry.source_refs if _normalize_url(str(ref.url)) == target]
    if len(matching_refs) > 1:
        raise FullTextSnapshotError("snapshot_source_url matches duplicate catalog source_refs")
    if matching_refs:
        if supplemental_source_ref is not None:
            raise FullTextSnapshotError("Catalog snapshot sources must not also declare a supplemental source_ref")
        source_ref = matching_refs[0]
        if source_ref.role not in FULL_TEXT_SOURCE_ROLES:
            raise FullTextSnapshotError(
                f"Snapshot source role {source_ref.role.value} cannot supply normative full text; use PRIMARY or TEXT."
            )
        return source_ref, list(entry.source_refs)

    if supplemental_source_ref is None:
        raise FullTextSnapshotError(
            "snapshot_source_url must match a vetted catalog source_ref or provide a supplemental TEXT source_ref"
        )
    if _normalize_url(str(supplemental_source_ref.url)) != target:
        raise FullTextSnapshotError("supplemental source URL must equal snapshot_source_url")
    if supplemental_source_ref.role != SourceRole.TEXT:
        raise FullTextSnapshotError(
            "Supplemental full-text sources may use TEXT only; new PRIMARY provenance must be vetted in the catalog first."
        )
    return supplemental_source_ref, [*entry.source_refs, supplemental_source_ref]


def _validate_registry(entry: PlannedLegalVersion, registry: LegalSourceRegistry) -> None:
    for ref in entry.source_refs:
        try:
            validate_official_source_ref(ref, registry)
        except LegalSourceRegistryError as exc:
            raise FullTextSnapshotError(f"Catalog source policy no longer validates: {exc}") from exc


def _validate_full_text_articles(
    snapshot_text: str,
    *,
    authority_id: str,
    version_id: str,
    expected_article_count: int,
) -> tuple[str, int]:
    if expected_article_count < 1:
        raise FullTextSnapshotError("expected_article_count must be positive")

    normalized = normalize_snapshot_text(snapshot_text)
    try:
        parsed = parse_chinese_articles(
            normalized,
            authority_id=authority_id,
            version_id=version_id,
        )
    except LegalParseError as exc:
        raise FullTextSnapshotError(f"Full-text article parsing failed: {exc}") from exc

    ordinals = [article.article_ordinal for article in parsed.articles]
    if any(value is None for value in ordinals):
        raise FullTextSnapshotError("FULL_TEXT snapshots require every article heading to have a numeric ordinal")

    actual_ordinals = [int(value) for value in ordinals if value is not None]
    expected_ordinals = list(range(1, expected_article_count + 1))
    if actual_ordinals != expected_ordinals:
        raise FullTextSnapshotError(
            "FULL_TEXT snapshot article ordinals must be exactly contiguous from 1 through "
            f"{expected_article_count}; parsed {len(actual_ordinals)} articles with range "
            f"{actual_ordinals[:3]}...{actual_ordinals[-3:] if actual_ordinals else []}."
        )

    if len(parsed.articles) != expected_article_count:
        raise FullTextSnapshotError(
            f"Expected {expected_article_count} articles but parsed {len(parsed.articles)}."
        )
    return normalized, len(parsed.articles)


def build_full_text_manifest_record(
    entry: PlannedLegalVersion,
    *,
    snapshot_text: str,
    snapshot_path: str,
    snapshot_source_url: str,
    expected_article_count: int,
    registry: LegalSourceRegistry,
    verified_on: date,
    supplemental_source_ref: OfficialSourceRef | None = None,
) -> ManifestRecord:
    """Build one Stage 6-compatible manifest record after strict FULL_TEXT validation.

    This function performs no network access. The caller must first obtain the exact
    official source text. A record is emitted only when the source remains valid under
    the Stage 15 registry and article ordinals form the complete sequence 1..N.

    A Stage 15.2B snapshot target may add one registry-approved TEXT carrier that was
    discovered after the 15.2A Authority/Version inventory. Supplemental sources can
    never create or replace PRIMARY provenance.
    """

    if entry.catalog_state == CatalogEntryState.BLOCKED:
        raise FullTextSnapshotError("BLOCKED catalog entries cannot be frozen as uniform FULL_TEXT versions")
    if entry.target_coverage != CoverageType.FULL_TEXT:
        raise FullTextSnapshotError("Stage 15.2B full-text freezing requires target_coverage=FULL_TEXT")

    _validate_registry(entry, registry)
    source_ref, manifest_source_refs = _snapshot_source_ref(
        entry,
        snapshot_source_url,
        supplemental_source_ref,
    )
    if supplemental_source_ref is not None:
        try:
            validate_official_source_ref(supplemental_source_ref, registry)
        except LegalSourceRegistryError as exc:
            raise FullTextSnapshotError(f"Supplemental source policy does not validate: {exc}") from exc

    safe_snapshot_path = _validate_snapshot_path(snapshot_path)
    normalized, parsed_count = _validate_full_text_articles(
        snapshot_text,
        authority_id=entry.authority.authority_id,
        version_id=entry.version_id,
        expected_article_count=expected_article_count,
    )
    source_hash = sha256_text(normalized)

    return ManifestRecord(
        authority=entry.authority,
        version_id=entry.version_id,
        status=entry.status,
        publication_date=entry.publication_date,
        effective_date=entry.effective_date,
        end_date_exclusive=entry.end_date_exclusive,
        repeal_date=None,
        supersedes_version_id=None,
        superseded_by_version_id=None,
        coverage_type=CoverageType.FULL_TEXT,
        coverage_note=(
            "Stage 15.2B verified official full-text snapshot; "
            f"{parsed_count} contiguous articles (1-{parsed_count}) were frozen from {source_ref.name}."
        ),
        source_refs=manifest_source_refs,
        snapshot_path=safe_snapshot_path,
        expected_source_sha256=source_hash,
        expected_article_count=parsed_count,
        parser="chinese-articles-v1",
        inclusion_reason=entry.notes,
        verified_on=verified_on,
        verification_note=(
            f"Full-text snapshot source: {source_ref.name} ({source_ref.url}); "
            f"normalized UTF-8 SHA-256 {source_hash}; parser verified contiguous article ordinals 1-{parsed_count}."
        ),
    )
