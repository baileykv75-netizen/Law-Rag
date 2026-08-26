from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from .report_export import ReportExportError, export_audit_report
from .report_export_models import ReportExportFormat

router = APIRouter(tags=["report-export"])

_MEDIA_TYPES = {
    ReportExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ReportExportFormat.PDF: "application/pdf",
}


@router.post("/api/documents/{job_id}/report-export/{format}")
def create_report_export(job_id: UUID, format: ReportExportFormat) -> FileResponse:
    """Render a local report from validated ISSUE_V1 artifacts only.

    This endpoint never invokes OCR, retrieval, or another provider. It only
    reads already-persisted authoritative artifacts and renders a local report.
    """

    try:
        path, result = export_audit_report(job_id, format)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ReportExportError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Report export failed safely: {type(exc).__name__}: {exc}",
        ) from exc

    return FileResponse(
        path,
        media_type=_MEDIA_TYPES[format],
        filename=result.filename,
        headers={
            "X-Law-Rag-Report-SHA256": result.sha256,
            "X-Law-Rag-Report-Content-Fingerprint": result.report_content_fingerprint,
        },
    )
