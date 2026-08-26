import { useCallback, useEffect, useMemo, useState } from 'react'

import { API_BASE_URL } from './apiBase'
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
  delete_state: 'READY' | 'NEEDS_CANCEL' | 'LOCKED' | 'PROTECTED' | 'INVALID'
  delete_reason: string | null
  selected_delete_hint: string | null
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

type BulkDeleteResponse = {
  deleted: Array<{ job_id: string; reclaimed_bytes: number }>
  skipped: Array<{ job_id: string; reason: string }>
  reclaimed_bytes: number
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
  if (item.pipeline_status === 'COMPLETE') return '已完成'
  if (item.pipeline_status === 'FAILED') return '失败'
  if (item.pipeline_status === 'RUNNING') return '运行中'
  if (item.pipeline_status === 'PAUSED_BEFORE_PROVIDER') return '等待模型'
  if (item.pipeline_status === 'WAITING_WORKER') return '等待处理'
  if (item.pipeline_status === 'WAITING_EXTERNAL_SERVICE') return '等待外部服务'
  if (item.pipeline_status === 'CANCELLED') return '已取消'
  return item.pipeline_status ?? '未知状态'
}

export default function JobHistoryApp() {
  const [page, setPage] = useState<HistoryPage | null>(null)
  const [storage, setStorage] = useState<StorageSummary | null>(null)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([])
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

  const items = page?.items ?? []
  const selectedItems = useMemo(
    () => items.filter((item) => selectedJobIds.includes(item.job_id)),
    [items, selectedJobIds],
  )
  const selectedBytes = selectedItems.reduce((sum, item) => sum + item.storage_bytes, 0)

  const toggleSelected = (jobId: string) => {
    setSelectedJobIds((current) =>
      current.includes(jobId) ? current.filter((value) => value !== jobId) : [...current, jobId],
    )
  }

  const selectPage = () => {
    setSelectedJobIds(items.filter((item) => item.can_delete).map((item) => item.job_id))
  }

  const selectDeletable = () => {
    setSelectedJobIds(items.filter((item) => item.can_delete).map((item) => item.job_id))
  }

  const deleteSelected = async () => {
    if (!selectedJobIds.length || deleting) return
    const preview = selectedItems.slice(0, 6).map((item) => `- ${item.filename ?? item.job_id}`).join('\n')
    const extra = selectedItems.length > 6 ? `\n…另有 ${selectedItems.length - 6} 个任务` : ''
    const confirmed = window.confirm(
      `将删除选中的 ${selectedItems.length} 个本机任务，预计释放 ${formatBytes(selectedBytes)}。\n\n${preview}${extra}\n\n运行中任务会先请求停止；共享法律库不会被删除。`,
    )
    if (!confirmed) return

    setDeleting(true)
    setError('')
    setNotice('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/batches/history/jobs/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_ids: selectedJobIds, mode: 'force_safe', confirm: true }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(detail)
      }
      const result = body as BulkDeleteResponse
      const skippedText = result.skipped.length ? `，${result.skipped.length} 个跳过` : ''
      setNotice(`已删除 ${result.deleted.length} 个任务${skippedText}，回收约 ${formatBytes(result.reclaimed_bytes)}。共享法律库未触碰。`)
      setSelectedJobIds([])
      const nextOffset = page && result.deleted.length >= page.items.length && offset > 0 ? Math.max(0, offset - PAGE_SIZE) : offset
      await load(nextOffset)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '无法安全清理选中任务。')
    } finally {
      setDeleting(false)
    }
  }
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
        <button type="button" onClick={() => void load(offset)} disabled={loading || deleting}>
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
          <div><span>受保护任务</span><strong>{storage.active_or_protected_job_count}</strong></div>
          <div><span>待恢复清理数据</span><strong>{formatBytes(storage.cleanup_bytes)}</strong></div>
          <p>删除任务只清理该 Job 的 jobs / uploads / rendered 私有目录；共享 legal 目录不属于删除事务。</p>
          {storage.warnings.map((warning) => <p className="storage-warning" key={warning}>{warning}</p>)}
        </section>
      ) : null}

      {notice ? <div className="history-notice">{notice}</div> : null}
      {error ? <div className="history-error">{error}</div> : null}

      <section className="history-bulk-toolbar" aria-label="批量清理">
        <div>
          <strong>已选 {selectedJobIds.length} 个</strong>
          <span>预计释放 {formatBytes(selectedBytes)}</span>
        </div>
        <button type="button" onClick={selectPage} disabled={loading || deleting || !items.length}>选择本页</button>
        <button type="button" onClick={selectDeletable} disabled={loading || deleting || !items.some((item) => item.can_delete)}>选择可清理</button>
        <button type="button" onClick={() => setSelectedJobIds([])} disabled={loading || deleting || !selectedJobIds.length}>清空选择</button>
        <button className="history-delete" type="button" onClick={() => void deleteSelected()} disabled={loading || deleting || !selectedJobIds.length}>
          {deleting ? '删除中…' : '删除选中'}
        </button>
      </section>

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
            <label className="history-select">
              <input
                type="checkbox"
                checked={selectedJobIds.includes(item.job_id)}
                disabled={!item.can_delete || deleting}
                onChange={() => toggleSelected(item.job_id)}
              />
              <span>{item.can_delete ? '选择' : '不可选'}</span>
            </label>
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

              <div className="history-meta compact" aria-label="任务摘要">
                <span><em>类型</em><strong>{item.document_kind?.toUpperCase() ?? '—'}</strong></span>
                <span><em>进度</em><strong>{item.progress_percent == null ? '—' : `${item.progress_percent}%`}</strong></span>
                <span><em>占用</em><strong>{formatBytes(item.storage_bytes)}</strong></span>
                <span><em>更新</em><strong>{formatTime(item.updated_at ?? item.started_at)}</strong></span>
              </div>

              {item.warning ? <p className="history-warning">{item.warning}</p> : null}
            </div>

            <div className="history-card-actions">
              <a href={`/workspace?job=${encodeURIComponent(item.job_id)}`}>打开工作台</a>
              <span>{item.delete_reason ?? (item.can_delete ? '可清理' : '暂不可清理')}</span>
            </div>
          </article>
        ))}
      </section>

      {total > PAGE_SIZE ? (
        <nav className="history-pagination" aria-label="历史分页">
          <button type="button" disabled={!hasPrevious || loading || deleting} onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}>
            上一页
          </button>
          <span>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
          <button type="button" disabled={!hasNext || loading || deleting} onClick={() => void load(offset + PAGE_SIZE)}>
            下一页
          </button>
        </nav>
      ) : null}
    </main>
  )
}
