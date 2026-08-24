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
  external_service_waiting_jobs: number
  cancelled_jobs: number
  failed_jobs: number
  invalid_jobs: number
  provider_failed_jobs: number
  system_error_jobs: number
  human_review_required_jobs: number
  processing_jobs: number
  issue_v1_jobs: number
  legacy_rc2_jobs: number
  coverage_incomplete_jobs: number
}

const TRANSIENT_POLL_STATUSES = new Set([409, 422, 429, 500, 502, 503, 504])
const MAX_TRANSIENT_POLL_FAILURES = 6

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
    if (job.pipeline_status === 'WAITING_EXTERNAL_SERVICE') return '等待外部服务恢复'
    return '等待 API 配置'
  }
  if (job.state === 'CANCELLED') return '已取消'
  if (job.state === 'FAILED') {
    if (job.failure_code === 'APPLICATION_RESTARTED_RETRY_REQUIRED') return '上次运行被中断'
    return '处理未完成'
  }
  if (job.state === 'INVALID') return '旧任务记录异常（非审计结论）'
  if (job.human_review_required) return '需要人工复核'
  if (job.final_review_state === 'MINOR_DISAGREEMENT') return '轻微模型分歧'
  return '审计完成'
}

function architectureText(job: BatchJobResult) {
  if (job.state === 'INVALID') return '旧本地任务记录不完整，已从有效合同统计中隔离。'
  if (job.architecture === 'ISSUE_V1') return '当前审计流程'
  if (job.architecture === 'LEGACY_RC2') return '历史版本审计任务'
  if (job.architecture === 'CONFLICT') return '任务结构异常 · 暂不生成法律结论'
  return '正在确认任务状态'
}

function friendlyFailure(job: BatchJobResult) {
  const detail = job.failure_detail ?? ''
  const code = job.failure_code ?? ''
  if (job.state === 'INVALID' || code === 'DOCUMENT_METADATA_INVALID') {
    return '旧任务的本地记录不完整。它不代表合同存在法律风险，也不计入有效合同数量。'
  }
  if (job.pipeline_status === 'WAITING_EXTERNAL_SERVICE') {
    return '外部模型暂时不可用。已完成的本地处理和模型检查点已经保留；稍后点击“继续审计”即可从未完成阶段恢复。'
  }
  if (detail.includes('AtomicWriteError') || code.includes('AtomicWriteError')) {
    return '本地任务状态保存时发生短暂文件冲突。已完成的处理结果会尽量保留；可点击“重试审计”。'
  }
  if (detail.includes('Server disconnected') || detail.includes('network') || detail.includes('Network')) {
    return '外部模型连接暂时中断。已完成的本地处理结果会保留；可稍后重试。'
  }
  return detail || '本次处理未完成。已完成的阶段会在重试时优先复用。'
}

function BatchResultsApp() {
  const initialBatchId = new URLSearchParams(window.location.search).get('batch')
  const [batchId, setBatchId] = useState<string | null>(initialBatchId)
  const [summary, setSummary] = useState<BatchResultSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const [actionJobId, setActionJobId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: number | null = null
    let transientFailures = 0

    const scheduleRetry = (delay: number) => {
      if (!cancelled) timer = window.setTimeout(load, delay)
    }

    const resolveRecentBatch = async () => {
      const response = await fetch(`${API_BASE_URL}/api/batches/recent`)
      if (!response.ok) throw new Error(`无法读取最近审计批次（HTTP ${response.status}）。`)
      const payload = (await response.json()) as BatchResultSummary | null
      if (cancelled) return null
      if (!payload?.batch_id) {
        setSummary(null)
        setError(null)
        setLoading(false)
        return null
      }
      setBatchId(payload.batch_id)
      window.history.replaceState(null, '', `/results?batch=${encodeURIComponent(payload.batch_id)}`)
      return payload.batch_id
    }

    const load = async () => {
      try {
        const resolvedBatchId = batchId ?? (await resolveRecentBatch())
        if (!resolvedBatchId || cancelled) return
        const response = await fetch(`${API_BASE_URL}/api/batches/${encodeURIComponent(resolvedBatchId)}`)
        if (!response.ok) {
          if (TRANSIENT_POLL_STATUSES.has(response.status) && transientFailures < MAX_TRANSIENT_POLL_FAILURES) {
            transientFailures += 1
            scheduleRetry(Math.min(300 * 2 ** (transientFailures - 1), 3000))
            return
          }
          throw new Error(`无法读取批次结果（HTTP ${response.status}）。`)
        }
        const payload = (await response.json()) as BatchResultSummary
        if (cancelled) return
        transientFailures = 0
        setSummary(payload)
        setError(null)
        setLoading(false)
        if (payload.processing_jobs > 0) scheduleRetry(1000)
      } catch (caught) {
        if (cancelled) return
        // Network-level fetch failures follow the same bounded recovery policy as
        // transient HTTP responses. Do not let one dropped localhost poll replace
        // a previously valid task state with a false user-visible failure.
        if (transientFailures < MAX_TRANSIENT_POLL_FAILURES) {
          transientFailures += 1
          scheduleRetry(Math.min(300 * 2 ** (transientFailures - 1), 3000))
          return
        }
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
    () => summary?.jobs.filter((job) => job.state !== 'INVALID' && job.needs_attention).length ?? 0,
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
      setMessage(`${job.filename}：已保留可复用的前序结果，将从最早未完成阶段继续。`)
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
      setMessage(`${job.filename}：已批准后续受限云端审计。`)
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
          ? `${job.filename}：当前外部模型请求已开始，无法撤回；后续云端调用将在发送前暂停。`
          : `${job.filename}：尚未开始的云端调用已改为发送前确认。`,
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
          ? `${job.filename}：取消已记录。当前外部模型请求已经开始，已发送内容无法撤回；后续阶段不会继续。`
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
      setMessage(`${job.filename}：已按原云端策略重新开始。`)
      refreshSoon()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法重新开始已取消的审计。')
    } finally {
      setActionJobId(null)
    }
  }

  const removeInvalidFromBatch = async (job: BatchJobResult) => {
    if (!batchId) return
    setActionJobId(job.job_id)
    setError(null)
    setMessage(null)
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/batches/${encodeURIComponent(batchId)}/invalid-jobs/${encodeURIComponent(job.job_id)}`,
        { method: 'DELETE' },
      )
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string }
        throw new Error(payload.detail ?? `无法移除旧异常记录（HTTP ${response.status}）。`)
      }
      const payload = (await response.json()) as BatchResultSummary
      setSummary(payload)
      setMessage('旧异常记录已从当前批次移除；本地诊断数据仍保留在历史记录中。')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法移除旧异常记录。')
    } finally {
      setActionJobId(null)
    }
  }

  const validJobs = summary?.jobs.filter((job) => job.state !== 'INVALID') ?? []
  const allJobsComplete = validJobs.length > 0 && validJobs.every((job) => job.state === 'COMPLETE')

  return (
    <main className="batch-results-shell">
      <header className="batch-results-header">
        <div>
          <p className="intake-eyebrow">LAW-RAG</p>
          <h1>{allJobsComplete ? '审计结果' : '审计进度与结果'}</h1>
          <p>处理中显示任务进度；只有完整完成的合同才进入法律风险统计。</p>
        </div>
        <div className="batch-results-header-actions">
          <a href="/">审计新合同 / API 设置</a>
          <a href="/developer" className="quiet-link">高级模式</a>
        </div>
      </header>

      {loading && <section className="batch-results-message">正在读取本机审计结果…</section>}
      {error && <section className="batch-results-message error">{error}</section>}
      {message && <section className="batch-results-message">{message}</section>}
      {!loading && !error && !summary && (
        <section className="batch-results-message">
          暂无可查看的审计批次。请先导入合同开始审计。 <a href="/">返回导入合同</a>
        </section>
      )}

      {summary && (
        <>
          <section className="batch-summary-grid" aria-label="批次审计摘要">
            <article><strong>{summary.total_jobs}</strong><span>有效合同任务</span></article>
            <article><strong>{summary.complete_jobs}</strong><span>审计已完成</span></article>
            <article><strong>{summary.human_review_required_jobs}</strong><span>仍需人工复核</span></article>
            <article><strong>{attentionJobs}</strong><span>合同任务需处理</span></article>
            {(summary.processing_jobs > 0 || summary.waiting_jobs > 0 || summary.cancelled_jobs > 0 || summary.failed_jobs > 0) && (
              <article className="wide">
                <strong>{summary.processing_jobs} / {summary.waiting_jobs} / {summary.cancelled_jobs} / {summary.failed_jobs}</strong>
                <span>处理中 / 等待继续 / 已取消 / 处理未完成</span>
              </article>
            )}
            {summary.external_service_waiting_jobs > 0 && (
              <article className="wide">
                <strong>{summary.external_service_waiting_jobs}</strong>
                <span>外部模型暂时不可用 · 已保留检查点，可稍后继续</span>
              </article>
            )}
            {(summary.provider_failed_jobs > 0 || summary.system_error_jobs > 0 || summary.invalid_jobs > 0) && (
              <article className="wide">
                <strong>{summary.provider_failed_jobs} / {summary.system_error_jobs} / {summary.invalid_jobs}</strong>
                <span>不可恢复的外部服务错误 / 本地系统异常 / 隔离的旧异常记录</span>
              </article>
            )}
            {summary.coverage_incomplete_jobs > 0 && (
              <article className="wide">
                <strong>{summary.coverage_incomplete_jobs}</strong>
                <span>仍有合同文本未完成规划覆盖，不能解释为“未发现风险”</span>
              </article>
            )}
          </section>

          <p className="batch-results-note">
            系统故障、网络异常和旧任务损坏都不是法律风险。法律结论只来自完整完成的合同审查；技术诊断可在高级模式查看。
          </p>

          <section className="batch-results-list" aria-live="polite">
            {summary.jobs.map((job) => {
              const waitingForProvider = job.pipeline_status === 'PAUSED_BEFORE_PROVIDER'
              const resumable =
                (job.state === 'PROCESSING' && !job.pipeline_status)
                || job.state === 'FAILED'
                || (
                  job.state === 'WAITING'
                  && (
                    job.pipeline_status === 'WAITING_CONFIGURATION'
                    || job.pipeline_status === 'WAITING_OPTIONAL_COMPONENT'
                    || job.pipeline_status === 'WAITING_EXTERNAL_SERVICE'
                  )
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
                        {job.architecture === 'ISSUE_V1' && <span>审查问题 {job.issue_count}</span>}
                        {job.architecture === 'ISSUE_V1' && job.planning_coverage_total_count > 0 && (
                          <span>
                            文本覆盖 {job.planning_coverage_reviewed_count}/{job.planning_coverage_total_count}
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
                        {job.review_required_count > 0 && <span>建议复核 {job.review_required_count}</span>}
                        {job.human_review_resolved_count > 0 && <span>人工已处理 {job.human_review_resolved_count}</span>}
                        {job.human_review_outstanding_count > 0 && <span>人工待处理 {job.human_review_outstanding_count}</span>}
                        {job.human_review_stale_count > 0 && <span>人工决定需更新 {job.human_review_stale_count}</span>}
                        {!job.needs_attention && !hasLowPriorityRisk && <span>暂无优先风险项</span>}
                      </div>
                    )}

                    {job.state === 'PROCESSING' && job.pipeline_status && (
                      <div className="batch-job-progress" aria-label={`处理进度 ${job.progress_percent}%`}>
                        <div style={{ width: `${job.progress_percent}%` }} />
                      </div>
                    )}

                    {job.state !== 'COMPLETE' && job.failure_detail && (
                      <p className="batch-job-problem">{friendlyFailure(job)}</p>
                    )}
                    {job.state === 'FAILED' && (
                      <p className="batch-results-note">重试会优先复用已完成的 OCR、合同结构、规则检查和已保存的模型检查点，不会无条件从头开始。</p>
                    )}
                    {job.state === 'WAITING' && job.pipeline_status === 'WAITING_CONFIGURATION' && (
                      <p className="batch-job-problem">请先从首页“API 设置”补充对应密钥，再返回这里继续审计。</p>
                    )}
                    {job.state === 'WAITING' && job.pipeline_status === 'WAITING_EXTERNAL_SERVICE' && (
                      <p className="batch-results-note">这不是法律风险，也不是合同审计结论。现有进度已保存，外部服务恢复后可直接继续。</p>
                    )}
                    {waitingForProvider && (
                      <p className="batch-job-problem">本地处理已完成并到达云端发送边界。只有点击“批准云端审计”后才会发送下一次受限请求。</p>
                    )}
                    {job.architecture === 'ISSUE_V1' && job.planning_coverage_complete === false && (
                      <p className="batch-job-problem">仍有合同文本未完成规划覆盖；即使当前问题都已处理，也不能把未覆盖文本解释为安全。</p>
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
                    {job.state === 'INVALID' && (
                      <button type="button" className="quiet" onClick={() => void removeInvalidFromBatch(job)} disabled={actionJobId === job.job_id}>
                        从当前批次移除
                      </button>
                    )}
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
