import { FormEvent, useEffect, useMemo, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type SourceEvidenceDetail = {
  schema_version: string
  evidence_id: string
  page_number: number
  source_method: 'native_pdf_text' | 'image_source' | 'ocr'
  text: string
  confidence: number | null
  bbox: number[] | null
  polygon: number[][] | null
  char_start: number | null
  char_end: number | null
  source_locator: string | null
  coordinate_space_width_px: number | null
  coordinate_space_height_px: number | null
  canonical_references: Array<{ object_type: string; object_id: string }>
}

type Props = {
  jobId: string
  pageCount: number
  sourceAvailable: boolean
  requestedEvidenceId?: string | null
}

function sourceMethodLabel(method: SourceEvidenceDetail['source_method']) {
  if (method === 'ocr') return 'OCR'
  if (method === 'native_pdf_text') return '原生 PDF 文本'
  return '原始图片'
}

export default function SourceViewerPane({ jobId, pageCount, sourceAvailable, requestedEvidenceId }: Props) {
  const [page, setPage] = useState(1)
  const [zoom, setZoom] = useState(1)
  const [evidenceInput, setEvidenceInput] = useState('')
  const [evidence, setEvidence] = useState<SourceEvidenceDetail | null>(null)
  const [evidenceMessage, setEvidenceMessage] = useState('')
  const [loadingEvidence, setLoadingEvidence] = useState(false)

  const pageUrl = `${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/source/pages/${page}`

  const overlayStyle = useMemo(() => {
    if (!evidence || evidence.page_number !== page) return null
    const width = evidence.coordinate_space_width_px
    const height = evidence.coordinate_space_height_px
    if (!width || !height) return null

    if (evidence.polygon && evidence.polygon.length >= 3) {
      const points = evidence.polygon
        .map(([x, y]) => `${(x / width) * 100}% ${(y / height) * 100}%`)
        .join(', ')
      return {
        left: '0%', top: '0%', width: '100%', height: '100%',
        clipPath: `polygon(${points})`,
      }
    }

    if (evidence.bbox && evidence.bbox.length >= 4) {
      const [x1, y1, x2, y2] = evidence.bbox
      return {
        left: `${(x1 / width) * 100}%`,
        top: `${(y1 / height) * 100}%`,
        width: `${((x2 - x1) / width) * 100}%`,
        height: `${((y2 - y1) / height) * 100}%`,
      }
    }
    return null
  }, [evidence, page])

  const changePage = (next: number) => {
    const bounded = Math.min(Math.max(next, 1), pageCount)
    setPage(bounded)
  }

  const resolveEvidenceById = async (rawId: string) => {
    const id = rawId.trim()
    if (!id) return
    setLoadingEvidence(true)
    setEvidenceMessage('正在解析 Evidence…')
    setEvidenceInput(id)
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/evidence/${encodeURIComponent(id)}`,
      )
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(detail)
      }
      const detail = body as SourceEvidenceDetail
      setEvidence(detail)
      setPage(detail.page_number)
      setEvidenceMessage('Evidence 已定位到源页。')
    } catch (error) {
      setEvidence(null)
      setEvidenceMessage(error instanceof Error ? error.message : 'Evidence 无法解析。')
    } finally {
      setLoadingEvidence(false)
    }
  }

  useEffect(() => {
    if (requestedEvidenceId) void resolveEvidenceById(requestedEvidenceId)
    // The request is an explicit cross-pane navigation event.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedEvidenceId, jobId])

  const resolveEvidence = (event: FormEvent) => {
    event.preventDefault()
    if (loadingEvidence) return
    void resolveEvidenceById(evidenceInput)
  }

  if (!sourceAvailable) {
    return (
      <div className="source-viewer-error">
        <strong>源文件不可用</strong>
        <p>工作台不会猜测或替换源文件。请先恢复该 Job 唯一的本地 source 文件。</p>
      </div>
    )
  }

  return (
    <div className="source-viewer">
      <div className="source-toolbar">
        <div className="page-controls">
          <button type="button" onClick={() => changePage(page - 1)} disabled={page <= 1}>‹</button>
          <span>第 <strong>{page}</strong> / {pageCount} 页</span>
          <button type="button" onClick={() => changePage(page + 1)} disabled={page >= pageCount}>›</button>
        </div>
        <div className="zoom-controls">
          <button type="button" onClick={() => setZoom((value) => Math.max(.6, value - .15))}>−</button>
          <span>{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={() => setZoom((value) => Math.min(2, value + .15))}>＋</button>
          <button type="button" onClick={() => setZoom(1)}>重置</button>
        </div>
      </div>

      <div className="source-page-viewport">
        <div className="source-page-scale" style={{ width: `${zoom * 100}%` }}>
          <div className={`source-page-canvas ${evidence && evidence.page_number === page && !overlayStyle ? 'native-span-selected' : ''}`}>
            <img src={pageUrl} alt={`合同第 ${page} 页`} draggable={false} />
            {overlayStyle && <div className="evidence-overlay" style={overlayStyle} aria-label="Evidence 高亮区域" />}
          </div>
        </div>
      </div>

      <form className="evidence-locator" onSubmit={resolveEvidence}>
        <label htmlFor="evidence-id-input">Evidence 定位</label>
        <div>
          <input
            id="evidence-id-input"
            value={evidenceInput}
            onChange={(event) => setEvidenceInput(event.target.value)}
            placeholder="输入合同 Evidence ID"
            autoComplete="off"
          />
          <button type="submit" disabled={!evidenceInput.trim() || loadingEvidence}>
            {loadingEvidence ? '定位中…' : '定位'}
          </button>
        </div>
        {evidenceMessage && <small>{evidenceMessage}</small>}
      </form>

      {evidence && (
        <div className="selected-evidence-card">
          <div className="selected-evidence-heading">
            <span>{sourceMethodLabel(evidence.source_method)}</span>
            <strong>{evidence.evidence_id}</strong>
          </div>
          <blockquote>{evidence.text || '该 Evidence 没有可展示文本。'}</blockquote>
          <div className="selected-evidence-meta">
            <span>页码：{evidence.page_number}</span>
            <span>置信度：{evidence.confidence == null ? '—' : evidence.confidence.toFixed(3)}</span>
            <span>
              {evidence.bbox || evidence.polygon
                ? '可视坐标：已高亮'
                : evidence.char_start != null
                  ? `文本范围：${evidence.char_start}–${evidence.char_end ?? '—'}`
                  : '可视坐标：无'}
            </span>
          </div>
          {evidence.source_method === 'native_pdf_text' && !overlayStyle && (
            <p className="native-span-note">原生文本 Evidence 只有字符区间时，当前页以边框提示“本页命中”，精确 quote/offset 保留在此卡片中；不会伪造 bbox。</p>
          )}
          {evidence.canonical_references.length > 0 && (
            <div className="canonical-ref-list">
              {evidence.canonical_references.map((ref) => (
                <span key={`${ref.object_type}-${ref.object_id}`}>{ref.object_type} · {ref.object_id}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
