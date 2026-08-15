import { useCallback, useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type ProviderHealth = {
  provider: string
  configured: boolean
  model: string
  base_url: string | null
  detail: string
}

type SecondaryReview = {
  review_id: string
  primary_finding_id: string
  assessment: 'SUPPORTED' | 'NOT_SUPPORTED' | 'REVIEW_REQUIRED' | 'INSUFFICIENT_EVIDENCE'
  severity: 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  reasoning_summary: string
  suggestion: string
  contract_evidence_ids: string[]
  legal_evidence_ids: string[]
  disagreement_categories: string[]
  review_reasons: string[]
}

type SecondaryReport = {
  job_id: string
  as_of: string
  provider: string
  model: string
  finding_reviews: SecondaryReview[]
  possible_omissions: Array<{
    omission_id: string
    risk_category: string
    severity: string
    title: string
    reasoning_summary: string
    contract_evidence_ids: string[]
    legal_evidence_ids: string[]
  }>
  warnings: string[]
}

type EvidenceSetComparison = {
  state: string
  shared: string[]
  primary_only: string[]
  secondary_only: string[]
}

type FindingComparison = {
  comparison_id: string
  primary_finding_id: string
  risk_state: string
  severity: { primary: string; secondary: string; distance: number; state: string }
  contract_evidence: EvidenceSetComparison
  legal_basis: EvidenceSetComparison
  overall_state: string
  material_reasons: string[]
  follow_up: string
}

type ReviewReport = {
  job_id: string
  as_of: string
  final_state: 'DUAL_MODEL_AGREEMENT' | 'MINOR_DISAGREEMENT' | 'HUMAN_REVIEW_REQUIRED'
  primary_provider: string
  primary_model: string
  secondary_provider: string
  secondary_model: string
  comparison: {
    overall_state: string
    follow_up: string
    finding_comparisons: FindingComparison[]
    omission_comparisons: Array<{ omission_id: string; risk_category: string; severity: string; reason: string }>
  }
  action_trace: Array<{
    action_id: string
    cycle: number
    tool_name: string
    state: string
    reason: string
    input_evidence_ids: string[]
    output_evidence_ids: string[]
    provider_call_occurred: boolean
    private_contract_evidence_left_machine: boolean
    validation_or_error: string | null
  }>
  evidence_gathered: boolean
  final_reasons: string[]
  warnings: string[]
}

type PanelState = 'idle' | 'running-secondary' | 'building-report' | 'success' | 'error'

function finalStateLabel(state: ReviewReport['final_state']) {
  if (state === 'DUAL_MODEL_AGREEMENT') return '双模型一致'
  if (state === 'MINOR_DISAGREEMENT') return '轻度分歧'
  return '需要人工复核'
}

export default function SecondaryReviewPanel() {
  const [health, setHealth] = useState<ProviderHealth | null>(null)
  const [healthMessage, setHealthMessage] = useState('正在检查 Kimi 配置…')
  const [jobId, setJobId] = useState('')
  const [useSemantic, setUseSemantic] = useState(false)
  const [state, setState] = useState<PanelState>('idle')
  const [message, setMessage] = useState('')
  const [secondary, setSecondary] = useState<SecondaryReport | null>(null)
  const [report, setReport] = useState<ReviewReport | null>(null)

  const refreshHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/ai/secondary/health?provider=kimi`)
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(detail)
      }
      const next = body as ProviderHealth
      setHealth(next)
      setHealthMessage(next.detail)
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setHealth(null)
      setHealthMessage(`无法检查 Kimi：${detail}`)
    }
  }, [])

  useEffect(() => {
    void refreshHealth()
  }, [refreshHealth])

  const runSecondary = async () => {
    if (!jobId.trim() || state.startsWith('running') || state === 'building-report') return
    setState('running-secondary')
    setMessage('正在将与 Stage 8 完全一致的受控证据包发送给 Kimi K3 做一次合同级独立复核…')
    setReport(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId.trim())}/secondary-review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: 'kimi', use_semantic: useSemantic }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `Kimi 二审失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      setSecondary(body as SecondaryReport)
      setState('success')
      setMessage('Kimi 二审已通过独立 Evidence/法律版本校验并保存到本机 secondary-review.json。')
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setState('error')
      setMessage(`二审无法完成：${detail}`)
    }
  }

  const buildFinalReport = async () => {
    if (!jobId.trim() || state === 'running-secondary' || state === 'building-report') return
    setState('building-report')
    setMessage('正在本地比较 DeepSeek 与 Kimi，并按需执行最多 2 个白名单证据工具；不会再次调用模型…')
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId.trim())}/review-report`, {
        method: 'POST',
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `生成报告失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      setReport(body as ReviewReport)
      setState('success')
      setMessage('双模型结构化比较与本地 Agent 补证据已完成，review-report.json 已保存。')
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setState('error')
      setMessage(`无法生成比较报告：${detail}`)
    }
  }

  const loadFinalReport = async () => {
    if (!jobId.trim() || state === 'running-secondary' || state === 'building-report') return
    setState('building-report')
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId.trim())}/review-report`)
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `读取失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      setReport(body as ReviewReport)
      setState('success')
      setMessage('已读取本机 review-report.json。')
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setState('error')
      setMessage(`无法读取比较报告：${detail}`)
    }
  }

  const busy = state === 'running-secondary' || state === 'building-report'

  return (
    <section className="result-card" aria-label="Kimi 二审与双模型比较" style={{ width: 'min(920px, calc(100% - 32px))', margin: '0 auto 40px' }}>
      <div className="result-heading">
        <div>
          <span className="meta-label">Secondary Review + Constrained Agent · Stage 9</span>
          <h2>DeepSeek × Kimi 双模型复核</h2>
        </div>
        <span className="success-pill">{health?.configured ? 'KIMI READY' : 'KIMI CONFIG'}</span>
      </div>

      <div className="status status-ready">
        {health ? `${health.provider} · ${health.model} · ${health.configured ? '已配置' : '未配置'}。${healthMessage}` : healthMessage}
      </div>

      <p className="stage-boundary">
        “运行 Kimi 二审”会发生一次外部模型调用；“生成双模型比较报告”只在本机比较结构字段并运行最多两个白名单证据工具，不会自动调用第三个模型。实质分歧不会由程序擅自投票决定，而会进入人工复核。
      </p>

      <div style={{ display: 'grid', gap: 12, margin: '18px 0' }}>
        <label>
          <span className="meta-label">Job ID</span>
          <input value={jobId} onChange={(event) => setJobId(event.target.value)} placeholder="粘贴已完成 Stage 8 的 job_id" style={{ width: '100%', padding: 10 }} />
        </label>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input type="checkbox" checked={useSemantic} onChange={(event) => setUseSemantic(event.target.checked)} />
          Stage 8 若启用了本地 BGE 语义检索，这里也必须保持开启以复现相同 context fingerprint
        </label>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button className="primary-action" type="button" onClick={() => void runSecondary()} disabled={!jobId.trim() || busy || !health?.configured}>
          {state === 'running-secondary' ? 'Kimi 复核中…' : '运行 Kimi 二审（1次外部调用）'}
        </button>
        <button className="secondary-action" type="button" onClick={() => void buildFinalReport()} disabled={!jobId.trim() || busy}>
          {state === 'building-report' ? '本地处理中…' : '生成双模型比较报告（仅本地）'}
        </button>
        <button className="secondary-action" type="button" onClick={() => void loadFinalReport()} disabled={!jobId.trim() || busy}>
          读取已保存 review-report
        </button>
        <button className="secondary-action" type="button" onClick={() => void refreshHealth()} disabled={busy}>
          刷新 Kimi 状态
        </button>
      </div>

      {message && <div className={`status status-${state === 'error' ? 'error' : 'ready'}`} style={{ marginTop: 14 }}>{message}</div>}

      {secondary && (
        <div className="structure-section" style={{ marginTop: 20 }}>
          <div className="section-label">Kimi 二审 · {secondary.provider} / {secondary.model}</div>
          {secondary.finding_reviews.map((review) => (
            <div className="page-route" key={review.review_id} style={{ alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <strong>{review.primary_finding_id}</strong>
                <span>{review.assessment} · {review.severity}</span>
                <p>{review.reasoning_summary}</p>
                <p><strong>建议：</strong>{review.suggestion}</p>
                {review.disagreement_categories.length > 0 && <small>模型自述比较标签：{review.disagreement_categories.join(' · ')}</small>}
              </div>
            </div>
          ))}
          {secondary.possible_omissions.length > 0 && <p className="stage-boundary">Kimi 提出了 {secondary.possible_omissions.length} 个可能的主审漏项；它们仍需程序证据校验与后续复核。</p>}
        </div>
      )}

      {report && (
        <div className="structure-section" style={{ marginTop: 20 }}>
          <div className="section-label">最终比较 · {finalStateLabel(report.final_state)} · {report.comparison.overall_state}</div>
          {report.comparison.finding_comparisons.map((comparison) => (
            <div className="page-route" key={comparison.comparison_id} style={{ alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <strong>{comparison.primary_finding_id}</strong>
                <span>{comparison.overall_state} · risk={comparison.risk_state} · severity={comparison.severity.primary}/{comparison.severity.secondary}</span>
                <small>合同证据：{comparison.contract_evidence.state} ｜ 法律依据：{comparison.legal_basis.state}</small>
                {comparison.material_reasons.length > 0 && <small>实质原因：{comparison.material_reasons.join(' · ')}</small>}
              </div>
            </div>
          ))}

          {report.action_trace.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div className="section-label">Agent 本地动作轨迹</div>
              {report.action_trace.map((action) => (
                <div className="page-route" key={action.action_id}>
                  <div>
                    <strong>Cycle {action.cycle} · {action.tool_name}</strong>
                    <span>{action.state} · {action.reason}</span>
                    <small>输入 Evidence: {action.input_evidence_ids.join(' · ') || '无'} ｜ 输出 Evidence: {action.output_evidence_ids.join(' · ') || '无'}</small>
                    <small>外部调用：{action.provider_call_occurred ? '是' : '否'} ｜ 私有合同证据离开本机：{action.private_contract_evidence_left_machine ? '是' : '否'}</small>
                    {action.validation_or_error && <small>{action.validation_or_error}</small>}
                  </div>
                </div>
              ))}
            </div>
          )}

          <p className="stage-boundary">
            最终状态：{finalStateLabel(report.final_state)}。{report.final_reasons.length > 0 ? ` 原因：${report.final_reasons.join(' ｜ ')}` : ''}
          </p>
        </div>
      )}
    </section>
  )
}
