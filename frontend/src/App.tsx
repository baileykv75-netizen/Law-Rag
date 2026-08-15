import { ChangeEvent, DragEvent, useRef, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png']
const MAX_BYTES = 50 * 1024 * 1024

type PageRoute = 'NATIVE_TEXT_USABLE' | 'OCR_REQUIRED' | 'EMPTY_OR_UNSUPPORTED'
type DocumentRoute = 'NATIVE_TEXT' | 'OCR_REQUIRED' | 'MIXED'

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

type ViewState = 'idle' | 'ready' | 'uploading' | 'success' | 'error'

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
  if (route === 'NATIVE_TEXT') return '原生文本可用'
  if (route === 'NATIVE_TEXT_USABLE') return '原生文本可用'
  if (route === 'MIXED') return '混合路由'
  if (route === 'OCR_REQUIRED') return '需要 OCR'
  return '空白/不支持'
}

function App() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [state, setState] = useState<ViewState>('idle')
  const [message, setMessage] = useState('')
  const [result, setResult] = useState<UploadResult | null>(null)
  const [dragging, setDragging] = useState(false)

  const selectFile = (nextFile: File | null) => {
    setResult(null)
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
        setMessage('检查完成：PDF 原生文本可直接保留，本阶段不会执行 OCR 或 AI 审计。')
      } else if (inspection.route === 'MIXED') {
        setMessage('检查完成：部分页面可直接使用原生文本，其余页面将在阶段 3 进入 OCR。')
      } else {
        setMessage('检查完成：该文档需要 OCR。阶段 2 只负责识别路由，不会执行 OCR。')
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setState('error')
      setMessage(`处理失败：${detail}。请确认本地后端正在运行。`)
    }
  }

  return (
    <main className="page-shell">
      <section className="hero">
        <div className="eyebrow">LOCAL · RESEARCH USE</div>
        <h1>Law-Rag</h1>
        <p className="subtitle">智能合同审计辅助系统 · 本地开发版</p>
        <p className="notice">
          当前阶段只检查文档结构与 PDF 原生文本可用性，不提供法律意见，也不会调用 OCR 或任何大模型 API。
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
        </section>
      )}

      <footer>
        真实合同、脱敏测试集和 API Key 不应提交到 GitHub。正式法律判断必须由专业人员复核。
      </footer>
    </main>
  )
}

export default App
