import { useEffect, useState } from 'react'
import {
  API_BASE_URL,
  approveProvider,
  cancelPipeline,
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
  completion_state: string | null
  overall_risk: string | null
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
  if (job.completion_state) return job.completion_state
  if (job.state === 'PROCESSING') return job.pipeline_status ? `分析中 · ${job.progress_percent}%` : '等待启动'
  if (job.state === 'WAITING') {
    if (job.pipeline_status === 'PAUSED_BEFORE_PROVIDER') return '等待授权'
    if (job.pipeline_status === 'WAITING_EXTERNAL_SERVICE') return '等待外部服务'
    return '等待配置'
  }
  if (job.state === 'CANCELLED') return '已取消'
  if (job.state === 'FAILED') return '未完成'
  if (job.state === 'INVALID') return '记录异常'
  return '已完成'
}

function riskText(job: BatchJobResult) {
  if (job.overall_risk) return job.overall_risk
  if (job.state !== 'COMPLETE') return '待确认'
  if (job.finding_counts.critical > 0 || job.material_disagreement_count > 0) return '重大风险'
  if (job.finding_counts.high > 0) return '高风险'
  if (job.finding_counts.medium > 0) return '中风险'
  return '低风险'
}

function riskClass(risk: string) {
  if (risk === '低风险') return 'risk-low'
  if (risk === '中风险') return 'risk-medium'
  if (risk === '高风险') return 'risk-high'
  if (risk === '重大风险') return 'risk-critical'
  return 'risk-pending'
}

function friendlyFailure(job: BatchJobResult) {
  const detail = job.failure_detail ?? ''
  const code = job.failure_code ?? ''
  if (job.state === 'INVALID' || code === 'DOCUMENT_METADATA_INVALID') {
    return '本地记录不完整，不作为法律风险结论。'
  }
  if (job.pipeline_status === 'WAITING_EXTERNAL_SERVICE') {
    return '外部模型暂时不可用，已保存进度，可稍后继续。'
  }
  if (detail.includes('Server disconnected') || detail.includes('network') || detail.includes('Network')) {
    return '网络连接中断，已保存进度，可稍后重试。'
  }
  return detail || '本次处理未完成，重试会复用已完成阶段。'
}

export default function BatchResultsApp() {
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

  const refreshSoon = () => setReloadKey((value) => value + 1)

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
      setMessage(`${job.filename}：已继续处理。`)
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
      setMessage(`${job.filename}：已授权继续审计。`)
      refreshSoon()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法授权云端审计。')
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
      setMessage(`${job.filename}：${action.detail}`)
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
      setMessage(`${job.filename}：已重新开始。`)
      refreshSoon()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法重新开始审计。')
    } finally {
      setActionJobId(null)
    }
  }

  const total = summary?.total_jobs ?? 0
  const complete = summary?.complete_jobs ?? 0

  return (
    <main className="batch-results-shell">
      <header className="batch-results-header">
        <div>
          <p className="intake-eyebrow">LAW-RAG</p>
          <h1>批量审查结果</h1>
          <p>{summary ? `${complete}/${total} 份合同已完成审查。` : '正在读取本机审查批次。'}</p>
        </div>
        <div className="batch-results-header-actions">
          <a href="/">上传合同</a>
          <a href="/?settings=1" className="quiet-link">API 设置</a>
        </div>
      </header>

      {loading && <section className="batch-results-message">正在读取本机审查结果…</section>}
      {error && <section className="batch-results-message error">{error}</section>}
      {message && <section className="batch-results-message">{message}</section>}
      {!loading && !error && !summary && (
        <section className="batch-results-message">
          暂无可查看的审查批次。请先上传合同开始审查。 <a href="/">返回上传合同</a>
        </section>
      )}

      {summary && (
        <>
          <section className="batch-summary-grid compact" aria-label="批次状态摘要">
            <article><strong>{summary.complete_jobs}</strong><span>已完成</span></article>
            <article><strong>{summary.processing_jobs}</strong><span>分析中</span></article>
            <article><strong>{summary.waiting_jobs}</strong><span>等待继续</span></article>
            <article><strong>{summary.failed_jobs + summary.cancelled_jobs}</strong><span>未完成</span></article>
          </section>

          <section className="batch-results-list compact" aria-live="polite">
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
              const risk = riskText(job)
              return (
                <article className={`batch-result-card compact state-${job.state.toLowerCase()}`} key={job.job_id}>
                  <div className="batch-result-main">
                    <div className="batch-result-title-row">
                      <h2 title={job.filename}>{job.filename}</h2>
                      <div className="batch-row-badges">
                        <span className="batch-state-badge">{stateText(job)}</span>
                        <span className={`risk-level-badge ${riskClass(risk)}`}>{risk}</span>
                      </div>
                    </div>
                    {job.state === 'PROCESSING' && job.pipeline_status && (
                      <div className="batch-job-progress" aria-label={`处理进度 ${job.progress_percent}%`}>
                        <div style={{ width: `${job.progress_percent}%` }} />
                      </div>
                    )}
                    {job.state !== 'COMPLETE' && (job.failure_detail || job.pipeline_status === 'WAITING_EXTERNAL_SERVICE') && (
                      <p className="batch-job-problem">{friendlyFailure(job)}</p>
                    )}
                  </div>

                  <div className="batch-result-actions">
                    {job.state === 'COMPLETE' && (
                      <a href={`/workspace?job=${encodeURIComponent(job.job_id)}`}>查看报告</a>
                    )}
                    {waitingForProvider && (
                      <button type="button" onClick={() => void approveCloud(job)} disabled={actionJobId === job.job_id}>
                        授权继续
                      </button>
                    )}
                    {resumable && (
                      <button type="button" onClick={() => void resumeJob(job)} disabled={actionJobId === job.job_id}>
                        {actionJobId === job.job_id ? '启动中…' : '继续审查'}
                      </button>
                    )}
                    {job.state === 'CANCELLED' && (
                      <button type="button" onClick={() => void resumeCancelled(job)} disabled={actionJobId === job.job_id}>
                        重新开始
                      </button>
                    )}
                    {canCancel && (
                      <button type="button" className="danger-quiet" onClick={() => void cancelJob(job)} disabled={actionJobId === job.job_id}>
                        取消
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
