from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from .ai_audit_models import AiAuditReport
from .audit_rule_models import AuditRuleReport
from .contract_models import CanonicalContract
from .models import OcrRunResult, PageEvidence
from .review_report import ReviewReport
from .secondary_review_models import SecondaryReviewReport
from .storage import legal_db_path, legal_retrieval_index_path, runtime_dir
from .workspace_models import (
    WorkspaceArtifactState,
    WorkspaceDocumentSummary,
    WorkspaceOverallState,
    WorkspaceReviewSummary,
    WorkspaceStageSummary,
    WorkspaceSummary,
)


class WorkspaceLoadError(RuntimeError):
    pass


_PAGE_EVIDENCE_ADAPTER = TypeAdapter(list[PageEvidence])


def _job_dir(job_id: UUID) -> Path:
    # Deliberately do not use job_output_dir(): a read-only workspace GET must
    # never create a phantom runtime directory for an unknown job.
    return runtime_dir() / "jobs" / str(job_id)


def _source_candidates(job_id: UUID) -> list[Path]:
    return sorted((runtime_dir() / "uploads" / str(job_id)).glob("source.*"))


def _stage(
    stage: str,
    label: str,
    state: WorkspaceArtifactState,
    artifact: str | None,
    detail: str,
) -> WorkspaceStageSummary:
    return WorkspaceStageSummary(
        stage=stage,
        label=label,
        state=state,
        artifact=artifact,
        detail=detail,
    )


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceLoadError(f"Invalid local artifact {path.name}: {exc}") from exc


def _model_from_file(path: Path, model_type):
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise WorkspaceLoadError(f"Invalid local artifact {path.name}: {exc}") from exc


def _validated_stage(
    *,
    stage: str,
    label: str,
    path: Path,
    model_type,
) -> tuple[WorkspaceStageSummary, object | None]:
    if not path.exists():
        return (
            _stage(stage, label, WorkspaceArtifactState.MISSING, path.name, f"{path.name} is not present."),
            None,
        )
    try:
        value = _model_from_file(path, model_type)
    except WorkspaceLoadError as exc:
        return (
            _stage(stage, label, WorkspaceArtifactState.INVALID, path.name, str(exc)),
            None,
        )
    return (
        _stage(stage, label, WorkspaceArtifactState.READY, path.name, f"Validated {path.name} is available locally."),
        value,
    )


def load_workspace_summary(job_id: UUID) -> WorkspaceSummary:
    job_dir = _job_dir(job_id)
    source_candidates = _source_candidates(job_id)
    artifact_names = (
        "document.json",
        "evidence.json",
        "ocr.json",
        "contract.json",
        "audit-rules.json",
        "ai-audit.json",
        "secondary-review.json",
        "review-report.json",
    )
    any_artifact = any((job_dir / name).exists() for name in artifact_names)
    if not source_candidates and not any_artifact:
        raise FileNotFoundError(f"No local Law-Rag job exists for {job_id}.")

    source_available = len(source_candidates) == 1
    warnings: list[str] = []
    source_uncertainty: list[str] = []
    stages: list[WorkspaceStageSummary] = []
    review = WorkspaceReviewSummary()

    document: WorkspaceDocumentSummary | None = None
    document_path = job_dir / "document.json"
    evidence_path = job_dir / "evidence.json"
    document_valid = False

    if not document_path.exists() or not evidence_path.exists():
        missing = []
        if not document_path.exists():
            missing.append("document.json")
        if not evidence_path.exists():
            missing.append("evidence.json")
        stages.append(
            _stage(
                "2",
                "Document ingestion",
                WorkspaceArtifactState.MISSING,
                "document.json + evidence.json",
                f"Missing Stage 2 artifact(s): {', '.join(missing)}.",
            )
        )
    else:
        try:
            raw_document = _read_json(document_path)
            if not isinstance(raw_document, dict):
                raise WorkspaceLoadError("Invalid local artifact document.json: expected an object.")
            document = WorkspaceDocumentSummary.model_validate(raw_document)
            raw_evidence = evidence_path.read_text(encoding="utf-8")
            _PAGE_EVIDENCE_ADAPTER.validate_json(raw_evidence)
            document_valid = True
            stages.append(
                _stage(
                    "2",
                    "Document ingestion",
                    WorkspaceArtifactState.READY,
                    "document.json + evidence.json",
                    "Document metadata and page evidence are valid local artifacts.",
                )
            )
        except (OSError, ValidationError, WorkspaceLoadError) as exc:
            stages.append(
                _stage(
                    "2",
                    "Document ingestion",
                    WorkspaceArtifactState.INVALID,
                    "document.json + evidence.json",
                    str(exc),
                )
            )
            warnings.append("Stage 2 document metadata/evidence could not be validated.")

    ocr_path = job_dir / "ocr.json"
    ocr_result: OcrRunResult | None = None
    if document_valid and document is not None and document.ocr_required_pages == 0:
        stages.append(
            _stage(
                "3",
                "OCR evidence",
                WorkspaceArtifactState.NOT_REQUIRED,
                None,
                "All pages used reliable native text; OCR was not required.",
            )
        )
    elif not ocr_path.exists():
        stages.append(
            _stage(
                "3",
                "OCR evidence",
                WorkspaceArtifactState.MISSING,
                "ocr.json",
                "OCR is required by the document route but ocr.json is not present."
                if document is not None
                else "OCR status cannot be confirmed because ocr.json is not present.",
            )
        )
    else:
        try:
            ocr_result = _model_from_file(ocr_path, OcrRunResult)
            stages.append(
                _stage(
                    "3",
                    "OCR evidence",
                    WorkspaceArtifactState.READY,
                    "ocr.json",
                    f"OCR attempted {ocr_result.ocr_pages_attempted} page(s); {ocr_result.low_confidence_pages} low-confidence page(s).",
                )
            )
            if document is not None:
                document.ocr_used = ocr_result.ocr_pages_attempted > 0
                document.low_confidence_ocr_pages = ocr_result.low_confidence_pages
                document.failed_ocr_pages = ocr_result.failed_pages
                document.no_text_ocr_pages = ocr_result.no_text_pages
            if ocr_result.low_confidence_pages:
                source_uncertainty.append(f"{ocr_result.low_confidence_pages} OCR page(s) are low confidence.")
            if ocr_result.failed_pages:
                source_uncertainty.append(f"{ocr_result.failed_pages} OCR page(s) failed.")
            if ocr_result.no_text_pages:
                source_uncertainty.append(f"{ocr_result.no_text_pages} OCR page(s) returned no text.")
        except WorkspaceLoadError as exc:
            stages.append(_stage("3", "OCR evidence", WorkspaceArtifactState.INVALID, "ocr.json", str(exc)))
            warnings.append("Stage 3 OCR artifact could not be validated.")

    contract_stage, _ = _validated_stage(
        stage="4",
        label="Canonical contract",
        path=job_dir / "contract.json",
        model_type=CanonicalContract,
    )
    stages.append(contract_stage)

    rules_stage, _ = _validated_stage(
        stage="5",
        label="Deterministic audit rules",
        path=job_dir / "audit-rules.json",
        model_type=AuditRuleReport,
    )
    stages.append(rules_stage)

    legal_db = legal_db_path()
    stages.append(
        _stage(
            "6",
            "Versioned legal evidence store",
            WorkspaceArtifactState.READY if legal_db.exists() else WorkspaceArtifactState.MISSING,
            "legal.db",
            "Local versioned legal store is available."
            if legal_db.exists()
            else "Local legal.db is not present; legal evidence details cannot be resolved.",
        )
    )

    retrieval_db = legal_retrieval_index_path()
    stages.append(
        _stage(
            "7",
            "Hybrid legal retrieval index",
            WorkspaceArtifactState.READY if retrieval_db.exists() else WorkspaceArtifactState.MISSING,
            "retrieval.db",
            "Local retrieval index is available."
            if retrieval_db.exists()
            else "Local retrieval.db is not present.",
        )
    )

    primary_stage, primary_value = _validated_stage(
        stage="8",
        label="DeepSeek primary audit",
        path=job_dir / "ai-audit.json",
        model_type=AiAuditReport,
    )
    stages.append(primary_stage)
    if isinstance(primary_value, AiAuditReport):
        review.primary_available = True
        review.primary_provider = primary_value.provider
        review.primary_model = primary_value.model
        review.primary_finding_count = len(primary_value.findings)
        warnings.extend(primary_value.warnings)

    secondary_stage, secondary_value = _validated_stage(
        stage="9A/B",
        label="Kimi secondary review",
        path=job_dir / "secondary-review.json",
        model_type=SecondaryReviewReport,
    )
    stages.append(secondary_stage)
    if isinstance(secondary_value, SecondaryReviewReport):
        review.secondary_available = True
        review.secondary_provider = secondary_value.provider
        review.secondary_model = secondary_value.model
        review.secondary_review_count = len(secondary_value.finding_reviews)
        review.possible_omission_count = len(secondary_value.possible_omissions)
        warnings.extend(secondary_value.warnings)

    report_stage, report_value = _validated_stage(
        stage="9C/D",
        label="Comparison and constrained Agent",
        path=job_dir / "review-report.json",
        model_type=ReviewReport,
    )
    stages.append(report_stage)
    if isinstance(report_value, ReviewReport):
        review.comparison_available = True
        review.final_review_state = report_value.final_state.value
        review.agent_action_count = len(report_value.action_trace)
        warnings.extend(report_value.warnings)

    if not source_available:
        if not source_candidates:
            warnings.append("Original source file is missing from the local upload workspace.")
        else:
            warnings.append("Multiple source files were found for one job; source identity is ambiguous.")

    states = {item.state for item in stages}
    if WorkspaceArtifactState.INVALID in states:
        overall = WorkspaceOverallState.INVALID
    elif report_value is not None and all(
        item.state in {WorkspaceArtifactState.READY, WorkspaceArtifactState.NOT_REQUIRED}
        for item in stages
    ) and source_available:
        if review.final_review_state == "HUMAN_REVIEW_REQUIRED":
            overall = WorkspaceOverallState.HUMAN_REVIEW_REQUIRED
        else:
            overall = WorkspaceOverallState.COMPLETE
    else:
        overall = WorkspaceOverallState.INCOMPLETE

    return WorkspaceSummary(
        job_id=job_id,
        overall_state=overall,
        source_available=source_available,
        document=document,
        stages=stages,
        review=review,
        source_uncertainty=sorted(set(source_uncertainty)),
        warnings=sorted(set(warnings)),
    )
