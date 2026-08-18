import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type PageTextAnchor = {
  kind: 'PAGE_TEXT'
  page_number: number
  char_start: number | null
  char_end: number | null
}

type PageRegionAnchor = {
  kind: 'PAGE_REGION'
  page_number: number
  bbox: number[] | null
  polygon: number[][] | null
}

type DocxParagraphAnchor = {
  kind: 'DOCX_PARAGRAPH'
  part: string
  paragraph_index: number
  char_start: number | null
  char_end: number | null
}

type DocxTableCellAnchor = {
  kind: 'DOCX_TABLE_CELL'
  part: string
  table_index: number
  row_index: number
  cell_index: number
  paragraph_index: number
  char_start: number | null
  char_end: number | null
}

type DocxImageAnchor = {
  kind: 'DOCX_EMBEDDED_IMAGE'
  part: string
  image_index: number
  relationship_id: string | null
  parent_locator: string | null
}

type SourceAnchor = PageTextAnchor | PageRegionAnchor | DocxParagraphAnchor | DocxTableCellAnchor | DocxImageAnchor

type SourceEvidenceDetail = {
  schema_version: string
  evidence_id: string
  page_number: number | null
  source_method: 'native_pdf_text' | 'native_docx_text' | 'image_source' | 'ocr'
  text: string
  source_anchor: SourceAnchor | null
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

type SourceWarning = {
  code: string
  message: string
  source_locator: string | null
  blocks_complete_coverage: boolean
}

type DocxLogicalParagraph = {
  kind: 'PARAGRAPH'
  order_index: number
  evidence_id: string
  text: string
  source_locator: string
  source_anchor: DocxParagraphAnchor
}

type DocxCellParagraph = {
  order_index: number
  evidence_id: string
  text: string
  source_locator: string
  source_anchor: DocxTableCellAnchor
}

type DocxLogicalTable = {
  kind: 'TABLE'
  order_index: number
  table_index: number
  group_id: string
  rows: Array<{
    row_index: number
    cells: Array<{
      row_index: number
      cell_index: number
      paragraphs: DocxCellParagraph[]
    }>
  }>
}

type DocxLogicalImage = {
  kind: 'IMAGE'
  order_index: number
  evidence_id: string
  source_locator: string
  source_anchor: DocxImageAnchor
}

type DocxSourceView = {
  schema_version: string
  job_id: string
  document_kind: 'docx'
  filename: string
  pagination: 'LOGICAL_NO_STABLE_PAGES'
  evidence_count: number
  coverage_complete: boolean
  warnings: SourceWarning[]
  blocks: Array<DocxLogicalParagraph | DocxLogicalTable | DocxLogicalImage>
}

type Props = {
  jobId: string
  documentKind: string
  pageCount: number
  sourceAvailable: boolean
  requestedEvidenceId?: string | null
}

function sourceMethodLabel(method: SourceEvidenceDetail['source_method']) {
  if (method === 'ocr') return 'OCR'
  if (method === 'native_pdf_text') return '原生 PDF 文本'
  if (method === 'native_docx_text') return '原生 DOCX 结构'
  return '原始图片'
}

function sourceLocationLabel(evidence: SourceEvidenceDetail) {
  const anchor = evidence.source_anchor
  if (!anchor) return evidence.page_number == null ? '结构位置未知' : `第 ${evidence.page_number} 页`
  if (anchor.kind === 'DOCX_PARAGRAPH') return `正文段落 ${anchor.paragraph_index}`
  if (anchor.kind === 'DOCX_TABLE_CELL') {
    return `表 ${anchor.table_index} · 行 ${anchor.row_index} · 列 ${anchor.cell_index} · 段 ${anchor.paragraph_index}`
  }
  if (anchor.kind === 'DOCX_EMBEDDED_IMAGE') return `内嵌图片 ${anchor.image_index}`
  return `第 ${anchor.page_number} 页`
}

export default function SourceViewerPane({ jobId, documentKind, pageCount, sourceAvailable, requestedEvidenceId }: Props) {
  const isDocx = documentKind === 'docx'
  const [page, setPage] = useState(1)
  const [zoom, setZoom] = useState(1)
  const [evidenceInput, setEvidenceInput] = useState('')
  const [evidence, setEvidence] = useState<SourceEvidenceDetail | null>(null)
  const [evidenceMessage, setEvidenceMessage] = useState('')
  const [loadingEvidence, setLoadingEvidence] = useState(false)
  const [docxView, setDocxView] = useState<DocxSourceView | null>(null)
  const [docxMessage, setDocxMessage] = useState(isDocx ? '正在读取本地 DOCX 逻辑结构…' : '')
  const logicalViewportRef = useRef<HTMLDivElement | null>(null)

  const pageUrl = `${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/source/pages/${page}`

  useEffect(() => {
    if (!isDocx || !sourceAvailable) {
      setDocxView(null)
      setDocxMessage('')
      return
    }
    let cancelled = false
    const load = async () => {
      setDocxMessage('正在读取本地 DOCX 逻辑结构…')
      try {
        const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/source/docx`)
        const body = await response.json().catch(() => null)
        if (!response.ok) {
          const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
          throw new Error(detail)
        }
        if (!cancelled) {
          setDocxView(body as DocxSourceView)
          setDocxMessage('按 Word 结构展示；DOCX 不具有稳定源页码。')
        }
      } catch (error) {
        if (!cancelled) {
          setDocxView(null)
          setDocxMessage(error instanceof Error ? error.message : 'DOCX 逻辑源无法读取。')
        }
      }
    }
    void load()
    return () => { cancelled = true }
  }, [isDocx, jobId, sourceAvailable])

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
    if (pageCount < 1) return
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
      if (detail.page_number != null) setPage(detail.page_number)
      setEvidenceMessage(
        detail.page_number == null
          ? 'Evidence 已定位到 DOCX 结构位置。'
          : 'Evidence 已定位到源页。',
      )
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

  useEffect(() => {
    if (!isDocx || !evidence || !docxView || !logicalViewportRef.current) return
    const candidates = Array.from(logicalViewportRef.current.querySelectorAll<HTMLElement>('[data-evidence-id]'))
    const target = candidates.find((node) => node.dataset.evidenceId === evidence.evidence_id)
    target?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [docxView, evidence, isDocx])

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
      {isDocx ? (
        <>
          <div className="source-toolbar docx-source-toolbar">
            <div>
              <strong>DOCX 逻辑源</strong>
              <span>按段落与表格结构定位 · 不伪造页码</span>
            </div>
            <span>{docxView ? `${docxView.evidence_count} 个 Evidence` : '读取中'}</span>
          </div>

          {docxView && docxView.warnings.length > 0 && (
            <div className={`docx-source-warnings ${docxView.coverage_complete ? '' : 'is-blocking'}`}>
              <strong>{docxView.coverage_complete ? '源文档提示' : '源覆盖需要人工确认'}</strong>
              <ul>
                {docxView.warnings.map((warning, index) => (
                  <li key={`${warning.code}-${warning.source_locator ?? index}`}>
                    <span>{warning.code}</span>
                    {warning.message}
                    {warning.blocks_complete_coverage && <em>影响完整覆盖</em>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="docx-logical-viewport" ref={logicalViewportRef}>
            {docxView ? docxView.blocks.map((block) => {
              if (block.kind === 'PARAGRAPH') {
                const selected = evidence?.evidence_id === block.evidence_id
                return (
                  <article
                    className={`docx-paragraph ${selected ? 'is-selected' : ''}`}
                    key={`p-${block.order_index}-${block.evidence_id}`}
                    data-evidence-id={block.evidence_id}
                  >
                    <span>P{block.source_anchor.paragraph_index}</span>
                    <p>{block.text}</p>
                  </article>
                )
              }
              if (block.kind === 'TABLE') {
                return (
                  <section className="docx-table-block" key={`table-${block.table_index}`}>
                    <div className="docx-block-caption">表 {block.table_index} · {block.group_id}</div>
                    <div className="docx-table-scroll">
                      <table>
                        <tbody>
                          {block.rows.map((row) => (
                            <tr key={`row-${block.table_index}-${row.row_index}`}>
                              {row.cells.map((cell) => {
                                const cellSelected = cell.paragraphs.some((item) => item.evidence_id === evidence?.evidence_id)
                                return (
                                  <td className={cellSelected ? 'is-selected' : ''} key={`cell-${row.row_index}-${cell.cell_index}`}>
                                    <small>R{row.row_index} · C{cell.cell_index}</small>
                                    {cell.paragraphs.map((item) => (
                                      <p
                                        className={item.evidence_id === evidence?.evidence_id ? 'is-selected-paragraph' : ''}
                                        key={item.evidence_id}
                                        data-evidence-id={item.evidence_id}
                                      >
                                        {item.text}
                                      </p>
                                    ))}
                                  </td>
                                )
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                )
              }
              const selected = evidence?.evidence_id === block.evidence_id
              return (
                <article
                  className={`docx-image-placeholder ${selected ? 'is-selected' : ''}`}
                  key={`image-${block.order_index}-${block.evidence_id}`}
                  data-evidence-id={block.evidence_id}
                >
                  <strong>内嵌图片 {block.source_anchor.image_index}</strong>
                  <span>已保留 Evidence 身份；Stage 14.3 不执行图片 OCR。</span>
                </article>
              )
            }) : (
              <div className="docx-source-empty">{docxMessage || 'DOCX 逻辑源不可用。'}</div>
            )}
          </div>
          {docxMessage && <small className="docx-source-message">{docxMessage}</small>}
        </>
      ) : (
        <>
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
        </>
      )}

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
            <span>位置：{sourceLocationLabel(evidence)}</span>
            <span>置信度：{evidence.confidence == null ? '—' : evidence.confidence.toFixed(3)}</span>
            <span>
              {evidence.bbox || evidence.polygon
                ? '可视坐标：已高亮'
                : evidence.char_start != null
                  ? `文本范围：${evidence.char_start}–${evidence.char_end ?? '—'}`
                  : isDocx ? '结构锚点：已高亮' : '可视坐标：无'}
            </span>
          </div>
          {evidence.source_method === 'native_pdf_text' && !overlayStyle && (
            <p className="native-span-note">原生文本 Evidence 只有字符区间时，当前页以边框提示“本页命中”，精确 quote/offset 保留在此卡片中；不会伪造 bbox。</p>
          )}
          {evidence.source_method === 'native_docx_text' && (
            <p className="native-span-note">DOCX 使用 Word 结构锚点定位，不把流式排版转换成虚构页码。所选段落或表格单元格已在上方逻辑源中高亮。</p>
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
