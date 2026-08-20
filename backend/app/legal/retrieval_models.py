from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator

RETRIEVAL_SCHEMA_VERSION = "1.0.0"
RETRIEVAL_ENGINE_VERSION = "stage7-1.0.0"


class RetrievalChannel(str, Enum):
    EXACT = "EXACT"
    LEXICAL = "LEXICAL"
    SEMANTIC = "SEMANTIC"


class RetrievalState(str, Enum):
    OK = "OK"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    INSUFFICIENT_CORPUS = "INSUFFICIENT_CORPUS"
    NO_APPLICABLE_VERSION = "NO_APPLICABLE_VERSION"
    VERSION_AMBIGUOUS = "VERSION_AMBIGUOUS"
    INDEX_NOT_READY = "INDEX_NOT_READY"


class RetrievalRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    as_of: date
    top_k: int = Field(default=8, ge=1, le=50)
    authority_id_hint: str | None = None
    authority_title_hint: str | None = None
    article_token_hint: str | None = None
    legal_evidence_id_hint: str | None = None
    use_semantic: bool = True
    authority_ids_allowlist: list[str] = Field(default_factory=list)

    @field_validator("authority_ids_allowlist")
    @classmethod
    def validate_authority_scope(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("authority_ids_allowlist may not contain blank Authority IDs.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("authority_ids_allowlist may not contain duplicate Authority IDs.")
        return normalized


class ChannelScore(BaseModel):
    channel: RetrievalChannel
    rank: int = Field(ge=1)
    raw_score: float | None = None
    contribution: float = Field(ge=0)


class RetrievalCandidate(BaseModel):
    legal_evidence_id: str
    authority_id: str
    authority_title: str
    version_id: str
    article_id: str
    article_token: str
    article_text: str
    coverage_type: str
    effective_date: date
    end_date_exclusive: date | None = None
    exact_hit: bool = False
    fused_score: float = Field(ge=0)
    channels: list[ChannelScore] = Field(default_factory=list)
    matched_snippet: str | None = None


class AuthorityResolutionNote(BaseModel):
    authority_id: str
    state: str
    version_id: str | None = None
    candidate_version_ids: list[str] = Field(default_factory=list)
    message: str


class RetrievalResponse(BaseModel):
    schema_version: str = RETRIEVAL_SCHEMA_VERSION
    engine_version: str = RETRIEVAL_ENGINE_VERSION
    query: str
    as_of: date
    state: RetrievalState
    channels_executed: list[RetrievalChannel] = Field(default_factory=list)
    candidates: list[RetrievalCandidate] = Field(default_factory=list)
    authority_resolution: list[AuthorityResolutionNote] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    semantic_provider: str | None = None
    semantic_model: str | None = None
    lexical_index_version: str | None = None


class RetrievalIndexSummary(BaseModel):
    ready: bool
    schema_version: str | None = None
    legal_source_fingerprint: str | None = None
    lexical_ready: bool = False
    lexical_tokenizer: str | None = None
    article_count: int = 0
    semantic_ready: bool = False
    semantic_provider: str | None = None
    semantic_model: str | None = None
    semantic_dimension: int | None = None


class RetrievalEvaluationCase(BaseModel):
    case_id: str
    query: str
    as_of: date
    expected_evidence_ids: list[str] = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    authority_id_hint: str | None = None
    article_token_hint: str | None = None


class RetrievalEvaluationReport(BaseModel):
    case_count: int
    recall_at_k: float
    mrr: float
    passed_cases: int
    case_results: list[dict]
