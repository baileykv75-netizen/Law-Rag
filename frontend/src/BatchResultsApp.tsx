import { useEffect, useMemo, useState } from 'react'
import {
  API_BASE_URL,
  approveProvider,
  cancelPipeline,
  pauseFutureProviders,
  resumeCancelledPipeline,
} from './pipelineControlClient'

type BatchJobState = 'PROCESSING' | 'WAITING' | 'CANCELLED' | 'FAILED' | 'COMPLETE' | 'INVALID'

type SeverityCounts = {
  critical: number
  high: number
  medium: number
  low: number
  info: number
}

type BatchJobResult = {
  job_id: string
  filename: string
  state: BatchJobState
  progress_percent: number
  pipeline_status: string | null
  failure_code: string | null
  failure_detail: string | null
  final_review_state: string | null
  human_review_required: boolean
  finding_counts: SeverityCounts
  possible_omissions: number
  material_disagreement: boolean
  needs_attention: boolean
}

type BatchResultSummary = {
  batch_id: string
  created_at: string
  jobs: BatchJobResult[]
  total_jobs: number
  complete_jobs: number
  waiting_jobs: number
  cancelled_jobs: number
  failed_jobs: number
  human_review_required_jobs: number
  processing_jobs: number
}

function localToday() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function stateText(job: BatchJobResult) {
  if (job.state === 'PROCESSING') {
    if (job.pipeline_status === 'CANCEL_REQUESTED') return '正在安全取消'
    if (!job.pipeline_status) return '等待继续审计'
    return `处理中 · ${job.progress_percent}%`
  }
  if (job.state === 'WAITING') {
    if (job.pipeline_status === 'PAUSED_BEFORE_PROVIDER') return '等待云端发送确认'
    if (job.pipeline_status === 'WAITING_OPTIONAL_COMPONENT') return '等待 OCR 组件'
    return '等待 API 配置'
  }
  if (job.state === 'CANCELLED') return '已取消'
  if (job.state === 'FAILED') {
    if (job.failure_code === 'APPLICATION_RESTARTED_RETRY_REQUIRED') return '上次运行被中断'
    return '处理失败'
  }
  if (job.state === 'INVALID') return '结果完整性异常'
  if (job.human_review_required) return '需要人工复核'
  if (job.final_review_state === 'MINOR_DISAGREEMENT') return '轻微模型分歧'
  return '审计完成'
}

function BatchResultsApp() {
  const batchId = new URLSearchParams(window.location.search).get('batch')
  const [summary, setSummary] = useState<BatchResultSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const [actionJobId, setActionJobId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: number | null = null

    const load = async () => {
      if (!batchId) {
        setError('缺少批次编号。')
        setLoading(false)
        return
      }
      try {
        const response = await fetch(`${API_BASE_URL}/api/batches/${encodeURIComponent(batchId)}`)
        if (!response.ok) throw new Error(`无法读取批次结果（HTTP ${response.status}）。`)
        const payload = (await response.json()) as BatchResultSummary
        if (cancelled) return
        setSummary(payload)
        setError(null)
        setLoading(false)
        if (payload.processing_jobs > 0) timer = window.setTimeout(load, 1000)
      } catch (caught) {
        if (cancelled) return
        setError(caught instanceof Error ? caught.message : '无法读取批次结果。')
        setLoading(false)
      }
    }

    void load()
    return () => {
      cancelled = true
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [batchId, reloadKey])

  const attentionJobs = useMemo(
    () => summary?.jobs.filter((job) => job.needs_attention).length ?? 0,
    [summary],
  )

  const refreshSoon = () => {
    setReloadKey((value) => value + 1)
  }

  const resumeJob = async (job: BatchJobResult) => {
    setActionJobId(job.job_id)
    setError(null)
    setMessage(null)
    try {
      const hasPipeline = Boolean(job.pipeline_status)
      const endpoint = hasPipeline
        ? `${API_BASE_URL}/api/documents/${job.job_id}/pipeline/retry`
        : `${API_BASE_URL}/api/documents/${job.job_id}/pipeline`
      const response = await fetch(endpoint, hasPipeline
        ? { method: 'POST' }
        : {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ as_of: localToday(), use_semantic: false, provider_mode: 'REQUIRE_APPROVAL' }),
          })
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string }
        throw new Error(payload.detail ?? `无法继续审计（HTTP ${response.status}）。`)
      }
      refreshSoon()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法继续审计。')
    } finally {
      setActionJobId(null)
    }
  }

  const approveCloud = async (job: BatchJobResult) => {
    setActionJobId(job.job_id)
    setError(null)
    setMessage(null)
    try {
      await approveProvider(job.job_id)
      setMessage(`${job.filename}：已明确批准进入 DeepSeek/Kimi 云端审计。`)
      refreshSoon()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法批准云端审计。')
    } finally {
      setActionJobId(null)
    }
  }

  const pauseCloud = async (job: BatchJobResult) => {
    setActionJobId(job.job_id)
    setError(null)
    setMessage(null)
    try {
      const control = await pauseFutureProviders(job.job_id)
      setMessage(
        control.active_provider
          ? `${job.filename}：当前 ${control.active_provider} 请求已经开始，无法撤回；后续外部模型调用将在发送前暂停。`
          : `${job.filename}：尚未开始的 DeepSeek/Kimi 调用已改为发送前确认。`,
      )
      refreshSoon()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法暂停后续云端调用。')
    } finally {
      setActionJobId(null)
    }
  }

  const cancelJob = async (job: BatchJobResult) => {
    setActionJobId(job.job_id)
    setError(null)
    setMessage(null)
    try {
      const action = await cancelPipeline(job.job_id)
      setMessage(
        action.provider_in_flight
          ? `${job.filename}：取消已记录。当前 ${action.control.active_provider ?? '外部模型'} 请求已经开始，已发送内容无法撤回；后续阶段不会继续。`
          : `${job.filename}：${action.detail}`,
      )
      refreshSoon()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法取消审计。')
    } finally {
      setActionJobId(null)
    }
  }

  const resumeCancelled = async (job: BatchJobResult) => {
    setActionJobId(job.job_id)
    setError(null)
    setMessage(null)
    try {
      await resumeCancelledPipeline(job.job_id)
      setMessage(`${job.filename}：已按原云端策略显式重新开始。`)
      refreshSoon()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法重新开始已取消的审计。')
    } finally {
      setActionJobId(null)
    }
  }

  return (
    <main className="batch-results-shell">
      <header className="batch-results-header">
        <div>
          <p className="intake-eyebrow">LAW-RAG</p>
          <h1>审计结果</h1>
          <p>按人工复核需求、严重风险和模型重大分歧优先排序。</p>
        </div>
        <div className="batch-results-header-actions">
          <a href="/">审计新合同 / API 设置</a>
          <a href="/developer" className="quiet-link">高级模式</a>
        </div>
      </header>

      {loading && <section className="batch-results-message">正在读取本机审计结果…</section>}
      {error && <section className="batch-results-message error">{error}</section>}
      {message && <section className="batch-results-message">{message}</section>}

      {summary && (
        <>
          <section className="batch-summary-grid" aria-label="批次审计摘要">
            <article><strong>{summary.total_jobs}</strong><span>合同总数</span></article>
            <article><strong>{summary.complete_jobs}</strong><span>已完成</span></article>
            <article><strong>{summary.human_review_required_jobs}</strong><span>需人工复核</span></article>
            <article><strong>{attentionJobs}</strong><span>优先关注</span></article>
            {(summary.waiting_jobs > 0 || summary.cancelled_jobs > 0 || summary.failed_jobs > 0 || summary.processing_jobs > 0) && (
              <article className="wide">
                <strong>{summary.processing_jobs} / {summary.waiting_jobs} / {summary.cancelled_jobs} / {summary.failed_jobs}</strong>
                <span>处理中 / 等待确认或配置 / 已取消 / 失败或异常</span>
              </article>
            )}
          </section>

          <p className="batch-results-note">
            这里显示的是审计队列与风险提示，不是“合同正确率”或法律结论评分。进入 DeepSeek/Kimi 前的授权与取消由 Law-Rag 的持久化控制状态决定；已经开始的外部请求无法撤回已发送内容，但取消会阻止后续模型/阶段继续。
          </p>

          <section className="batch-results-list" aria-live="polite">
            {summary.jobs.map((job) => {
              const waitingForProvider = job.pipeline_status === 'PAUSED_BEFORE_PROVIDER'
              const resumable = job.state !== 'COMPLETE' && job.state !== 'INVALID' && job.state !== 'CANCELLED' && !waitingForProvider
              const canCancel = (job.state === 'PROCESSING' || job.state === 'WAITING') && job.pipeline_status !== 'CANCEL_REQUESTED'
              return (
                <article className={`batch-result-card state-${job.state.toLowerCase()}${job.needs_attention ? ' needs-attention' : ''}`} key={job.job_id}>
                  <div className="batch-result-main">
                    <div className="batch-result-title-row">
                      <h2 title={job.filename}>{job.filename}</h2>
                      <span className="batch-state-badge">{stateText(job)}</span>
                    </div>

                    {job.state === 'COMPLETE' && (
                      <div className="risk-chip-row" aria-label="风险数量">
                        {job.finding_counts.critical > 0 && <span>严重 {job.finding_counts.critical}</span>}
                        {job.finding_counts.high > 0 && <span>高风险 {job.finding_counts.high}</span>}
                        {job.finding_counts.medium > 0 && <span>中风险 {job.finding_counts.medium}</span>}
                        {job.finding_counts.low > 0 && <span>低风险 {job.finding_counts.low}</span>}
                        {job.possible_omissions > 0 && <span>可能漏审 {job.possible_omissions}</span>}
                        {job.material_disagreement && <span>双模型重大分歧</span>}
                        {!job.needs_attention && job.finding_counts.medium === 0 && job.finding_counts.low === 0 && (
                          <span>暂无优先风险项</span>
                        )}
                      </div>
                    )}

                    {job.state === 'PROCESSING' && job.pipeline_status && (
                      <div className="batch-job-progress" aria-label={`处理进度 ${job.progress_percent}%`}>
                        <div style={{ width: `${job.progress_percent}%` }} />
                      </div>
                    )}

                    {job.state !== 'COMPLETE' && job.failure_detail && (
                      <p className="batch-job-problem">{job.failure_detail}</p>
                    )}
                    {job.state === 'WAITING' && job.pipeline_status === 'WAITING_CONFIGURATION' && (
                      <p className="batch-job-problem">先从首页“API 设置”补充对应 Key，再返回这里点击继续审计。</p>
                    )}
                    {waitingForProvider && (
                      <p className="batch-job-problem">本地阶段已完成。只有点击“批准云端审计”后，受限合同/法律证据才会进入 DeepSeek/Kimi。</p>
                    )}
                  </div>

                  <div className="batch-result-actions">
                    {job.state === 'COMPLETE' && (
                      <a href={`/workspace?job=${encodeURIComponent(job.job_id)}`}>查看详细审计</a>
                    )}
                    {waitingForProvider && (
                      <button type="button" onClick={() => void approveCloud(job)} disabled={actionJobId === job.job_id}>
                        批准云端审计
                      </button>
                    )}
                    {job.state === 'PROCESSING' && job.pipeline_status !== 'CANCEL_REQUESTED' && (
                      <button type="button" className="quiet" onClick={() => void pauseCloud(job)} disabled={actionJobId === job.job_id}>
                        发送前暂停
                      </button>
                    )}
                    {resumable && (
                      <button type="button" onClick={() => void resumeJob(job)} disabled={actionJobId === job.job_id}>
                        {actionJobId === job.job_id ? '正在启动…' : job.pipeline_status ? '继续 / 重试审计' : '启动后台审计'}
                      </button>
                    )}
                    {job.state === 'CANCELLED' && (
                      <button type="button" onClick={() => void resumeCancelled(job)} disabled={actionJobId === job.job_id}>
                        重新开始审计
                      </button>
                    )}
                    {canCancel && (
                      <button type="button" className="danger-quiet" onClick={() => void cancelJob(job)} disabled={actionJobId === job.job_id}>
                        取消审计
                      </button>
                    )}
                    {job.state === 'INVALID' && <a href="/">返回首页处理</a>}
                  </div>
                </article>
              )
            })}
          </section>
        </>
      )}
    </main>
  )
}

export default BatchResultsApp