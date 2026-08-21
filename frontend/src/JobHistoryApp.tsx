import { useCallback, useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const PAGE_SIZE = 30

type HistoryItem = {
  job_id: string
  filename: string | null
  document_kind: string | null
  architecture: string | null
  pipeline_status: string | null
  progress_percent: number | null
  started_at: string | null
  updated_at: string | null
  completed_at: string | null
  integrity: 'OK' | 'PARTIAL' | 'INVALID'
  terminal: boolean
  can_delete: boolean
  storage_bytes: number
  warning: string | null
}

type HistoryPage = {
  total_count: number
  offset: number
  limit: number
  items: HistoryItem[]
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  const kib = value / 1024
  if (kib < 1024) return `${kib.toFixed(kib >= 100 ? 0 : 1)} KB`
  const mib = kib / 1024
  if (mib < 1024) return `${mib.toFixed(mib >= 100 ? 0 : 1)} MB`
  return `${(mib / 1024).toFixed(2)} GB`
}

function formatTime(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function statusLabel(item: HistoryItem) {
  if (item.integrity === 'INVALID') return '产物异常'
  if (item.integrity === 'PARTIAL' && !item.pipeline_status) return '未形成流水线'
  return item.pipeline_status ?? '未知状态'
}

export default function JobHistoryApp() {
  const [page, setPage] = useState<HistoryPage | null>(null)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async (nextOffset: number) => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/batches/history/jobs?offset=${nextOffset}&limit=${PAGE_SIZE}`,
      )
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(detail)
      }
      setPage(body as HistoryPage)
      setOffset(nextOffset)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法读取本机历史任务。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load(0)
  }, [load])

  const items = page?.items ?? []
  const total = page?.total_count ?? 0
  const hasPrevious = offset > 0
  const hasNext = offset + PAGE_SIZE < total

  return (
    <main className="history-shell">
      <header className="history-header">
        <div>
          <span className="history-eyebrow">LOCAL · PERSISTED HISTORY</span>
          <h1>本机审计历史</h1>
          <p>直接读取现有 runtime 产物，不重新 OCR、不重新检索，也不会调用 DeepSeek / Kimi。</p>
        </div>
        <button type="button" onClick={() => void load(offset)} disabled={loading}>
          {loading ? '刷新中…' : '刷新'}
        </button>
      </header>

      <section className="history-summary" aria-label="历史任务摘要">
        <div><strong>{total}</strong><span>本机任务</span></div>
        <div><strong>{items.filter((item) => item.terminal).length}</strong><span>本页终态</span></div>
        <div><strong>{items.filter((item) => !item.terminal).length}</strong><span>本页未终态</span></div>
        <div><strong>{formatBytes(items.reduce((sum, item) => sum + item.storage_bytes, 0))}</strong><span>本页占用</span></div>
      </section>

      {error ? <div className="history-error">{error}</div> : null}

      <section className="history-list" aria-live="polite">
        {!loading && !error && items.length === 0 ? (
          <div className="history-empty">
            <h2>还没有可读取的本机任务</h2>
            <p>完成一次合同导入后，任务会直接从现有 runtime 目录出现在这里。</p>
            <a href="/">开始导入合同</a>
          </div>
        ) : null}

        {items.map((item) => (
          <article className={`history-card integrity-${item.integrity.toLowerCase()}`} key={item.job_id}>
            <div className="history-card-main">
              <div className="history-title-row">
                <div>
                  <h2>{item.filename ?? '未命名 / 元数据不完整'}</h2>
                  <code>{item.job_id}</code>
                </div>
                <span className={`history-status status-${(item.pipeline_status ?? item.integrity).toLowerCase()}`}>
                  {statusLabel(item)}
                </span>
              </div>

              <dl className="history-meta">
                <div><dt>架构</dt><dd>{item.architecture ?? '—'}</dd></div>
                <div><dt>文件</dt><dd>{item.document_kind?.toUpperCase() ?? '—'}</dd></div>
                <div><dt>进度</dt><dd>{item.progress_percent == null ? '—' : `${item.progress_percent}%`}</dd></div>
                <div><dt>占用</dt><dd>{formatBytes(item.storage_bytes)}</dd></div>
                <div><dt>最近更新</dt><dd>{formatTime(item.updated_at ?? item.started_at)}</dd></div>
                <div><dt>完整性</dt><dd>{item.integrity}</dd></div>
              </dl>

              {item.warning ? <p className="history-warning">{item.warning}</p> : null}
            </div>

            <div className="history-card-actions">
              <a href={`/workspace?job=${encodeURIComponent(item.job_id)}`}>打开工作台</a>
              <span>{item.can_delete ? '终态 · 可清理' : '保留 · 暂不可清理'}</span>
            </div>
          </article>
        ))}
      </section>

      {total > PAGE_SIZE ? (
        <nav className="history-pagination" aria-label="历史分页">
          <button type="button" disabled={!hasPrevious || loading} onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}>
            上一页
          </button>
          <span>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
          <button type="button" disabled={!hasNext || loading} onClick={() => void load(offset + PAGE_SIZE)}>
            下一页
          </button>
        </nav>
      ) : null}
    </main>
  )
}
