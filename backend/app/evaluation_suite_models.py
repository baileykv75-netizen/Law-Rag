from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

EVALUATION_SUITE_SCHEMA_VERSION = "1.0.0"
EVALUATION_SUITE_EVALUATOR_VERSION = "stage16d-1.0.0"


class EvaluationSuiteClass(str, Enum):
    PUBLIC_REGRESSION = "PUBLIC_REGRESSION"
    PRIVATE_EXPERT = "PRIVATE_EXPERT"
    REAL_PROVIDER_UAT = "REAL_PROVIDER_UAT"


class EvaluationSuiteEntryKind(str, Enum):
    BENCHMARK = "BENCHMARK"
    PUBLIC_QUALITY_PROFILE = "PUBLIC_QUALITY_PROFILE"
    PUBLIC_REGRESSION_PROFILE = "PUBLIC_REGRESSION_PROFILE"
    UAT_CAPTURE = "UAT_CAPTURE"


class EvaluationSuiteEntry(BaseModel):
    entry_id: str = Field(min_length=1, max_length=160)
    kind: EvaluationSuiteEntryKind
    scope: str = Field(min_length=1, max_length=2000)
    dataset_path: str | None = Field(default=None, min_length=1, max_length=1000)
    observations_path: str | None = Field(default=None, min_length=1, max_length=1000)
    quality_profile_path: str | None = Field(default=None, min_length=1, max_length=1000)
    public_regression_profile_path: str | None = Field(default=None, min_length=1, max_length=1000)
    uat_observation_path: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_kind_paths(self) -> "EvaluationSuiteEntry":
        if self.kind == EvaluationSuiteEntryKind.BENCHMARK:
            if not self.dataset_path or not self.observations_path:
                raise ValueError("BENCHMARK entries require dataset_path and observations_path.")
            if (
                self.quality_profile_path is not None
                or self.public_regression_profile_path is not None
                or self.uat_observation_path is not None
            ):
                raise ValueError("BENCHMARK entries cannot define profile or UAT-capture paths.")
        elif self.kind == EvaluationSuiteEntryKind.PUBLIC_QUALITY_PROFILE:
            if not self.quality_profile_path:
                raise ValueError("PUBLIC_QUALITY_PROFILE entries require quality_profile_path.")
            if (
                self.dataset_path is not None
                or self.observations_path is not None
                or self.public_regression_profile_path is not None
                or self.uat_observation_path is not None
            ):
                raise ValueError("PUBLIC_QUALITY_PROFILE entries cannot define benchmark, regression or UAT paths.")
        elif self.kind == EvaluationSuiteEntryKind.PUBLIC_REGRESSION_PROFILE:
            if not self.public_regression_profile_path:
                raise ValueError(
                    "PUBLIC_REGRESSION_PROFILE entries require public_regression_profile_path."
                )
            if (
                self.dataset_path is not None
                or self.observations_path is not None
                or self.quality_profile_path is not None
                or self.uat_observation_path is not None
            ):
                raise ValueError("PUBLIC_REGRESSION_PROFILE entries cannot define benchmark/quality/UAT paths.")
        elif self.kind == EvaluationSuiteEntryKind.UAT_CAPTURE:
            if not self.uat_observation_path:
                raise ValueError("UAT_CAPTURE entries require uat_observation_path.")
            if (
                self.dataset_path is not None
                or self.observations_path is not None
                or self.quality_profile_path is not None
                or self.public_regression_profile_path is not None
            ):
                raise ValueError("UAT_CAPTURE entries cannot define benchmark or public-profile paths.")
        return self


class EvaluationSuiteManifest(BaseModel):
    schema_version: str = EVALUATION_SUITE_SCHEMA_VERSION
    suite_id: str = Field(min_length=1, max_length=160)
    suite_version: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=3000)
    suite_class: EvaluationSuiteClass
    entries: list[EvaluationSuiteEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "EvaluationSuiteManifest":
        if self.schema_version != EVALUATION_SUITE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported evaluation suite schema_version {self.schema_version}; "
                f"expected {EVALUATION_SUITE_SCHEMA_VERSION}."
            )
        entry_ids = [entry.entry_id for entry in self.entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("Evaluation suite contains duplicate entry_id values.")
        if self.suite_class != EvaluationSuiteClass.PUBLIC_REGRESSION and any(
            entry.kind
            in {
                EvaluationSuiteEntryKind.PUBLIC_QUALITY_PROFILE,
                EvaluationSuiteEntryKind.PUBLIC_REGRESSION_PROFILE,
            }
            for entry in self.entries
        ):
            raise ValueError(
                "Public quality/regression profile entries are valid only in PUBLIC_REGRESSION suites."
            )
        if self.suite_class != EvaluationSuiteClass.REAL_PROVIDER_UAT and any(
            entry.kind == EvaluationSuiteEntryKind.UAT_CAPTURE for entry in self.entries
        ):
            raise ValueError("UAT_CAPTURE entries are valid only in REAL_PROVIDER_UAT suites.")
        return self


class EvaluationProducerSummary(BaseModel):
    provider: str
    model: str
    artifact_fingerprint: str


class EvaluationSuiteEntryResult(BaseModel):
    entry_id: str
    kind: EvaluationSuiteEntryKind
    passed: bool
    evaluator_version: str
    identity_id: str
    identity_version: str
    unit_label: str
    unit_count: int = Field(ge=0)
    passed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    source_fingerprints: dict[str, str] = Field(default_factory=dict)
    producers: list[EvaluationProducerSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvaluationSuiteRunReport(BaseModel):
    schema_version: str = EVALUATION_SUITE_SCHEMA_VERSION
    evaluator_version: str = EVALUATION_SUITE_EVALUATOR_VERSION
    suite_id: str
    suite_version: str
    suite_class: EvaluationSuiteClass
    manifest_fingerprint: str
    all_entries_passed: bool
    entries: list[EvaluationSuiteEntryResult]
    warnings: list[str] = Field(default_factory=list)
