from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

QUALITY_SCHEMA_VERSION = "1.0.0"
QUALITY_EVALUATOR_VERSION = "stage11b-1.0.0"


class GateOperator(str, Enum):
    GTE = "GTE"
    LTE = "LTE"
    EQ = "EQ"


class QualityMetric(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=300)
    value: float
    numerator: float | None = None
    denominator: float | None = None
    dataset_id: str = Field(min_length=1, max_length=200)
    dataset_version: str = Field(min_length=1, max_length=80)
    scope: str = Field(min_length=1, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)


class QualityDiagnostic(BaseModel):
    layer: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=2000)
    case_id: str | None = Field(default=None, max_length=200)
    expected: Any = None
    observed: Any = None


class QualityGateDefinition(BaseModel):
    gate_id: str = Field(min_length=1, max_length=160)
    metric_key: str = Field(min_length=1, max_length=200)
    operator: GateOperator
    threshold: float
    rationale: str = Field(min_length=1, max_length=2000)


class QualityGateProfile(BaseModel):
    schema_version: str = QUALITY_SCHEMA_VERSION
    profile_id: str = Field(min_length=1, max_length=160)
    profile_version: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    scope: str = Field(min_length=1, max_length=3000)
    gates: list[QualityGateDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profile(self) -> "QualityGateProfile":
        if self.schema_version != QUALITY_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported quality schema_version {self.schema_version}; expected {QUALITY_SCHEMA_VERSION}."
            )
        gate_ids = [gate.gate_id for gate in self.gates]
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("Quality gate profile contains duplicate gate_id values.")
        metric_keys = [gate.metric_key for gate in self.gates]
        if len(metric_keys) != len(set(metric_keys)):
            raise ValueError("Quality gate profile contains duplicate metric_key values.")
        return self


class QualityGateResult(BaseModel):
    gate_id: str
    metric_key: str
    operator: GateOperator
    threshold: float
    observed: float | None = None
    passed: bool
    reason: str


class BinaryClassificationMetrics(BaseModel):
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    true_negative: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)


class SetExtractionMetrics(BaseModel):
    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)


class RankingMetrics(BaseModel):
    case_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    recall_at_k: float = Field(ge=0, le=1)
    mrr: float = Field(ge=0, le=1)
    exact_case_count: int = Field(ge=0)
    exact_hit_count: int = Field(ge=0)
    exact_citation_hit_rate: float = Field(ge=0, le=1)


class QualityRunReport(BaseModel):
    schema_version: str = QUALITY_SCHEMA_VERSION
    evaluator_version: str = QUALITY_EVALUATOR_VERSION
    profile_id: str
    profile_version: str
    all_gates_passed: bool
    metrics: list[QualityMetric]
    gates: list[QualityGateResult]
    diagnostics: list[QualityDiagnostic] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
