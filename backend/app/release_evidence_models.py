from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

RELEASE_EVIDENCE_SCHEMA_VERSION = "1.0.0"
RELEASE_EVIDENCE_EVALUATOR_VERSION = "stage16e-1.0.0"


class ReleaseEvidenceClass(str, Enum):
    PUBLIC_REGRESSION = "PUBLIC_REGRESSION"
    PRIVATE_EXPERT = "PRIVATE_EXPERT"
    REAL_PROVIDER_UAT = "REAL_PROVIDER_UAT"


class ReleaseEvidenceStatus(str, Enum):
    PASS = "PASS"
    PRESENT = "PRESENT"
    PENDING = "PENDING"
    FAIL = "FAIL"


class ReleaseEvidenceItem(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    evidence_class: ReleaseEvidenceClass
    status: ReleaseEvidenceStatus
    required_for_stage16_evidence_complete: bool = True
    source_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    summary: str = Field(min_length=1, max_length=2000)
    warnings: list[str] = Field(default_factory=list)


class Stage16ReleaseEvidenceMatrix(BaseModel):
    schema_version: str = RELEASE_EVIDENCE_SCHEMA_VERSION
    evaluator_version: str = RELEASE_EVIDENCE_EVALUATOR_VERSION
    engineering_ready: bool
    stage16_evidence_complete: bool
    pending_evidence_classes: list[ReleaseEvidenceClass] = Field(default_factory=list)
    evidence: list[ReleaseEvidenceItem]
    warnings: list[str] = Field(default_factory=list)
