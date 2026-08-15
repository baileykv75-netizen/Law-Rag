import { FormEvent, useEffect, useMemo, useState } from 'react'
import SourceViewerPane from './SourceViewerPane'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type ArtifactState = 'READY' | 'MISSING' | 'NOT_REQUIRED' | 'INVALID'
type OverallState = 'COMPLETE' | 'INCOMPLETE' | 'HUMAN_REVIEW_REQUIRED' | 'INVALID'

type WorkspaceStage = {
  stage: string
  label: string
  state: ArtifactState
  artifact: string | null
  detail: string
}

type WorkspaceDocument = {
  filename: string
  media_type: string
  document_kind: string
  page_count: number
  route: string
  native_text_pages: number
  ocr_required_pages: number
  ocr_used: boolean
  low_confidence_ocr_pages: number
  failed_ocr_pages: number
  no_text_ocr_pages: number
}

type WorkspaceReview = {
  primary_available: boolean
  primary_provider: string | null
  primary_model: string | null
  primary_finding_count: number
  secondary_available: boolean
  secondary_provider: string | null
  secondary_model: string | null
  secondary_review_count: number
  possible_omission_count: number
  comparison_available: boolean
  final_review_state: string | null
  agent_action_count: number
}

type WorkspaceSummary = {
  schema_version: string
  job_id: string
  overall_state: OverallState
  source_available: boolean
  document: WorkspaceDocument | null
  stages: WorkspaceStage[]
  review: WorkspaceReview
  source_uncertainty: string[]
  warnings: string[]
}

type LoadState = 'idle' | 'loading' | 'ready' | 'error'

function artifactLabel(state: ArtifactState) {
  if (state === 'READY') return '已就绪'
  if (state === 'NOT_REQUIRED') return '无需执行'
  if (state === 'INVALID') return '完整性异常'
  return '尚未完成'
}

function overallLabel(state: OverallState) {
  if (state === 'COMPLETE') return '审计链完整'
  if (state === 'HUMAN_REVIEW_REQUIRED') return '需要人工复核'
  if (state === 'INVALID') return '存在完整性异常'
  return '审计链未完成'
}

function stateClass(state: ArtifactState | OverallState) {
  if (state === 'READY' || state === 'COMPLETE') return 'is-ready'
  if (state === 'NOT_REQUIRED') return 'is-muted'
  if (state === 'HUMAN_REVIEW_REQUIRED') return 'is-review'
  if (state === 'INVALID') return 'is-invalid'
  return 'is-missing'
}

function initialJobId() {
  return new URLSearchParams(window.location.search).get('job') ?? ''
}

export default function WorkspaceApp() {
  const [jobId, setJobId] = useState(initialJobId)
  const [state, setState] = useState<LoadState>('idle')
  const [message, setMessage] = useState('输入一个本机 Job ID，工作台只读取既有审计产物，不会触发 OCR、检索或模型调用。')
  const [summary, setSummary] = useState<WorkspaceSummary | null>(null)

  const loadWorkspace = async (requestedJobId: string) => {
    const normalized = requestedJobId.trim()
    if (!normalized || state === 'loading') return

    setState('loading')
    setMessage('正在读取本机审计产物…')
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(normalized)}/workspace`)
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(detail)
      }
      const next = body as WorkspaceSummary
      setSummary(next)
      setJobId(next.job_id)
      setState('ready')
      setMessage('已读取本机 Stage 2–9 产物摘要；本次操作没有触发外部模型调用。')
      const url = new URL(window.location.href)
      url.pathname = '/workspace'
      url.searchParams.set('job', next.job_id)
      window.history.replaceState({}, '', url)
    } catch (error) {
      setSummary(null)
      setState('error')
      setMessage(error instanceof Error ? error.message : '无法读取工作台。')
    }
  }

  useEffect(() => {
    const initial = initialJobId()
    if (initial) void loadWorkspace(initial)
    // Load once from the URL. Subsequent loads are explicit form submissions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void loadWorkspace(jobId)
  }

  const attentionStages = useMemo(
    () => summary?.stages.filter((item) => item.state === 'MISSING' || item.state === 'INVALID') ?? [],
    [summary],
  )

  return (
    <main className="workstation-shell">
      <header className="workstation-topbar">
        <div className="workstation-brand">
          <span className="workstation-mark">LR</span>
          <div>
            <strong>Law-Rag</strong>
            <span>专业合同审计工作台</span>
          </div>
        </div>
        <div className="workstation-top-actions">
          <span className="local-only-chip">LOCAL · READ ONLY</span>
          <a href="/">返回开发控制台</a>
        </div>
      </header>

      <section className="workspace-loader" aria-label="打开审计任务">
        <form onSubmit={submit}>
          <label htmlFor="workspace-job-id">Job ID</label>
          <input
            id="workspace-job-id"
            value={jobId}
            onChange={(event) => setJobId(event.target.value)}
            placeholder="粘贴本机审计任务的 job_id"
            autoComplete="off"
          />
          <button type="submit" disabled={!jobId.trim() || state === 'loading'}>
            {state === 'loading' ? '读取中…' : '打开工作台'}
          </button>
        </form>
        <div className={`workspace-message ${state === 'error' ? 'is-error' : ''}`}>{message}</div>
      </section>

      {!summary ? (
        <section className="workspace-empty-state">
          <div className="empty-illustration">§</div>
          <h1>从一个已存在的审计任务开始</h1>
          <p>工作台不会因为打开页面而重新识别合同、重新检索法律或调用 DeepSeek / Kimi。</p>
        </section>
      ) : (
        <>
          <section className="workspace-summarybar">
            <div className="summary-document">
              <span className="eyebrow">CURRENT JOB</span>
              <h1>{summary.document?.filename ?? '文档元数据不可用'}</h1>
              <div className="summary-meta">
                <span>{summary.document ? `${summary.document.page_count} 页` : '页数未知'}</span>
                <span>{summary.document?.document_kind?.toUpperCase() ?? 'UNKNOWN'}</span>
                <span>{summary.document?.route ?? 'ROUTE UNKNOWN'}</span>
                <span className={summary.source_available ? 'source-ok' : 'source-broken'}>
                  {summary.source_available ? '源文件可用' : '源文件异常'}
                </span>
              </div>
            </div>
            <div className={`overall-state ${stateClass(summary.overall_state)}`}>
              <span>最终状态</span>
              <strong>{overallLabel(summary.overall_state)}</strong>
              <small>{summary.review.final_review_state ?? '尚无 Stage 9 最终状态'}</small>
            </div>
          </section>

          <section className="workstation-grid">
            <aside className="workstation-pane source-pane" aria-label="合同来源与处理链">
              <div className="pane-heading">
                <div>
                  <span className="eyebrow">SOURCE</span>
                  <h2>合同来源</h2>
                </div>
                <span>{summary.document?.page_count ?? '—'} 页</span>
              </div>

              {summary.document ? (
                <SourceViewerPane
                  jobId={summary.job_id}
                  pageCount={summary.document.page_count}
                  sourceAvailable={summary.source_available}
                />
              ) : (
                <div className="source-viewer-error">
                  <strong>文档元数据不可用</strong>
                  <p>没有可靠的页数/文档类型信息，工作台不会猜测源页。</p>
                </div>
              )}

              {summary.document && (
                <div className="document-facts">
                  <div><span>原生文本页</span><strong>{summary.document.native_text_pages}</strong></div>
                  <div><span>需要 OCR 页</span><strong>{summary.document.ocr_required_pages}</strong></div>
                  <div><span>实际使用 OCR</span><strong>{summary.document.ocr_used ? '是' : '否'}</strong></div>
                  <div><span>低置信 OCR 页</span><strong>{summary.document.low_confidence_ocr_pages}</strong></div>
                </div>
              )}

              <div className="stage-timeline">
                <div className="subheading">处理链</div>
                {summary.stages.map((item) => (
                  <div className="stage-row" key={`${item.stage}-${item.label}`}>
                    <span className={`stage-dot ${stateClass(item.state)}`} />
                    <div>
                      <strong>Stage {item.stage} · {item.label}</strong>
                      <span>{item.detail}</span>
                    </div>
                    <em className={stateClass(item.state)}>{artifactLabel(item.state)}</em>
                  </div>
                ))}
              </div>
            </aside>

            <section className="workstation-pane findings-pane" aria-label="审计结果概览">
              <div className="pane-heading">
                <div>
                  <span className="eyebrow">AUDIT QUEUE</span>
                  <h2>审计结果</h2>
                </div>
                <span>{summary.review.primary_finding_count} 项主审发现</span>
              </div>

              <div className="review-metrics">
                <article>
                  <span>DeepSeek 主审</span>
                  <strong>{summary.review.primary_finding_count}</strong>
                  <small>{summary.review.primary_available ? '报告已存在' : '尚未生成'}</small>
                </article>
                <article>
                  <span>Kimi 二审</span>
                  <strong>{summary.review.secondary_review_count}</strong>
                  <small>{summary.review.secondary_available ? '报告已存在' : '尚未生成'}</small>
                </article>
                <article className={summary.review.possible_omission_count > 0 ? 'needs-attention' : ''}>
                  <span>可能漏审项</span>
                  <strong>{summary.review.possible_omission_count}</strong>
                  <small>仍保持独立复核项</small>
                </article>
                <article className={summary.review.agent_action_count > 0 ? 'needs-attention' : ''}>
                  <span>Agent 动作</span>
                  <strong>{summary.review.agent_action_count}</strong>
                  <small>最多 2 个白名单动作</small>
                </article>
              </div>

              <div className="attention-block">
                <div className="subheading">当前需要关注</div>
                {attentionStages.length === 0 && summary.source_uncertainty.length === 0 ? (
                  <div className="quiet-state">Stage 2–9 摘要未发现缺失或损坏产物。</div>
                ) : (
                  <div className="attention-list">
                    {attentionStages.map((item) => (
                      <div className="attention-item" key={`attention-${item.stage}-${item.label}`}>
                        <span className={stateClass(item.state)}>{item.state}</span>
                        <div>
                          <strong>{item.label}</strong>
                          <p>{item.detail}</p>
                        </div>
                      </div>
                    ))}
                    {summary.source_uncertainty.map((item) => (
                      <div className="attention-item" key={item}>
                        <span className="is-review">SOURCE</span>
                        <div><strong>来源不确定性</strong><p>{item}</p></div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="next-stage-placeholder">
                <span className="eyebrow">10C</span>
                <strong>统一风险列表将在这里接入</strong>
                <p>下一步会把主审 finding、Kimi assessment、Comparison、漏审项和 Agent trace 合成可筛选的审计队列，但不会修改原始报告。</p>
              </div>
            </section>

            <aside className="workstation-pane evidence-pane" aria-label="证据与复核上下文">
              <div className="pane-heading">
                <div>
                  <span className="eyebrow">REVIEW CONTEXT</span>
                  <h2>证据与复核</h2>
                </div>
              </div>

              <div className="provider-card">
                <span>PRIMARY</span>
                <strong>{summary.review.primary_provider ?? '未生成'}</strong>
                <small>{summary.review.primary_model ?? '—'}</small>
              </div>
              <div className="provider-card">
                <span>SECONDARY</span>
                <strong>{summary.review.secondary_provider ?? '未生成'}</strong>
                <small>{summary.review.secondary_model ?? '—'}</small>
              </div>

              <div className={`final-review-card ${stateClass(summary.overall_state)}`}>
                <span>Stage 9 Final</span>
                <strong>{summary.review.final_review_state ?? '尚无最终比较报告'}</strong>
                <p>
                  {summary.review.comparison_available
                    ? '比较结果已持久化；打开工作台本身不会重新执行 Agent 或模型。'
                    : '需要先完成既有审计链，工作台不会自动替你补跑。'}
                </p>
              </div>

              <div className="warning-panel">
                <div className="subheading">完整性与警告</div>
                {summary.warnings.length === 0 ? (
                  <p className="quiet-state">暂无已持久化警告。</p>
                ) : (
                  <ul>
                    {summary.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                  </ul>
                )}
              </div>

              <div className="next-stage-placeholder compact">
                <span className="eyebrow">10C / 10D</span>
                <strong>法条、双模型比较与人工决定</strong>
                <p>源页和合同 Evidence 已在左侧接入；后续在此处加入 Legal Evidence、结构化分歧和人工确认/驳回/待复核记录。</p>
              </div>
            </aside>
          </section>
        </>
      )}
    </main>
  )
}
