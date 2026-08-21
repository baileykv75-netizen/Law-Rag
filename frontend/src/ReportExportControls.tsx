import { useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type ExportFormat = 'docx' | 'pdf'

type Props = {
  jobId: string
  enabled: boolean
  outstandingHumanReview: number
}

function exportFilename(response: Response, jobId: string, format: ExportFormat) {
  const disposition = response.headers.get('content-disposition') ?? ''
  const encoded = disposition.match(/filename\*=utf-8''([^;]+)/i)?.[1]
  if (encoded) {
    try {
      return decodeURIComponent(encoded)
    } catch {
      // Fall back to the safe local filename below.
    }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  return plain || `Law-Rag-Audit-${jobId.slice(0, 8)}.${format}`
}

export default function ReportExportControls({ jobId, enabled, outstandingHumanReview }: Props) {
  const [exporting, setExporting] = useState<ExportFormat | null>(null)
  const [message, setMessage] = useState('')

  const exportReport = async (format: ExportFormat) => {
    if (!enabled || exporting) return
    setExporting(format)
    setMessage(`正在本地生成 ${format.toUpperCase()} 报告…`)
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/report-export/${format}`,
        { method: 'POST' },
      )
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(detail)
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      try {
        const anchor = document.createElement('a')
        anchor.href = url
        anchor.download = exportFilename(response, jobId, format)
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
      } finally {
        URL.revokeObjectURL(url)
      }
      setMessage(
        outstandingHumanReview > 0
          ? `本地 ${format.toUpperCase()} 已导出；仍有 ${outstandingHumanReview} 项必需人工复核。未触发模型调用。`
          : `本地 ${format.toUpperCase()} 已导出；未触发模型调用。`,
      )
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '报告导出失败。')
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="report-export-controls" aria-label="本地审计报告导出">
      <div className="report-export-actions">
        <button type="button" disabled={!enabled || exporting !== null} onClick={() => void exportReport('docx')}>
          {exporting === 'docx' ? '生成 DOCX…' : '导出 DOCX'}
        </button>
        <button type="button" disabled={!enabled || exporting !== null} onClick={() => void exportReport('pdf')}>
          {exporting === 'pdf' ? '生成 PDF…' : '导出 PDF'}
        </button>
      </div>
      <small className={outstandingHumanReview > 0 ? 'is-review' : ''}>
        {message || (
          enabled
            ? (outstandingHumanReview > 0 ? '可导出，但报告会明确标记“待人工复核”。' : '仅从本地已验证 ISSUE_V1 工件生成。')
            : '审计比较链完整后才能导出。'
        )}
      </small>
    </div>
  )
}
