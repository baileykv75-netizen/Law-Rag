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

type StorageSummary = {
  job_count: number
  terminal_deletable_job_count: number
  active_or_protected_job_count: number
  jobs_bytes: number
  batches_bytes: number
  shared_legal_bytes: number
  cleanup_bytes: number
  other_runtime_bytes: number
  total_runtime_bytes: number
  warnings: string[]
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
  const [storage, setStorage] = useState<StorageSummary | null>(null)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async (nextOffset: number) => {
    setLoading(true)
    setError('')
    try {
      const [historyResponse, storageResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/batches/history/jobs?offset=${nextOffset}&limit=${PAGE_SIZE}`),
        fetch(`${API_BASE_URL}/api/batches/history/storage`),
      ])
      const historyBody = await historyResponse.json().catch(() => null)
      const storageBody = await storageResponse.json().catch(() => null)
      if (!historyResponse.ok) {
        const detail = historyBody && typeof historyBody.detail === 'string' ? historyBody.detail : `HTTP ${historyResponse.status}`
        throw new Error(detail)
      }
      if (!storageResponse.ok) {
        const detail = storageBody && typeof storageBody.detail === 'string' ? storageBody.detail : `HTTP ${storageResponse.status}`
        throw new Error(detail)
      }
      setPage(historyBody as HistoryPage)
      setStorage(storageBody as StorageSummary)
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

  const deleteJob = async (item: HistoryItem) => {
    if (!item.can_delete || deletingJobId) return
    const typed = window.prompt(
      `此操作会永久删除该 Job 的本机合同、审计产物与渲染缓存，且不可撤销。\n\n共享法律库不会被删除。\n\n请输入完整 Job ID 以确认：\n${item.job_id}`,
      '',
    )
    if (typed === null) return
    if (typed.trim() !== item.job_id) {
      setNotice('未删除：输入的 Job ID 与目标任务不一致。')
      return
    }

    setDeletingJobId(item.job_id)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/batches/history/jobs/${encodeURIComponent(item.job_id)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm_job_id: item.job_id }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(detail)
      }
      const reclaimed = body && typeof body.reclaimed_bytes === 'number' ? body.reclaimed_bytes : item.storage_bytes
      setNotice(`已安全清理 ${item.filename ?? item.job_id}，回收约 ${formatBytes(reclaimed)}。共享法律库未触碰。`)
      const nextOffset = page && page.items.length === 1 && offset > 0 ? Math.max(0, offset - PAGE_SIZE) : offset
      await load(nextOffset)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法安全清理该任务。')
    } finally {
      setDeletingJobId(null)
    }
  }

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
        <button type="button" onClick={() => void load(offset)} disabled={loading || Boolean(deletingJobId)}>
          {loading ? '刷新中…' : '刷新'}
        </button>
      </header>

      <section className="history-summary" aria-label="本机存储摘要">
        <div><strong>{storage?.job_count ?? total}</strong><span>本机任务</span></div>
        <div><strong>{storage?.terminal_deletable_job_count ?? items.filter((item) => item.can_delete).length}</strong><span>可安全清理</span></div>
        <div><strong>{formatBytes(storage?.jobs_bytes ?? items.reduce((sum, item) => sum + item.storage_bytes, 0))}</strong><span>任务数据</span></div>
        <div><strong>{formatBytes(storage?.total_runtime_bytes ?? 0)}</strong><span>runtime 总占用</span></div>
      </section>

      {storage ? (
        <section className="storage-breakdown" aria-label="存储构成">
          <div><span>共享法律库</span><strong>{formatBytes(storage.shared_legal_bytes)}</strong></div>
          <div><span>批次索引</span><strong>{formatBytes(storage.batches_bytes)}</strong></div>
          <div><span>受保护/运行中任务</span><strong>{storage.active_or_protected_job_count}</strong></div>
          <div><span>待恢复清理数据</span><strong>{formatBytes(storage.cleanup_bytes)}</strong></div>
          <p>删除任务只清理该 Job 的 jobs / uploads / rendered 私有目录；共享 legal 目录不属于删除事务。</p>
          {storage.warnings.map((warning) => <p className="storage-warning" key={warning}>{warning}</p>)}
        </section>
      ) : null}

      {notice ? <div className="history-notice">{notice}</div> : null}
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
              {item.can_delete ? (
                <button
                  className="history-delete"
                  type="button"
                  disabled={Boolean(deletingJobId)}
                  onClick={() => void deleteJob(item)}
                >
                  {deletingJobId === item.job_id ? '清理中…' : '删除本机任务'}
                </button>
              ) : null}
              <span>{item.can_delete ? '终态 · 输入 Job ID 后可清理' : '保留 · 暂不可清理'}</span>
            </div>
          </article>
        ))}
      </section>

      {total > PAGE_SIZE ? (
        <nav className="history-pagination" aria-label="历史分页">
          <button type="button" disabled={!hasPrevious || loading || Boolean(deletingJobId)} onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}>
            上一页
          </button>
          <span>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
          <button type="button" disabled={!hasNext || loading || Boolean(deletingJobId)} onClick={() => void load(offset + PAGE_SIZE)}>
            下一页
          </button>
        </nav>
      ) : null}
    </main>
  )
}
