import { useCallback, useEffect, useState } from 'react'

import { API_BASE_URL } from './apiBase'

type ProviderHealth = {
  provider: string
  configured: boolean
  model: string
  base_url: string | null
  detail: string
}

type Finding = {
  finding_id: string
  state: 'SUPPORTED_FINDING' | 'NO_FINDING' | 'INSUFFICIENT_EVIDENCE' | 'REVIEW_REQUIRED'
  evidence_sufficiency: 'SUFFICIENT' | 'PARTIAL_CORPUS' | 'INSUFFICIENT_CORPUS' | 'VERSION_UNCERTAIN' | 'SOURCE_UNCERTAIN'
  risk_category: string
  severity: 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  title: string
  reasoning_summary: string
  suggestion: string
  issue_ids: string[]
  canonical_object_ids: string[]
  contract_evidence_ids: string[]
  legal_evidence_ids: string[]
  review_reasons: string[]
}

type AiAuditReport = {
  schema_version: string
  engine_version: string
  job_id: string
  status: string
  as_of: string
  provider: string
  model: string
  context_fingerprint: string
  raw_response_hash: string
  findings: Finding[]
  warnings: string[]
}

type PanelState = 'idle' | 'running' | 'success' | 'error'

function stateLabel(value: Finding['state']) {
  if (value === 'SUPPORTED_FINDING') return '有证据支持的发现'
  if (value === 'NO_FINDING') return '未形成发现'
  if (value === 'INSUFFICIENT_EVIDENCE') return '证据不足'
  return '需要复核'
}

export default function PrimaryAuditPanel() {
  const [health, setHealth] = useState<ProviderHealth | null>(null)
  const [healthMessage, setHealthMessage] = useState('正在检查 DeepSeek 配置…')
  const [jobId, setJobId] = useState('')
  const [asOf, setAsOf] = useState('2026-08-15')
  const [useSemantic, setUseSemantic] = useState(false)
  const [state, setState] = useState<PanelState>('idle')
  const [message, setMessage] = useState('')
  const [report, setReport] = useState<AiAuditReport | null>(null)

  const refreshHealth = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/ai/providers/health?provider=deepseek`)
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
      setHealthMessage(`无法检查 provider：${detail}`)
    }
  }, [])

  useEffect(() => {
    void refreshHealth()
  }, [refreshHealth])

  const runAudit = async () => {
    if (!jobId.trim() || state === 'running') return
    setState('running')
    setMessage('正在构造证据包、执行法律检索并调用主审模型…')
    setReport(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId.trim())}/ai-audit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ as_of: asOf, provider: 'deepseek', use_semantic: useSemantic }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `主审失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      setReport(body as AiAuditReport)
      setState('success')
      setMessage('主审输出已通过结构与证据 ID 校验，并保存到本机 ai-audit.json。')
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setState('error')
      setMessage(`主审无法完成：${detail}`)
    }
  }

  const loadReport = async () => {
    if (!jobId.trim() || state === 'running') return
    setState('running')
    setMessage('正在读取本机 ai-audit.json…')
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId.trim())}/ai-audit`)
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `读取失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      setReport(body as AiAuditReport)
      setState('success')
      setMessage('已读取本机保存的主审报告。')
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setState('error')
      setMessage(`无法读取报告：${detail}`)
    }
  }

  return (
    <section className="result-card" aria-label="主模型合同审计" style={{ width: 'min(920px, calc(100% - 32px))', margin: '0 auto 40px' }}>
      <div className="result-heading">
        <div>
          <span className="meta-label">Primary AI Audit · Stage 8</span>
          <h2>证据约束主审</h2>
        </div>
        <span className="success-pill">{health?.configured ? 'READY' : 'CONFIG'}</span>
      </div>

      <div className="status status-ready">
        {health ? `${health.provider} · ${health.model} · ${health.configured ? '已配置' : '未配置'}。${healthMessage}` : healthMessage}
      </div>

      <p className="stage-boundary">
        点击“运行主审”后，Law-Rag 只发送程序选出的合同证据、规则上下文和检索到的法律证据给已配置的 DeepSeek API；不会把 API Key 写入报告。当前结果仍是 AI 辅助分析，不是最终法律意见。
      </p>

      <div style={{ display: 'grid', gap: 12, margin: '18px 0' }}>
        <label>
          <span className="meta-label">Job ID</span>
          <input value={jobId} onChange={(event) => setJobId(event.target.value)} placeholder="粘贴当前合同的 job_id" style={{ width: '100%', padding: 10 }} />
        </label>
        <label>
          <span className="meta-label">法律适用日期 as_of</span>
          <input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} style={{ padding: 10 }} />
        </label>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input type="checkbox" checked={useSemantic} onChange={(event) => setUseSemantic(event.target.checked)} />
          使用已构建的本地 BGE 语义检索；未构建时建议保持关闭，仅使用 Exact + BM25
        </label>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button className="primary-action" type="button" onClick={() => void runAudit()} disabled={!jobId.trim() || !asOf || state === 'running' || !health?.configured}>
          {state === 'running' ? '处理中…' : '运行 DeepSeek 主审'}
        </button>
        <button className="secondary-action" type="button" onClick={() => void loadReport()} disabled={!jobId.trim() || state === 'running'}>
          读取已保存报告
        </button>
        <button className="secondary-action" type="button" onClick={() => void refreshHealth()}>
          刷新 Provider 状态
        </button>
      </div>

      {message && <div className={`status status-${state === 'error' ? 'error' : 'ready'}`} style={{ marginTop: 14 }}>{message}</div>}

      {report && (
        <div className="structure-section" style={{ marginTop: 20 }}>
          <div className="section-label">主审结果 · {report.provider} / {report.model} · as_of {report.as_of}</div>
          {report.findings.length === 0 && <p>模型没有返回 finding；请结合覆盖范围与上下文警告人工判断。</p>}
          {report.findings.map((finding) => (
            <div className="page-route" key={finding.finding_id} style={{ alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <strong>{finding.title}</strong>
                <span>{stateLabel(finding.state)} · {finding.severity} · {finding.risk_category} · {finding.evidence_sufficiency}</span>
                <p>{finding.reasoning_summary}</p>
                <p><strong>建议：</strong>{finding.suggestion}</p>
                {finding.review_reasons.length > 0 && <small>复核原因：{finding.review_reasons.join(' · ')}</small>}
                {finding.contract_evidence_ids.length > 0 && <small className="mono">Contract Evidence: {finding.contract_evidence_ids.join(' · ')}</small>}
                {finding.legal_evidence_ids.length > 0 && <small className="mono">Legal Evidence: {finding.legal_evidence_ids.join(' · ')}</small>}
              </div>
            </div>
          ))}
          {report.warnings.length > 0 && (
            <p className="stage-boundary">上下文/检索警告：{report.warnings.join(' ｜ ')}</p>
          )}
        </div>
      )}
    </section>
  )
}
