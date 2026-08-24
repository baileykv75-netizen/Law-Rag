import { useEffect, useMemo, useState } from 'react'
import {
  API_BASE_URL,
  approveProvider,
  cancelPipeline,
  pauseFutureProviders,
  resumeCancelledPipeline,
} from './pipelineControlClient'

type BatchJobState = 'PROCESSING' | 'WAITING' | 'CANCELLED' | 'FAILED' | 'COMPLETE' | 'INVALID'
type AuditArchitecture = 'ISSUE_V1' | 'LEGACY_RC2' | 'CONFLICT'

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
  architecture: AuditArchitecture | null
  final_review_state: string | null
  human_review_required: boolean
  finding_counts: SeverityCounts
  issue_count: number
  possible_omissions: number
  material_disagreement: boolean
  material_disagreement_count: number
  insufficient_evidence_count: number
  review_required_count: number
  planning_coverage_complete: boolean | null
  planning_coverage_reviewed_count: number
  planning_coverage_total_count: number
  human_review_resolved_count: number
  human_review_outstanding_count: number
  human_review_stale_count: number
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
  issue_v1_jobs: number
  legacy_rc2_jobs: number
  coverage_incomplete_jobs: number
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
  if (job.architecture === 'ISSUE_V1' && job.final_review_state === 'COMPLETE') return '审计闭环完成'
  if (job.final_review_state === 'MINOR_DISAGREEMENT') return '轻微模型分歧'
  return '审计完成'
}

function architectureText(job: BatchJobResult) {
  if (job.architecture === 'ISSUE_V1') return 'ISSUE_V1 · Stage 13'
  if (job.architecture === 'LEGACY_RC2') return 'LEGACY_RC2 · 历史任务'
  if (job.architecture === 'CONFLICT') return 'ARCHITECTURE CONFLICT'
  return '架构待确认'
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
      setMessage(`${job.filename}：已明确批准后续 Planner / DeepSeek / Kimi 受限云端调用。`)
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
          ? `${job.filename}：当前 ${control.active_provider} 请求已经开始，无法撤回；后续 Planner / DeepSeek / Kimi 调用将在发送前暂停。`
          : `${job.filename}：尚未开始的 Planner / DeepSeek / Kimi 调用已改为发送前确认。`,
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
          <p>按待人工复核、可能漏审、实质分歧、严重度与证据不足优先排序。</p>
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
            <article><strong>{summary.complete_jobs}</strong><span>流水线已完成</span></article>
            <article><strong>{summary.human_review_required_jobs}</strong><span>仍需人工复核</span></article>
            <article><strong>{attentionJobs}</strong><span>优先关注</span></article>
            {(summary.issue_v1_jobs > 0 || summary.legacy_rc2_jobs > 0) && (
              <article className="wide">
                <strong>{summary.issue_v1_jobs} / {summary.legacy_rc2_jobs}</strong>
                <span>Stage 13 Issue V1 / 历史 Legacy RC2</span>
              </article>
            )}
            {summary.coverage_incomplete_jobs > 0 && (
              <article className="wide">
                <strong>{summary.coverage_incomplete_jobs}</strong>
                <span>合同规划覆盖不完整，不能解释为“未发现风险”</span>
              </article>
            )}
            {(summary.waiting_jobs > 0 || summary.cancelled_jobs > 0 || summary.failed_jobs > 0 || summary.processing_jobs > 0) && (
              <article className="wide">
                <strong>{summary.processing_jobs} / {summary.waiting_jobs} / {summary.cancelled_jobs} / {summary.failed_jobs}</strong>
                <span>处理中 / 等待确认或配置 / 已取消 / 失败或异常</span>
              </article>
            )}
          </section>

          <p className="batch-results-note">
            这里显示的是审计工作队列，不是“合同正确率”或法律风险评分。Stage 13 新任务以 AuditPlan Issue、规划覆盖、双模型确定性 Comparison 和当前人工复核状态为权威摘要；历史 RC2 任务保持原语义。打开结果或工作台不会触发模型调用。
          </p>

          <section className="batch-results-list" aria-live="polite">
            {summary.jobs.map((job) => {
              const waitingForProvider = job.pipeline_status === 'PAUSED_BEFORE_PROVIDER'
              const resumable =
                (job.state === 'PROCESSING' && !job.pipeline_status)
                || job.state === 'FAILED'
                || (
                  job.state === 'WAITING'
                  && (job.pipeline_status === 'WAITING_CONFIGURATION' || job.pipeline_status === 'WAITING_OPTIONAL_COMPONENT')
                )
              const canCancel = (job.state === 'PROCESSING' || job.state === 'WAITING') && job.pipeline_status !== 'CANCEL_REQUESTED'
              const hasLowPriorityRisk = job.finding_counts.medium > 0 || job.finding_counts.low > 0
              return (
                <article className={`batch-result-card state-${job.state.toLowerCase()}${job.needs_attention ? ' needs-attention' : ''}`} key={job.job_id}>
                  <div className="batch-result-main">
                    <div className="batch-result-title-row">
                      <h2 title={job.filename}>{job.filename}</h2>
                      <span className="batch-state-badge">{stateText(job)}</span>
                    </div>
                    <p className="batch-results-note">{architectureText(job)}</p>

                    {job.state === 'COMPLETE' && (
                      <div className="risk-chip-row" aria-label="审计摘要">
                        {job.architecture === 'ISSUE_V1' && <span>AuditPlan Issues {job.issue_count}</span>}
                        {job.architecture === 'ISSUE_V1' && job.planning_coverage_total_count > 0 && (
                          <span>
                            Coverage {job.planning_coverage_reviewed_count}/{job.planning_coverage_total_count}
                            {job.planning_coverage_complete === false ? ' · 不完整' : ''}
                          </span>
                        )}
                        {job.finding_counts.critical > 0 && <span>严重 {job.finding_counts.critical}</span>}
                        {job.finding_counts.high > 0 && <span>高风险 {job.finding_counts.high}</span>}
                        {job.finding_counts.medium > 0 && <span>中风险 {job.finding_counts.medium}</span>}
                        {job.finding_counts.low > 0 && <span>低风险 {job.finding_counts.low}</span>}
                        {job.possible_omissions > 0 && <span>可能漏审 {job.possible_omissions}</span>}
                        {job.material_disagreement_count > 0 && <span>实质分歧 {job.material_disagreement_count}</span>}
                        {job.insufficient_evidence_count > 0 && <span>证据不足 {job.insufficient_evidence_count}</span>}
                        {job.review_required_count > 0 && <span>程序要求复核 {job.review_required_count}</span>}
                        {job.architecture === 'ISSUE_V1' && job.human_review_resolved_count > 0 && (
                          <span>人工已处理 {job.human_review_resolved_count}</span>
                        )}
                        {job.human_review_outstanding_count > 0 && <span>人工待处理 {job.human_review_outstanding_count}</span>}
                        {job.human_review_stale_count > 0 && <span>人工决定过期 {job.human_review_stale_count}</span>}
                        {!job.needs_attention && !hasLowPriorityRisk && <span>暂无优先风险项</span>}
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
                      <p className="batch-job-problem">当前已到外部模型边界。只有点击“批准云端审计”后，Law-Rag 才允许下一次受限 Planner / DeepSeek / Kimi 调用。</p>
                    )}
                    {job.architecture === 'ISSUE_V1' && job.planning_coverage_complete === false && (
                      <p className="batch-job-problem">AuditPlan 对 Canonical Contract 的规划覆盖不完整；即使已有 Issue 都处理完，也不能把未覆盖文本解释为安全。</p>
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
                        {actionJobId === job.job_id
                          ? '正在启动…'
                          : !job.pipeline_status
                            ? '启动后台审计'
                            : job.state === 'FAILED'
                              ? '重试审计'
                              : '继续审计'}
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