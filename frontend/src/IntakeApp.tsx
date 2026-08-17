import { DragEvent, useEffect, useMemo, useRef, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png']
const CURRENT_MAX_BYTES = 50 * 1024 * 1024

type QueueState = 'queued' | 'uploading' | 'inspecting' | 'received' | 'error'

type UploadResponse = {
  job_id: string
  filename: string
  page_count: number
  route: string
  ocr_required_pages: number
}

type QueueItem = {
  id: string
  file: File
  state: QueueState
  progress: number
  error: string | null
  result: UploadResponse | null
}

function extensionOf(name: string) {
  const index = name.lastIndexOf('.')
  return index >= 0 ? name.slice(index).toLowerCase() : ''
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(bytes >= 100 * 1024 * 1024 ? 0 : 1)} MB`
}

function validateFile(file: File): string | null {
  if (!ALLOWED_EXTENSIONS.includes(extensionOf(file.name))) {
    return '暂支持 PDF、JPG、JPEG、PNG。'
  }
  if (file.size === 0) return '文件为空。'
  if (file.size > CURRENT_MAX_BYTES) {
    return '当前版本单文件上限仍为 50 MB；500 MB 流式上传将在下一阶段接入。'
  }
  return null
}

function stateLabel(item: QueueItem) {
  if (item.state === 'queued') return '等待上传'
  if (item.state === 'uploading') return `正在上传 ${Math.round(item.progress)}%`
  if (item.state === 'inspecting') return '正在读取文档'
  if (item.state === 'received') return '文件已接收'
  return '处理失败'
}

function createQueueItem(file: File): QueueItem {
  const error = validateFile(file)
  return {
    id: `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`,
    file,
    state: error ? 'error' : 'queued',
    progress: 0,
    error,
    result: null,
  }
}

function IntakeApp() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [items, setItems] = useState<QueueItem[]>([])
  const [dragging, setDragging] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)

  const queuedCount = items.filter((item) => item.state === 'queued').length
  const receivedCount = items.filter((item) => item.state === 'received').length
  const errorCount = items.filter((item) => item.state === 'error').length

  const batchProgress = useMemo(() => {
    if (!items.length) return 0
    const total = items.reduce((sum, item) => {
      if (item.state === 'received') return sum + 100
      if (item.state === 'inspecting') return sum + 95
      if (item.state === 'uploading') return sum + Math.min(item.progress * 0.9, 90)
      return sum
    }, 0)
    return Math.round(total / items.length)
  }, [items])

  const addFiles = (files: File[]) => {
    if (!files.length) return
    setItems((current) => {
      const existing = new Set(
        current.map((item) => `${item.file.name}::${item.file.size}::${item.file.lastModified}`),
      )
      const additions = files
        .filter((file) => !existing.has(`${file.name}::${file.size}::${file.lastModified}`))
        .map(createQueueItem)
      return [...current, ...additions]
    })
  }

  useEffect(() => {
    if (activeId) return
    const next = items.find((item) => item.state === 'queued')
    if (next) setActiveId(next.id)
  }, [activeId, items])

  useEffect(() => {
    if (!activeId) return
    const item = items.find((candidate) => candidate.id === activeId)
    if (!item || item.state !== 'queued') {
      setActiveId(null)
      return
    }

    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', item.file)

    setItems((current) =>
      current.map((candidate) =>
        candidate.id === activeId
          ? { ...candidate, state: 'uploading', progress: 0, error: null }
          : candidate,
      ),
    )

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      const progress = Math.min(100, (event.loaded / event.total) * 100)
      setItems((current) =>
        current.map((candidate) =>
          candidate.id === activeId
            ? {
                ...candidate,
                state: progress >= 100 ? 'inspecting' : 'uploading',
                progress,
              }
            : candidate,
        ),
      )
    }

    xhr.onload = () => {
      if (xhr.status === 201) {
        let result: UploadResponse | null = null
        try {
          result = JSON.parse(xhr.responseText) as UploadResponse
        } catch {
          result = null
        }
        setItems((current) =>
          current.map((candidate) =>
            candidate.id === activeId
              ? { ...candidate, state: 'received', progress: 100, result, error: null }
              : candidate,
          ),
        )
      } else {
        let message = `上传失败（HTTP ${xhr.status}）。`
        try {
          const payload = JSON.parse(xhr.responseText) as { detail?: string }
          if (payload.detail) message = payload.detail
        } catch {
          // Keep the safe generic message; never surface an arbitrary HTML response.
        }
        setItems((current) =>
          current.map((candidate) =>
            candidate.id === activeId ? { ...candidate, state: 'error', error: message } : candidate,
          ),
        )
      }
      setActiveId(null)
    }

    xhr.onerror = () => {
      setItems((current) =>
        current.map((candidate) =>
          candidate.id === activeId
            ? { ...candidate, state: 'error', error: '无法连接本地 Law-Rag 服务。' }
            : candidate,
        ),
      )
      setActiveId(null)
    }

    xhr.open('POST', `${API_BASE_URL}/api/documents`)
    xhr.send(form)

    return () => {
      if (xhr.readyState !== XMLHttpRequest.DONE) xhr.abort()
    }
    // The selected queue item is intentionally captured once for this upload lifecycle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId])

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    addFiles(Array.from(event.dataTransfer.files))
  }

  const retry = (id: string) => {
    setItems((current) =>
      current.map((item) =>
        item.id === id && validateFile(item.file) === null
          ? { ...item, state: 'queued', progress: 0, error: null, result: null }
          : item,
      ),
    )
  }

  const remove = (id: string) => {
    if (id === activeId) return
    setItems((current) => current.filter((item) => item.id !== id))
  }

  return (
    <main className="intake-shell">
      <header className="intake-header">
        <div>
          <p className="intake-eyebrow">LAW-RAG</p>
          <h1>合同审计</h1>
        </div>
        <a className="intake-developer-link" href="/developer" aria-label="打开高级调试模式">
          高级模式
        </a>
      </header>

      <section className="intake-card" aria-label="合同文件导入">
        <div
          className={`intake-dropzone${dragging ? ' is-dragging' : ''}`}
          onDragEnter={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
          }}
        >
          <input
            ref={inputRef}
            className="intake-file-input"
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
            onChange={(event) => {
              addFiles(Array.from(event.target.files ?? []))
              event.currentTarget.value = ''
            }}
          />
          <div className="intake-drop-icon" aria-hidden="true">＋</div>
          <h2>拖入合同文件</h2>
          <p>也可以点击选择多个文件</p>
          <span>PDF · JPG · PNG</span>
        </div>

        {items.length > 0 && (
          <div className="intake-queue-wrap">
            <div className="intake-batch-summary">
              <div>
                <strong>{receivedCount}/{items.length}</strong>
                <span> 文件已接收</span>
                {queuedCount > 0 && <span> · {queuedCount} 个等待</span>}
                {errorCount > 0 && <span className="intake-error-text"> · {errorCount} 个失败</span>}
              </div>
              <span>{batchProgress}%</span>
            </div>
            <div className="intake-batch-progress" aria-label={`批次进度 ${batchProgress}%`}>
              <div style={{ width: `${batchProgress}%` }} />
            </div>

            <div className="intake-queue" aria-live="polite">
              {items.map((item) => (
                <article className={`intake-row state-${item.state}`} key={item.id}>
                  <div className="intake-file-copy">
                    <strong title={item.file.name}>{item.file.name}</strong>
                    <span>{formatBytes(item.file.size)}</span>
                  </div>
                  <div className="intake-row-status">
                    <span>{stateLabel(item)}</span>
                    {(item.state === 'uploading' || item.state === 'inspecting') && (
                      <div className="intake-row-progress" aria-hidden="true">
                        <div style={{ width: `${Math.max(item.progress, item.state === 'inspecting' ? 100 : 0)}%` }} />
                      </div>
                    )}
                    {item.error && <small>{item.error}</small>}
                    {item.result && (
                      <small>
                        {item.result.page_count} 页
                        {item.result.ocr_required_pages > 0 ? ` · ${item.result.ocr_required_pages} 页需要 OCR` : ''}
                      </small>
                    )}
                  </div>
                  <div className="intake-row-actions">
                    {item.state === 'error' && validateFile(item.file) === null && (
                      <button type="button" onClick={() => retry(item.id)}>重试</button>
                    )}
                    {item.id !== activeId && item.state !== 'uploading' && item.state !== 'inspecting' && (
                      <button type="button" className="quiet" onClick={() => remove(item.id)}>移除</button>
                    )}
                  </div>
                </article>
              ))}
            </div>

            <div className="intake-footnote">
              当前页面只显示真实上传/文档读取状态；完整后台审计进度将在下一阶段接入，不显示虚假百分比。
            </div>
          </div>
        )}
      </section>
    </main>
  )
}

export default IntakeApp
