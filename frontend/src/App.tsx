import { ChangeEvent, DragEvent, useRef, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png']
const MAX_BYTES = 50 * 1024 * 1024

type PageRoute = 'NATIVE_TEXT_USABLE' | 'OCR_REQUIRED' | 'EMPTY_OR_UNSUPPORTED'
type DocumentRoute = 'NATIVE_TEXT' | 'OCR_REQUIRED' | 'MIXED'
type OcrPageState = 'NATIVE_RETAINED' | 'OCR_COMPLETE' | 'OCR_LOW_CONFIDENCE' | 'OCR_NO_TEXT' | 'OCR_FAILED'

type PageSummary = {
  evidence_id: string
  page_number: number
  route: PageRoute
  character_count: number
  route_reason: string
}

type UploadResult = {
  job_id: string
  filename: string
  media_type: string
  size_bytes: number
  status: string
  storage_scope: string
  document_kind: 'pdf' | 'image'
  page_count: number
  route: DocumentRoute
  native_text_pages: number
  ocr_required_pages: number
  pages: PageSummary[]
}

type OcrPageResult = {
  page_number: number
  state: OcrPageState
  source_method: 'native_pdf_text' | 'image_source' | 'ocr'
  text: string
  low_confidence_blocks: number
  error: string | null
}

type OcrRunResult = {
  job_id: string
  provider: string
  model: string
  provider_version: string
  status: string
  page_count: number
  native_pages: number
  ocr_pages_attempted: number
  ocr_pages_complete: number
  low_confidence_pages: number
  failed_pages: number
  no_text_pages: number
  pages: OcrPageResult[]
}

type ViewState = 'idle' | 'ready' | 'uploading' | 'success' | 'error'
type OcrViewState = 'idle' | 'running' | 'success' | 'error'

function getExtension(name: string) {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot).toLowerCase() : ''
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function validateFile(file: File): string | null {
  if (!ALLOWED_EXTENSIONS.includes(getExtension(file.name))) {
    return '暂仅支持 PDF、JPG、JPEG、PNG 文件。'
  }
  if (file.size === 0) return '文件为空，请选择有效文件。'
  if (file.size > MAX_BYTES) return '文件超过当前 50 MiB 限制。'
  return null
}

function routeLabel(route: DocumentRoute | PageRoute) {
  if (route === 'NATIVE_TEXT' || route === 'NATIVE_TEXT_USABLE') return '原生文本可用'
  if (route === 'MIXED') return '混合路由'
  if (route === 'OCR_REQUIRED') return '需要 OCR'
  return '空白/不支持'
}

function ocrStateLabel(state: OcrPageState) {
  if (state === 'NATIVE_RETAINED') return '保留原生文本'
  if (state === 'OCR_COMPLETE') return 'OCR 完成'
  if (state === 'OCR_LOW_CONFIDENCE') return 'OCR 低置信度'
  if (state === 'OCR_NO_TEXT') return 'OCR 无文本'
  return 'OCR 失败'
}

function App() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [state, setState] = useState<ViewState>('idle')
  const [message, setMessage] = useState('')
  const [result, setResult] = useState<UploadResult | null>(null)
  const [dragging, setDragging] = useState(false)
  const [ocrState, setOcrState] = useState<OcrViewState>('idle')
  const [ocrMessage, setOcrMessage] = useState('')
  const [ocrResult, setOcrResult] = useState<OcrRunResult | null>(null)

  const resetOcr = () => {
    setOcrState('idle')
    setOcrMessage('')
    setOcrResult(null)
  }

  const selectFile = (nextFile: File | null) => {
    setResult(null)
    resetOcr()
    if (!nextFile) {
      setFile(null)
      setState('idle')
      setMessage('')
      return
    }

    const error = validateFile(nextFile)
    if (error) {
      setFile(null)
      setState('error')
      setMessage(error)
      return
    }

    setFile(nextFile)
    setState('ready')
    setMessage('文件已准备好，可以进行本地文档检查。')
  }

  const handleInput = (event: ChangeEvent<HTMLInputElement>) => {
    selectFile(event.target.files?.[0] ?? null)
    event.target.value = ''
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    selectFile(event.dataTransfer.files?.[0] ?? null)
  }

  const upload = async () => {
    if (!file || state === 'uploading') return

    setState('uploading')
    setMessage('正在保存并检查文档结构…')
    setResult(null)
    resetOcr()

    try {
      const form = new FormData()
      form.append('file', file)
      const response = await fetch(`${API_BASE_URL}/api/documents`, {
        method: 'POST',
        body: form,
      })
      const body = await response.json().catch(() => null)

      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `处理失败（HTTP ${response.status}）`
        throw new Error(detail)
      }

      const inspection = body as UploadResult
      setResult(inspection)
      setState('success')
      if (inspection.route === 'NATIVE_TEXT') {
        setMessage('检查完成：PDF 原生文本可直接保留，不需要 OCR。法律审计尚未开始。')
      } else if (inspection.route === 'MIXED') {
        setMessage('检查完成：部分页面使用原生文本，其余页面可继续运行本地 OCR。')
      } else {
        setMessage('检查完成：该文档需要 OCR。安装 OCR 运行时后可继续处理。')
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setState('error')
      setMessage(`处理失败：${detail}。请确认本地后端正在运行。`)
    }
  }

  const runOcr = async () => {
    if (!result || result.ocr_required_pages === 0 || ocrState === 'running') return

    setOcrState('running')
    setOcrMessage('正在本机执行 OCR；首次使用可能需要下载模型…')
    setOcrResult(null)

    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${result.job_id}/ocr`, {
        method: 'POST',
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `OCR 失败（HTTP ${response.status}）`
        throw new Error(detail)
      }

      const next = body as OcrRunResult
      setOcrResult(next)
      setOcrState('success')
      if (next.failed_pages || next.no_text_pages) {
        setOcrMessage('OCR 已完成，但存在失败或无文本页面；这些页面必须保留为待人工复核状态。')
      } else if (next.low_confidence_pages) {
        setOcrMessage('OCR 已完成，但存在低置信度页面。当前结果只是文字证据，不代表法律审计结论。')
      } else {
        setOcrMessage('OCR 已完成并保存页级证据。当前仍未开始法律审计。')
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setOcrState('error')
      setOcrMessage(`OCR 无法运行：${detail}`)
    }
  }

  return (
    <main className="page-shell">
      <section className="hero">
        <div className="eyebrow">LOCAL · RESEARCH USE</div>
        <h1>Law-Rag</h1>
        <p className="subtitle">智能合同审计辅助系统 · 本地开发版</p>
        <p className="notice">
          当前阶段完成文档分流和本地 OCR 证据提取，不提供法律意见，也不会调用任何大模型 API。
        </p>
      </section>

      <section className="workspace" aria-label="合同导入">
        <div
          className={`drop-zone ${dragging ? 'is-dragging' : ''}`}
          onDragEnter={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => {
            if (event.currentTarget === event.target) setDragging(false)
          }}
          onDrop={handleDrop}
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
          }}
        >
          <div className="document-icon" aria-hidden="true">§</div>
          <strong>拖入合同文件</strong>
          <span>或点击选择本机文件</span>
          <span className="file-hint">PDF · JPG · JPEG · PNG · 最大 50 MiB</span>
          <input
            ref={inputRef}
            className="file-input"
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
            onChange={handleInput}
          />
        </div>

        {file && (
          <div className="selected-file">
            <div>
              <span className="meta-label">已选择文件</span>
              <strong>{file.name}</strong>
            </div>
            <div className="file-size">{formatBytes(file.size)}</div>
          </div>
        )}

        <button className="primary-action" onClick={upload} disabled={!file || state === 'uploading'}>
          {state === 'uploading' ? '正在检查…' : '导入并检查文档'}
        </button>

        {message && <div className={`status status-${state}`}>{message}</div>}
      </section>

      {result && (
        <section className="result-card" aria-label="文档检查结果">
          <div className="result-heading">
            <div>
              <span className="meta-label">本地任务</span>
              <h2>文档检查完成</h2>
            </div>
            <span className={`route-pill route-${result.route.toLowerCase()}`}>{routeLabel(result.route)}</span>
          </div>

          <div className="route-metrics">
            <div><span>总页数</span><strong>{result.page_count}</strong></div>
            <div><span>原生文本页</span><strong>{result.native_text_pages}</strong></div>
            <div><span>待 OCR 页</span><strong>{result.ocr_required_pages}</strong></div>
          </div>

          <dl>
            <div><dt>文件名</dt><dd>{result.filename}</dd></div>
            <div><dt>文档类型</dt><dd>{result.document_kind.toUpperCase()}</dd></div>
            <div><dt>MIME 类型</dt><dd>{result.media_type}</dd></div>
            <div><dt>大小</dt><dd>{formatBytes(result.size_bytes)}</dd></div>
            <div><dt>任务 ID</dt><dd className="mono">{result.job_id}</dd></div>
            <div><dt>存储范围</dt><dd>{result.storage_scope}</dd></div>
          </dl>

          <div className="page-routes">
            <div className="section-label">页级路由</div>
            {result.pages.map((page) => (
              <div className="page-route" key={page.evidence_id}>
                <div>
                  <strong>第 {page.page_number} 页</strong>
                  <span className="mono">{page.evidence_id}</span>
                </div>
                <div className="page-route-detail">
                  <span>{routeLabel(page.route)}</span>
                  <small>{page.character_count} 字符</small>
                </div>
              </div>
            ))}
          </div>

          {result.ocr_required_pages > 0 && (
            <div className="ocr-actions">
              <button className="secondary-action" onClick={runOcr} disabled={ocrState === 'running'}>
                {ocrState === 'running' ? '正在运行本地 OCR…' : `运行本地 OCR（${result.ocr_required_pages} 页）`}
              </button>
              <p>首次使用请先运行根目录 <span className="mono">setup-ocr-cpu.bat</span>。OCR 仅处理待识别页面。</p>
              {ocrMessage && <div className={`status status-${ocrState === 'error' ? 'error' : 'ready'}`}>{ocrMessage}</div>}
            </div>
          )}
        </section>
      )}

      {ocrResult && (
        <section className="result-card" aria-label="OCR 结果">
          <div className="result-heading">
            <div>
              <span className="meta-label">OCR Evidence</span>
              <h2>本地 OCR 证据</h2>
            </div>
            <span className="success-pill">{ocrResult.status.toUpperCase()}</span>
          </div>

          <div className="route-metrics ocr-metrics">
            <div><span>尝试 OCR</span><strong>{ocrResult.ocr_pages_attempted}</strong></div>
            <div><span>识别出文本</span><strong>{ocrResult.ocr_pages_complete}</strong></div>
            <div><span>低置信度页</span><strong>{ocrResult.low_confidence_pages}</strong></div>
            <div><span>失败页</span><strong>{ocrResult.failed_pages}</strong></div>
            <div><span>无文本页</span><strong>{ocrResult.no_text_pages}</strong></div>
          </div>

          <dl>
            <div><dt>OCR Provider</dt><dd>{ocrResult.provider}</dd></div>
            <div><dt>模型</dt><dd>{ocrResult.model}</dd></div>
            <div><dt>Provider 版本</dt><dd>{ocrResult.provider_version}</dd></div>
          </dl>

          <div className="page-routes">
            <div className="section-label">处理后页级证据</div>
            {ocrResult.pages.map((page) => (
              <div className="page-route" key={`ocr-${page.page_number}`}>
                <div>
                  <strong>第 {page.page_number} 页</strong>
                  <span>{page.source_method === 'ocr' ? 'OCR evidence' : 'Native evidence'}</span>
                </div>
                <div className="page-route-detail">
                  <span>{ocrStateLabel(page.state)}</span>
                  {page.low_confidence_blocks > 0 && <small>{page.low_confidence_blocks} 个低置信度块</small>}
                  {page.error && <small className="warning-text">{page.error}</small>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <footer>
        真实合同、脱敏测试集和 API Key 不应提交到 GitHub。OCR 结果仍需人工复核，正式法律判断必须由专业人员完成。
      </footer>
    </main>
  )
}

export default App
