from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .benchmark_models import BenchmarkTaskType

EXPERT_BENCHMARK_SCHEMA_VERSION = "1.0.0"
EXPERT_BENCHMARK_EVALUATOR_VERSION = "stage16c-1.0.0"


class ExpertLabelStatus(str, Enum):
    AGREED = "AGREED"
    ADJUDICATED = "ADJUDICATED"
    AMBIGUOUS = "AMBIGUOUS"


class ExpertMetricType(str, Enum):
    BINARY_CLASSIFICATION = "BINARY_CLASSIFICATION"
    SET_EXTRACTION = "SET_EXTRACTION"


class ExpertCaseLabelAudit(BaseModel):
    case_id: str = Field(min_length=1, max_length=160)
    case_version: str = Field(min_length=1, max_length=40)
    status: ExpertLabelStatus
    reviewer_count: int = Field(ge=1, le=50)
    adjudicator_count: int = Field(default=0, ge=0, le=20)
    label_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_status_counts(self) -> "ExpertCaseLabelAudit":
        if self.status == ExpertLabelStatus.AGREED and self.adjudicator_count != 0:
            raise ValueError("AGREED label audit cannot record adjudicators; use ADJUDICATED instead.")
        if self.status == ExpertLabelStatus.ADJUDICATED and self.adjudicator_count < 1:
            raise ValueError("ADJUDICATED label audit requires at least one adjudicator.")
        return self


class ExpertLabelAuditArtifact(BaseModel):
    schema_version: str = EXPERT_BENCHMARK_SCHEMA_VERSION
    protocol_id: str = Field(min_length=1, max_length=160)
    protocol_version: str = Field(min_length=1, max_length=80)
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)
    cases: list[ExpertCaseLabelAudit] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_audit(self) -> "ExpertLabelAuditArtifact":
        if self.schema_version != EXPERT_BENCHMARK_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported expert audit schema_version {self.schema_version}; "
                f"expected {EXPERT_BENCHMARK_SCHEMA_VERSION}."
            )
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Expert label audit contains duplicate case_id values.")
        return self


class ExpertMetricDefinition(BaseModel):
    metric_id: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=300)
    metric_type: ExpertMetricType
    assertion_id: str = Field(min_length=1, max_length=160)
    scope: str = Field(min_length=1, max_length=2000)
    task_types: list[BenchmarkTaskType] = Field(default_factory=list)
    include_tags_all: list[str] = Field(default_factory=list, max_length=30)
    positive_values: list[Any] = Field(default_factory=list)
    negative_values: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_metric(self) -> "ExpertMetricDefinition":
        if self.metric_type == ExpertMetricType.BINARY_CLASSIFICATION:
            if not self.positive_values or not self.negative_values:
                raise ValueError(
                    "BINARY_CLASSIFICATION requires explicit non-empty positive_values and negative_values."
                )
            positive = {repr(value) for value in self.positive_values}
            negative = {repr(value) for value in self.negative_values}
            if positive & negative:
                raise ValueError("Binary positive_values and negative_values must be disjoint.")
        elif self.positive_values or self.negative_values:
            raise ValueError("positive_values/negative_values are valid only for BINARY_CLASSIFICATION.")
        return self


class ExpertBenchmarkProtocol(BaseModel):
    schema_version: str = EXPERT_BENCHMARK_SCHEMA_VERSION
    protocol_id: str = Field(min_length=1, max_length=160)
    protocol_version: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    scope: str = Field(min_length=1, max_length=3000)
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)
    dataset_path: str = Field(min_length=1, max_length=1000)
    observations_path: str = Field(min_length=1, max_length=1000)
    label_audit_path: str = Field(min_length=1, max_length=1000)
    minimum_reviewer_count: int = Field(default=2, ge=2, le=50)
    metrics: list[ExpertMetricDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_protocol(self) -> "ExpertBenchmarkProtocol":
        if self.schema_version != EXPERT_BENCHMARK_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported expert benchmark schema_version {self.schema_version}; "
                f"expected {EXPERT_BENCHMARK_SCHEMA_VERSION}."
            )
        metric_ids = [metric.metric_id for metric in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("Expert benchmark protocol contains duplicate metric_id values.")
        return self


class ExpertLabelQualitySummary(BaseModel):
    total_case_count: int = Field(ge=0)
    agreed_case_count: int = Field(ge=0)
    adjudicated_case_count: int = Field(ge=0)
    ambiguous_case_count: int = Field(ge=0)
    usable_case_count: int = Field(ge=0)
    minimum_reviewer_count_required: int = Field(ge=2)
    minimum_reviewer_count_observed: int = Field(ge=0)


class ExpertMetricResult(BaseModel):
    metric_id: str
    label: str
    metric_type: ExpertMetricType
    scope: str
    selected_case_count: int = Field(ge=0)
    usable_case_count: int = Field(ge=0)
    ambiguous_case_count: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    true_negative: int | None = Field(default=None, ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)


class ExpertBenchmarkRunReport(BaseModel):
    schema_version: str = EXPERT_BENCHMARK_SCHEMA_VERSION
    evaluator_version: str = EXPERT_BENCHMARK_EVALUATOR_VERSION
    protocol_id: str
    protocol_version: str
    dataset_id: str
    dataset_version: str
    label_quality: ExpertLabelQualitySummary
    metrics: list[ExpertMetricResult]
    source_fingerprints: dict[str, str]
    warnings: list[str] = Field(default_factory=list)
