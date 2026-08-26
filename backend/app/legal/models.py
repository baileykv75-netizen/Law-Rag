from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

LEGAL_SCHEMA_VERSION = "1.0.0"
LEGAL_IMPORTER_VERSION = "stage6-1.0.0"


class AuthorityType(str, Enum):
    LAW = "LAW"
    ADMINISTRATIVE_REGULATION = "ADMINISTRATIVE_REGULATION"
    JUDICIAL_INTERPRETATION = "JUDICIAL_INTERPRETATION"


class VersionStatus(str, Enum):
    NOT_YET_EFFECTIVE = "NOT_YET_EFFECTIVE"
    EFFECTIVE = "EFFECTIVE"
    SUPERSEDED = "SUPERSEDED"
    AMENDED = "AMENDED"
    REPEALED = "REPEALED"
    UNKNOWN = "UNKNOWN"


class CoverageType(str, Enum):
    FULL_TEXT = "FULL_TEXT"
    CURATED_EXCERPT = "CURATED_EXCERPT"


class ImportState(str, Enum):
    IMPORTED = "IMPORTED"
    REJECTED = "REJECTED"
    NO_CHANGE = "NO_CHANGE"


class VersionResolutionState(str, Enum):
    RESOLVED = "RESOLVED"
    NO_APPLICABLE_VERSION = "NO_APPLICABLE_VERSION"
    AMBIGUOUS = "AMBIGUOUS"


class SourceRole(str, Enum):
    PRIMARY = "PRIMARY"
    TEXT = "TEXT"
    METADATA = "METADATA"
    CROSS_CHECK = "CROSS_CHECK"


class OfficialSourceRef(BaseModel):
    name: str
    url: HttpUrl
    role: SourceRole


class LegalAuthority(BaseModel):
    authority_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,127}$")
    title: str = Field(min_length=1)
    authority_type: AuthorityType
    issuing_body: str = Field(min_length=1)
    document_number: str | None = None
    jurisdiction: str = "中华人民共和国"


class LegalVersion(BaseModel):
    authority_id: str
    version_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,127}$")
    status: VersionStatus
    publication_date: date | None = None
    effective_date: date
    end_date_exclusive: date | None = None
    repeal_date: date | None = None
    supersedes_version_id: str | None = None
    superseded_by_version_id: str | None = None
    coverage_type: CoverageType
    coverage_note: str | None = None
    source_refs: list[OfficialSourceRef] = Field(min_length=1)
    source_snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    importer_version: str = LEGAL_IMPORTER_VERSION
    schema_version: str = LEGAL_SCHEMA_VERSION
    verified_on: date | None = None
    verification_note: str | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> "LegalVersion":
        if self.end_date_exclusive is not None and self.end_date_exclusive <= self.effective_date:
            raise ValueError("end_date_exclusive must be later than effective_date")
        if self.repeal_date is not None and self.repeal_date < self.effective_date:
            raise ValueError("repeal_date cannot precede effective_date")
        return self


class LegalArticle(BaseModel):
    authority_id: str
    version_id: str
    article_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,127}$")
    article_token: str = Field(min_length=2)
    article_ordinal: int | None = Field(default=None, ge=1)
    text: str = Field(min_length=1)
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    legal_evidence_id: str = Field(min_length=5)
    heading_context: list[str] = Field(default_factory=list)


class LegalImportRecord(BaseModel):
    authority: LegalAuthority
    version: LegalVersion
    articles: list[LegalArticle]
    preamble_text: str | None = None


class ManifestRecord(BaseModel):
    authority: LegalAuthority
    version_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,127}$")
    status: VersionStatus
    publication_date: date | None = None
    effective_date: date
    end_date_exclusive: date | None = None
    repeal_date: date | None = None
    supersedes_version_id: str | None = None
    superseded_by_version_id: str | None = None
    coverage_type: CoverageType
    coverage_note: str | None = None
    source_refs: list[OfficialSourceRef] = Field(min_length=1)
    snapshot_path: str = Field(min_length=1)
    expected_source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_article_count: int = Field(ge=1)
    parser: Literal["chinese-articles-v1"] = "chinese-articles-v1"
    inclusion_reason: str = Field(min_length=1)
    verified_on: date | None = None
    verification_note: str | None = None


class LegalManifest(BaseModel):
    manifest_version: str = "1.0.0"
    records: list[ManifestRecord] = Field(min_length=1)


class ValidationIssue(BaseModel):
    code: str
    message: str
    critical: bool = False


class ImportValidationReport(BaseModel):
    authority_id: str
    version_id: str
    source_recognized: bool
    source_sha256: str
    expected_source_sha256: str
    metadata_complete: bool
    parsed_article_count: int = Field(ge=0)
    expected_article_count: int = Field(ge=0)
    duplicate_article_tokens: list[str] = Field(default_factory=list)
    empty_article_tokens: list[str] = Field(default_factory=list)
    interval_conflicts: list[str] = Field(default_factory=list)
    identity_conflicts: list[str] = Field(default_factory=list)
    state: ImportState
    issues: list[ValidationIssue] = Field(default_factory=list)


class ManifestImportReport(BaseModel):
    schema_version: str = LEGAL_SCHEMA_VERSION
    importer_version: str = LEGAL_IMPORTER_VERSION
    manifest_path: str
    database_path: str
    imported_records: int = Field(ge=0)
    rejected_records: int = Field(ge=0)
    no_change_records: int = Field(ge=0)
    reports: list[ImportValidationReport]


class LegalStoreSummary(BaseModel):
    ready: bool
    schema_version: str | None = None
    authority_count: int = Field(default=0, ge=0)
    version_count: int = Field(default=0, ge=0)
    article_count: int = Field(default=0, ge=0)
    effective_version_count: int = Field(default=0, ge=0)
    excerpt_version_count: int = Field(default=0, ge=0)


class AuthoritySummary(BaseModel):
    authority: LegalAuthority
    versions: list[LegalVersion]
    article_count: int = Field(ge=0)


class LegalEvidenceRecord(BaseModel):
    authority: LegalAuthority
    version: LegalVersion
    article: LegalArticle


class LegalArticleBrowserItem(BaseModel):
    authority: LegalAuthority
    version: LegalVersion
    article: LegalArticle


class VersionResolution(BaseModel):
    authority_id: str
    as_of: date
    state: VersionResolutionState
    version: LegalVersion | None = None
    candidate_version_ids: list[str] = Field(default_factory=list)
    message: str


class ArticleVersionResolution(BaseModel):
    resolution: VersionResolution
    article: LegalArticle | None = None
