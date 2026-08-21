from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .quality_models import QualityGateDefinition

PUBLIC_REGRESSION_SCHEMA_VERSION = "1.0.0"
PUBLIC_REGRESSION_EVALUATOR_VERSION = "stage16b-1.0.0"


class PublicRegressionRunner(str, Enum):
    THREE_DOMAIN_RETRIEVAL = "THREE_DOMAIN_RETRIEVAL"


class ThreeDomainRetrievalCase(BaseModel):
    case_id: str = Field(min_length=1, max_length=160)
    topic: str = Field(min_length=1, max_length=300)
    query: str = Field(min_length=1, max_length=1000)
    contract_type: str = Field(min_length=1, max_length=80)
    as_of: date
    expected_authority_id: str = Field(min_length=1, max_length=200)


class ThreeDomainRetrievalDataset(BaseModel):
    schema_version: str = PUBLIC_REGRESSION_SCHEMA_VERSION
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    scope: str = Field(min_length=1, max_length=3000)
    source_fixture_path: str = Field(min_length=1, max_length=1000)
    cases: list[ThreeDomainRetrievalCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> "ThreeDomainRetrievalDataset":
        if self.schema_version != PUBLIC_REGRESSION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported three-domain dataset schema_version {self.schema_version}; "
                f"expected {PUBLIC_REGRESSION_SCHEMA_VERSION}."
            )
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Three-domain regression dataset contains duplicate case_id values.")
        normalized = self.source_fixture_path.replace("\\", "/")
        if normalized.startswith("/") or "../" in f"/{normalized}":
            raise ValueError("source_fixture_path must be repository-relative and traversal-free.")
        return self


class PublicRegressionProfile(BaseModel):
    schema_version: str = PUBLIC_REGRESSION_SCHEMA_VERSION
    profile_id: str = Field(min_length=1, max_length=160)
    profile_version: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    scope: str = Field(min_length=1, max_length=3000)
    runner: PublicRegressionRunner
    benchmark_path: str = Field(min_length=1, max_length=1000)
    corpus_release_path: str = Field(min_length=1, max_length=1000)
    gates: list[QualityGateDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profile(self) -> "PublicRegressionProfile":
        if self.schema_version != PUBLIC_REGRESSION_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported public regression schema_version {self.schema_version}; "
                f"expected {PUBLIC_REGRESSION_SCHEMA_VERSION}."
            )
        gate_ids = [gate.gate_id for gate in self.gates]
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("Public regression profile contains duplicate gate_id values.")
        metric_keys = [gate.metric_key for gate in self.gates]
        if len(metric_keys) != len(set(metric_keys)):
            raise ValueError("Public regression profile contains duplicate metric_key values.")
        for configured in (self.benchmark_path, self.corpus_release_path):
            normalized = configured.replace("\\", "/")
            if normalized.startswith("/") or "../" in f"/{normalized}":
                raise ValueError("Public regression input paths must be repository-relative and traversal-free.")
        return self
