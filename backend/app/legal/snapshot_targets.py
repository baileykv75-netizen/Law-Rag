from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator, model_validator

from .corpus_inventory import CatalogEntryState, OfficialCorpusCatalog
from .models import SourceRole
from .source_registry import LegalSourceRegistry, LegalSourceRegistryError, validate_official_source_ref

SNAPSHOT_TARGETS_SCHEMA_VERSION = "1.0.0"


class SnapshotTargetsError(RuntimeError):
    pass


class FullTextSnapshotTarget(BaseModel):
    authority_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    version_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,127}$")
    snapshot_source_url: HttpUrl
    expected_article_count: int = Field(ge=1)
    verification_note: str = Field(min_length=1)


class FullTextSnapshotTargetSet(BaseModel):
    snapshot_targets_schema_version: str = SNAPSHOT_TARGETS_SCHEMA_VERSION
    target_set_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    pack_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    verified_on: date
    targets: list[FullTextSnapshotTarget] = Field(min_length=1)

    @field_validator("snapshot_targets_schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != SNAPSHOT_TARGETS_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported snapshot-target schema {value}; expected {SNAPSHOT_TARGETS_SCHEMA_VERSION}."
            )
        return value

    @model_validator(mode="after")
    def validate_unique_identities(self) -> "FullTextSnapshotTargetSet":
        identities = [(item.authority_id, item.version_id) for item in self.targets]
        duplicates = sorted({identity for identity in identities if identities.count(identity) > 1})
        if duplicates:
            raise ValueError(f"Duplicate snapshot target identities: {duplicates}")
        return self


def _normalize_url(value: str) -> str:
    return value.rstrip("/")


def load_snapshot_targets(
    path: Path,
    *,
    catalog: OfficialCorpusCatalog,
    registry: LegalSourceRegistry,
) -> FullTextSnapshotTargetSet:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SnapshotTargetsError(f"Unable to read snapshot targets {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SnapshotTargetsError(f"Malformed JSON in snapshot targets {path}: {exc}") from exc
    try:
        targets = FullTextSnapshotTargetSet.model_validate(payload)
    except ValidationError as exc:
        raise SnapshotTargetsError(f"Malformed snapshot targets {path}: {exc}") from exc

    catalog_by_identity = {
        (entry.authority.authority_id, entry.version_id): entry for entry in catalog.entries
    }
    expected_identities = {
        (entry.authority.authority_id, entry.version_id)
        for entry in catalog.entries
        if targets.pack_id in entry.pack_ids and entry.catalog_state != CatalogEntryState.BLOCKED
    }
    actual_identities = {(item.authority_id, item.version_id) for item in targets.targets}
    if actual_identities != expected_identities:
        missing = sorted(expected_identities - actual_identities)
        extra = sorted(actual_identities - expected_identities)
        raise SnapshotTargetsError(
            f"Snapshot target set must cover exactly the non-blocked catalog entries for {targets.pack_id}; "
            f"missing={missing}, extra={extra}"
        )

    for target in targets.targets:
        identity = (target.authority_id, target.version_id)
        entry = catalog_by_identity[identity]
        source_url = _normalize_url(str(target.snapshot_source_url))
        matching_refs = [
            ref for ref in entry.source_refs if _normalize_url(str(ref.url)) == source_url
        ]
        if len(matching_refs) != 1:
            raise SnapshotTargetsError(
                f"Snapshot source for {target.authority_id}:{target.version_id} must match exactly one catalog source_ref"
            )
        source_ref = matching_refs[0]
        if source_ref.role not in {SourceRole.PRIMARY, SourceRole.TEXT}:
            raise SnapshotTargetsError(
                f"Snapshot source for {target.authority_id}:{target.version_id} has role {source_ref.role.value}; "
                "FULL_TEXT freezing requires PRIMARY or TEXT"
            )
        try:
            validate_official_source_ref(source_ref, registry)
        except LegalSourceRegistryError as exc:
            raise SnapshotTargetsError(
                f"Snapshot source for {target.authority_id}:{target.version_id} fails registry policy: {exc}"
            ) from exc

    return targets
