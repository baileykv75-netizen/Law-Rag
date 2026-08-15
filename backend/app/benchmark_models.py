from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

BENCHMARK_SCHEMA_VERSION = "1.0.0"
BENCHMARK_EVALUATOR_VERSION = "stage11a-1.0.0"


class BenchmarkTaskType(str, Enum):
    OCR = "OCR"
    CANONICAL_STRUCTURE = "CANONICAL_STRUCTURE"
    DETERMINISTIC_RULE = "DETERMINISTIC_RULE"
    LEGAL_RETRIEVAL = "LEGAL_RETRIEVAL"
    LEGAL_CITATION_VALIDITY = "LEGAL_CITATION_VALIDITY"
    CONTRACT_EVIDENCE_LOCALIZATION = "CONTRACT_EVIDENCE_LOCALIZATION"
    PRIMARY_AUDIT_FINDING = "PRIMARY_AUDIT_FINDING"
    SECONDARY_REVIEW = "SECONDARY_REVIEW"
    HUMAN_REVIEW_INTEGRITY = "HUMAN_REVIEW_INTEGRITY"


class BenchmarkDataClass(str, Enum):
    PUBLIC_SYNTHETIC = "PUBLIC_SYNTHETIC"
    PUBLIC_LEGAL = "PUBLIC_LEGAL"
    PRIVATE_EXTERNAL = "PRIVATE_EXTERNAL"


class ComparisonMode(str, Enum):
    EXACT = "EXACT"
    ONE_OF = "ONE_OF"
    SET_EQUALS = "SET_EQUALS"
    SET_CONTAINS = "SET_CONTAINS"
    NUMERIC_WITHIN = "NUMERIC_WITHIN"
    NORMALIZED_TEXT_EQUALS = "NORMALIZED_TEXT_EQUALS"


class BenchmarkProvenance(BaseModel):
    data_class: BenchmarkDataClass
    source_name: str = Field(min_length=1, max_length=240)
    source_uri: str | None = Field(default=None, max_length=1000)
    scope: str = Field(min_length=1, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)


class BenchmarkExpectation(BaseModel):
    assertion_id: str = Field(min_length=1, max_length=160)
    pointer: str = Field(min_length=1, max_length=500)
    comparison: ComparisonMode
    expected: Any
    tolerance: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_comparison_configuration(self) -> "BenchmarkExpectation":
        if not self.pointer.startswith("/"):
            raise ValueError("Benchmark expectation pointer must be a JSON Pointer starting with '/'.")
        if self.comparison == ComparisonMode.NUMERIC_WITHIN and self.tolerance is None:
            raise ValueError("NUMERIC_WITHIN requires a non-negative tolerance.")
        if self.comparison != ComparisonMode.NUMERIC_WITHIN and self.tolerance is not None:
            raise ValueError("tolerance is only valid for NUMERIC_WITHIN.")
        if self.comparison == ComparisonMode.ONE_OF and not isinstance(self.expected, list):
            raise ValueError("ONE_OF expected value must be a list.")
        if self.comparison in {ComparisonMode.SET_EQUALS, ComparisonMode.SET_CONTAINS} and not isinstance(
            self.expected, list
        ):
            raise ValueError(f"{self.comparison.value} expected value must be a list.")
        return self


class BenchmarkCase(BaseModel):
    case_id: str = Field(min_length=1, max_length=160)
    case_version: str = Field(min_length=1, max_length=40)
    fixture_id: str = Field(min_length=1, max_length=240)
    task_type: BenchmarkTaskType
    title: str = Field(min_length=1, max_length=300)
    provenance: BenchmarkProvenance
    expectations: list[BenchmarkExpectation] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_unique_assertions(self) -> "BenchmarkCase":
        ids = [item.assertion_id for item in self.expectations]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate assertion_id in benchmark case {self.case_id}.")
        return self


class BenchmarkDataset(BaseModel):
    schema_version: str = BENCHMARK_SCHEMA_VERSION
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=3000)
    cases: list[BenchmarkCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> "BenchmarkDataset":
        if self.schema_version != BENCHMARK_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported benchmark schema_version {self.schema_version}; expected {BENCHMARK_SCHEMA_VERSION}."
            )
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Benchmark dataset contains duplicate case_id values.")
        return self


class BenchmarkProducer(BaseModel):
    producer_id: str = Field(min_length=1, max_length=160)
    producer_version: str = Field(min_length=1, max_length=80)
    provider: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=240)
    artifact_fingerprint: str | None = Field(default=None, max_length=256)


class BenchmarkObservation(BaseModel):
    case_id: str = Field(min_length=1, max_length=160)
    case_version: str = Field(min_length=1, max_length=40)
    observed: dict[str, Any] = Field(default_factory=dict)
    producer: BenchmarkProducer


class BenchmarkObservationSet(BaseModel):
    schema_version: str = BENCHMARK_SCHEMA_VERSION
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=40)
    observations: list[BenchmarkObservation]

    @model_validator(mode="after")
    def validate_observations(self) -> "BenchmarkObservationSet":
        if self.schema_version != BENCHMARK_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported observation schema_version {self.schema_version}; expected {BENCHMARK_SCHEMA_VERSION}."
            )
        case_ids = [item.case_id for item in self.observations]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Observation set contains duplicate case_id values.")
        return self


class BenchmarkAssertionResult(BaseModel):
    assertion_id: str
    pointer: str
    comparison: ComparisonMode
    passed: bool
    expected: Any
    observed: Any = None
    reason: str


class BenchmarkCaseResult(BaseModel):
    case_id: str
    case_version: str
    task_type: BenchmarkTaskType
    passed: bool
    producer: BenchmarkProducer | None = None
    assertions: list[BenchmarkAssertionResult] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)


class BenchmarkTaskSummary(BaseModel):
    task_type: BenchmarkTaskType
    case_count: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)


class BenchmarkRunReport(BaseModel):
    schema_version: str = BENCHMARK_SCHEMA_VERSION
    evaluator_version: str = BENCHMARK_EVALUATOR_VERSION
    dataset_id: str
    dataset_version: str
    case_count: int = Field(ge=0)
    all_cases_passed: bool
    task_summaries: list[BenchmarkTaskSummary]
    case_results: list[BenchmarkCaseResult]
    warnings: list[str] = Field(default_factory=list)
