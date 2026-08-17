import { useEffect, useMemo, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type BatchJobState = 'PROCESSING' | 'WAITING' | 'FAILED' | 'COMPLETE' | 'INVALID'

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
    if (!job.pipeline_status) return '等待继续审计'
    return `处理中 · ${job.progress_percent}%`
  }
  if (job.state === 'WAITING') {
    if (job.pipeline_status === 'WAITING_OPTIONAL_COMPONENT') return '等待 OCR 组件'
    return '等待 API 配置'
  }
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

  const resumeJob = async (job: BatchJobResult) => {
    setActionJobId(job.job_id)
    setError(null)
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
            body: JSON.stringify({ as_of: localToday(), use_semantic: false }),
          })
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string }
        throw new Error(payload.detail ?? `无法继续审计（HTTP ${response.status}）。`)
      }
      setReloadKey((value) => value + 1)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '无法继续审计。')
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

      {summary && (
        <>
          <section className="batch-summary-grid" aria-label="批次审计摘要">
            <article><strong>{summary.total_jobs}</strong><span>合同总数</span></article>
            <article><strong>{summary.complete_jobs}</strong><span>已完成</span></article>
            <article><strong>{summary.human_review_required_jobs}</strong><span>需人工复核</span></article>
            <article><strong>{attentionJobs}</strong><span>优先关注</span></article>
            {(summary.waiting_jobs > 0 || summary.failed_jobs > 0 || summary.processing_jobs > 0) && (
              <article className="wide">
                <strong>{summary.processing_jobs} / {summary.waiting_jobs} / {summary.failed_jobs}</strong>
                <span>处理中 / 等待处理 / 失败或异常</span>
              </article>
            )}
          </section>

          <p className="batch-results-note">
            这里显示的是审计队列与风险提示，不是“合同正确率”或法律结论评分。最终判断仍应结合证据、适用法律版本和人工复核。应用被关闭后，正在运行的任务不会静默继续调用外部模型；重开后可在这里显式继续。
          </p>

          <section className="batch-results-list" aria-live="polite">
            {summary.jobs.map((job) => {
              const resumable = job.state !== 'COMPLETE' && job.state !== 'INVALID'
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
                  </div>

                  <div className="batch-result-actions">
                    {job.state === 'COMPLETE' && (
                      <a href={`/workspace?job=${encodeURIComponent(job.job_id)}`}>查看详细审计</a>
                    )}
                    {resumable && (
                      <button type="button" onClick={() => void resumeJob(job)} disabled={actionJobId === job.job_id}>
                        {actionJobId === job.job_id ? '正在启动…' : job.pipeline_status ? '继续 / 重试审计' : '启动后台审计'}
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
