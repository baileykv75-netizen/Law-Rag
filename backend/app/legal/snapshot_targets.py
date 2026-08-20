from __future__ import annotations

import json
from datetime import date
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl, ValidationError, field_validator, model_validator

from .corpus_inventory import CatalogEntryState, OfficialCorpusCatalog
from .models import OfficialSourceRef, SourceRole
from .source_registry import LegalSourceRegistry, LegalSourceRegistryError, validate_official_source_ref

SNAPSHOT_TARGETS_SCHEMA_VERSION = "1.0.0"


class SnapshotTargetsError(RuntimeError):
    pass


class SnapshotTargetState(str, Enum):
    READY_FOR_FREEZE = "READY_FOR_FREEZE"
    SOURCE_UNRESOLVED = "SOURCE_UNRESOLVED"
    SOURCE_POLICY_BLOCKED = "SOURCE_POLICY_BLOCKED"


class FullTextSnapshotTarget(BaseModel):
    authority_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    version_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,127}$")
    state: SnapshotTargetState
    snapshot_source_url: HttpUrl | None = None
    supplemental_source_ref: OfficialSourceRef | None = None
    expected_article_count: int | None = Field(default=None, ge=1)
    verification_note: str = Field(min_length=1)
    blocking_issue: str | None = None

    @model_validator(mode="after")
    def validate_state(self) -> "FullTextSnapshotTarget":
        if self.state == SnapshotTargetState.READY_FOR_FREEZE:
            if self.snapshot_source_url is None or self.expected_article_count is None:
                raise ValueError("READY_FOR_FREEZE requires snapshot_source_url and expected_article_count")
            if self.blocking_issue:
                raise ValueError("READY_FOR_FREEZE must not set blocking_issue")
        else:
            if self.snapshot_source_url is not None or self.supplemental_source_ref is not None:
                raise ValueError("Non-ready snapshot targets must not pin a source as if freezing were approved")
            if not self.blocking_issue:
                raise ValueError("Non-ready snapshot targets require blocking_issue")
        return self


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
        if target.state != SnapshotTargetState.READY_FOR_FREEZE:
            continue
        identity = (target.authority_id, target.version_id)
        entry = catalog_by_identity[identity]
        source_url = _normalize_url(str(target.snapshot_source_url))
        matching_refs = [
            ref for ref in entry.source_refs if _normalize_url(str(ref.url)) == source_url
        ]

        if len(matching_refs) > 1:
            raise SnapshotTargetsError(
                f"Snapshot source for {target.authority_id}:{target.version_id} matches duplicate catalog source_refs"
            )
        if matching_refs:
            if target.supplemental_source_ref is not None:
                raise SnapshotTargetsError(
                    f"Snapshot source for {target.authority_id}:{target.version_id} is already in the catalog and must not be supplemented"
                )
            source_ref = matching_refs[0]
        else:
            source_ref = target.supplemental_source_ref
            if source_ref is None:
                raise SnapshotTargetsError(
                    f"Snapshot source for {target.authority_id}:{target.version_id} must match a catalog source_ref "
                    "or declare one supplemental TEXT source_ref"
                )
            if _normalize_url(str(source_ref.url)) != source_url:
                raise SnapshotTargetsError(
                    f"Supplemental source URL for {target.authority_id}:{target.version_id} must equal snapshot_source_url"
                )
            if source_ref.role != SourceRole.TEXT:
                raise SnapshotTargetsError(
                    f"Supplemental source for {target.authority_id}:{target.version_id} must use TEXT role; "
                    "new PRIMARY provenance must be vetted in the catalog first"
                )

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
