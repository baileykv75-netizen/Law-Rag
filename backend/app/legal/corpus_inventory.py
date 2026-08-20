from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from .corpus_packs import discover_corpus_packs
from .models import CoverageType, LegalAuthority, OfficialSourceRef, SourceRole, VersionStatus
from .source_registry import LegalSourceRegistry, LegalSourceRegistryError, validate_official_source_ref

OFFICIAL_CORPUS_CATALOG_SCHEMA_VERSION = "1.0.0"


class OfficialCorpusCatalogError(RuntimeError):
    pass


class CatalogEntryState(str, Enum):
    VETTED_FOR_SNAPSHOT = "VETTED_FOR_SNAPSHOT"
    PROMULGATED_NOT_YET_EFFECTIVE = "PROMULGATED_NOT_YET_EFFECTIVE"
    BLOCKED = "BLOCKED"


class CatalogPriority(str, Enum):
    CORE = "CORE"
    SECONDARY_CORE = "SECONDARY_CORE"


class PlannedLegalVersion(BaseModel):
    authority: LegalAuthority
    version_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,127}$")
    status: VersionStatus
    publication_date: date
    effective_date: date
    end_date_exclusive: date | None = None
    pack_ids: list[str] = Field(min_length=1)
    source_refs: list[OfficialSourceRef] = Field(min_length=1)
    target_coverage: CoverageType = CoverageType.FULL_TEXT
    catalog_state: CatalogEntryState
    priority: CatalogPriority = CatalogPriority.CORE
    notes: str = Field(min_length=1)
    blocking_issue: str | None = None

    @field_validator("pack_ids")
    @classmethod
    def validate_pack_ids(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("pack_ids must not contain duplicates")
        return values

    @model_validator(mode="after")
    def validate_state(self) -> "PlannedLegalVersion":
        if self.end_date_exclusive is not None and self.end_date_exclusive <= self.effective_date:
            raise ValueError("end_date_exclusive must be later than effective_date")
        if self.catalog_state == CatalogEntryState.BLOCKED:
            if not self.blocking_issue:
                raise ValueError("BLOCKED catalog entries require blocking_issue")
        elif self.blocking_issue:
            raise ValueError("Only BLOCKED catalog entries may set blocking_issue")
        if self.catalog_state == CatalogEntryState.PROMULGATED_NOT_YET_EFFECTIVE:
            if self.status != VersionStatus.NOT_YET_EFFECTIVE:
                raise ValueError("PROMULGATED_NOT_YET_EFFECTIVE requires NOT_YET_EFFECTIVE status")
        elif self.status == VersionStatus.NOT_YET_EFFECTIVE:
            raise ValueError("NOT_YET_EFFECTIVE status requires PROMULGATED_NOT_YET_EFFECTIVE catalog state")
        if not any(ref.role == SourceRole.PRIMARY for ref in self.source_refs):
            raise ValueError("Each planned legal version requires at least one PRIMARY official source reference")
        return self


class OfficialCorpusCatalog(BaseModel):
    catalog_schema_version: str = OFFICIAL_CORPUS_CATALOG_SCHEMA_VERSION
    catalog_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    verified_on: date
    description: str = Field(min_length=1)
    entries: list[PlannedLegalVersion] = Field(min_length=1)

    @field_validator("catalog_schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != OFFICIAL_CORPUS_CATALOG_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported official corpus catalog schema {value}; expected {OFFICIAL_CORPUS_CATALOG_SCHEMA_VERSION}."
            )
        return value

    @model_validator(mode="after")
    def validate_versions(self) -> "OfficialCorpusCatalog":
        identities: set[tuple[str, str]] = set()
        by_authority: dict[str, list[PlannedLegalVersion]] = defaultdict(list)
        for entry in self.entries:
            identity = (entry.authority.authority_id, entry.version_id)
            if identity in identities:
                raise ValueError(f"Duplicate authority/version identity: {identity[0]}:{identity[1]}")
            identities.add(identity)
            by_authority[entry.authority.authority_id].append(entry)
            if entry.catalog_state == CatalogEntryState.PROMULGATED_NOT_YET_EFFECTIVE:
                if entry.effective_date <= self.verified_on:
                    raise ValueError(
                        f"Future catalog entry {identity[0]}:{identity[1]} is already effective on verified_on"
                    )
        for authority_id, versions in by_authority.items():
            active = sorted(
                (item for item in versions if item.catalog_state != CatalogEntryState.BLOCKED),
                key=lambda item: item.effective_date,
            )
            for previous, current in zip(active, active[1:]):
                if previous.end_date_exclusive is None:
                    raise ValueError(
                        f"Authority {authority_id} has multiple planned versions but {previous.version_id} has no end_date_exclusive"
                    )
                if previous.end_date_exclusive > current.effective_date:
                    raise ValueError(f"Authority {authority_id} has overlapping planned version intervals")
        return self


def load_official_corpus_catalog(
    path: Path,
    *,
    registry: LegalSourceRegistry,
    corpus_root: Path,
) -> OfficialCorpusCatalog:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OfficialCorpusCatalogError(f"Unable to read official corpus catalog {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OfficialCorpusCatalogError(f"Malformed JSON in official corpus catalog {path}: {exc}") from exc
    try:
        catalog = OfficialCorpusCatalog.model_validate(payload)
    except ValidationError as exc:
        raise OfficialCorpusCatalogError(f"Malformed official corpus catalog {path}: {exc}") from exc

    known_pack_ids = {pack.manifest.pack_id for pack in discover_corpus_packs(corpus_root)}
    for entry in catalog.entries:
        unknown = sorted(set(entry.pack_ids) - known_pack_ids)
        if unknown:
            raise OfficialCorpusCatalogError(
                f"Catalog entry {entry.authority.authority_id}:{entry.version_id} references unknown packs: {unknown}"
            )
        for ref in entry.source_refs:
            try:
                validate_official_source_ref(ref, registry)
            except LegalSourceRegistryError as exc:
                raise OfficialCorpusCatalogError(
                    f"Catalog entry {entry.authority.authority_id}:{entry.version_id} has invalid source reference: {exc}"
                ) from exc
    return catalog
