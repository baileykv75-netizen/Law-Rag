from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import UUID

from .report_export import _atomic_render, _file_sha256, _render_docx, _render_pdf
from .report_export_models import (
    AuditReportDocument,
    ReportContractEvidence,
    ReportIssue,
    ReportLegalEvidence,
)

_SMOKE_JOB_ID = UUID("00000000-0000-0000-0000-000000001805")
_SMOKE_FINGERPRINT = "18" * 32


def _smoke_report() -> AuditReportDocument:
    return AuditReportDocument(
        job_id=_SMOKE_JOB_ID,
        filename="stage18-packaged-renderer-smoke.docx",
        document_kind="DOCX",
        as_of="2026-08-22",
        overall_state="COMPLETE",
        contract_type="OTHER",
        planning_mode="DETERMINISTIC_SMOKE",
        planning_coverage_complete=True,
        canonical_object_count=1,
        reviewed_with_issue_count=1,
        reviewed_no_specific_issue_count=0,
        primary_provider="diagnostic",
        primary_model="no-network",
        secondary_provider="diagnostic",
        secondary_model="no-network",
        final_review_state="COMPLETE",
        human_review_required_count=0,
        human_review_resolved_required_count=0,
        human_review_outstanding_required_count=0,
        issues=[
            ReportIssue(
                issue_id="issue-stage18-packaged-renderer-smoke",
                topic="Stage 18.5 打包报告渲染诊断",
                priority="LOW",
                why_review=["验证 frozen executable 内 python-docx、lxml、reportlab 与中文 PDF 字体路径可用。"],
                questions=["同一 Stage 18.2 renderer 能否在打包环境生成非空 DOCX/PDF？"],
                primary_state="SUPPORTED_FINDING",
                primary_severity="INFO",
                primary_title="仅用于离线打包诊断",
                primary_reasoning="该内容完全由本地固定字符串构造，不包含合同数据，也不调用任何 Provider。",
                primary_suggestion="仅检查打包依赖与 renderer 可执行性。",
                primary_evidence_sufficiency="SUFFICIENT",
                secondary_assessment="SUPPORTED",
                secondary_coverage_assessment="COVERED",
                secondary_severity="INFO",
                secondary_reasoning="固定诊断对象覆盖 DOCX 与 PDF 两个现有 renderer。",
                secondary_suggestion="诊断成功后删除临时输出。",
                comparison_state="AGREEMENT",
                requires_human_review=False,
                comparison_reasons=["synthetic packaged renderer smoke"],
                contract_evidence=[
                    ReportContractEvidence(
                        evidence_id="diagnostic:evidence:1",
                        quote="本段为 Stage 18.5 离线打包诊断文本。",
                        page_number=1,
                        source_method="SYNTHETIC_DIAGNOSTIC",
                    )
                ],
                legal_evidence=[
                    ReportLegalEvidence(
                        legal_evidence_id="diagnostic:legal:1",
                        authority_id="diagnostic-authority",
                        authority_title="打包诊断依据（非真实法律）",
                        version_id="diagnostic-v1",
                        article_token="诊断条目",
                        article_text="仅验证中文文本与 PDF/DOCX renderer，不构成任何法律内容。",
                        effective_date="2026-08-22",
                        coverage_type="DIAGNOSTIC",
                    )
                ],
            )
        ],
        source_uncertainty=[],
        warnings=["Synthetic release diagnostic only; no contract, legal corpus, model, or network input was used."],
        source_fingerprints={"diagnostic": _SMOKE_FINGERPRINT},
        report_content_fingerprint=_SMOKE_FINGERPRINT,
    )


def diagnose_packaged_report_renderers() -> dict[str, object]:
    """Exercise the authoritative Stage 18.2 renderers without a Job or network call."""

    report = _smoke_report()
    with tempfile.TemporaryDirectory(prefix="law-rag-stage18-report-") as temporary:
        root = Path(temporary)
        docx_path = root / "stage18-smoke.docx"
        pdf_path = root / "stage18-smoke.pdf"
        _atomic_render(docx_path, lambda path: _render_docx(report, path))
        _atomic_render(pdf_path, lambda path: _render_pdf(report, path))

        docx_prefix = docx_path.read_bytes()[:4]
        pdf_prefix = pdf_path.read_bytes()[:4]
        docx_ready = docx_path.stat().st_size > 0 and docx_prefix == b"PK\x03\x04"
        pdf_ready = pdf_path.stat().st_size > 0 and pdf_prefix == b"%PDF"
        return {
            "ready": bool(docx_ready and pdf_ready),
            "network_used": False,
            "synthetic_only": True,
            "report_engine_version": report.engine_version,
            "docx": {
                "ready": docx_ready,
                "size_bytes": docx_path.stat().st_size,
                "sha256": _file_sha256(docx_path),
                "signature": docx_prefix.hex(),
            },
            "pdf": {
                "ready": pdf_ready,
                "size_bytes": pdf_path.stat().st_size,
                "sha256": _file_sha256(pdf_path),
                "signature": pdf_prefix.decode("ascii", errors="replace"),
            },
        }


def run_packaged_report_renderer_diagnostic() -> int:
    try:
        payload = diagnose_packaged_report_renderers()
    except Exception as exc:
        payload = {
            "ready": False,
            "network_used": False,
            "synthetic_only": True,
            "error": f"{type(exc).__name__}: {exc}",
        }
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return 0 if payload.get("ready") is True else 8
