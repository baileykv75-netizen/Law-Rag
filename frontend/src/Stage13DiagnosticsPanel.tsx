import { useMemo, useState } from 'react'
import { API_BASE_URL } from './pipelineControlClient'

type DiagnosticState = 'IDLE' | 'LOADING' | 'AVAILABLE' | 'MISSING' | 'STALE' | 'INVALID' | 'ERROR'

type DiagnosticResult = {
  key: string
  label: string
  artifact: string
  endpoint: string
  state: DiagnosticState
  httpStatus: number | null
  payload: unknown
  detail: string
}

type DiagnosticDefinition = {
  key: string
  label: string
  artifact: string
  endpoint: (jobId: string) => string
}

const DEFINITIONS: DiagnosticDefinition[] = [
  {
    key: 'architecture',
    label: 'Architecture',
    artifact: 'job-architecture.json / pipeline shape',
    endpoint: (jobId) => `/api/documents/${jobId}/architecture`,
  },
  {
    key: 'pipeline',
    label: 'Pipeline',
    artifact: 'pipeline.json',
    endpoint: (jobId) => `/api/documents/${jobId}/pipeline`,
  },
  {
    key: 'audit-plan',
    label: 'Audit Plan · Stage 13B/C',
    artifact: 'audit-plan.json',
    endpoint: (jobId) => `/api/documents/${jobId}/audit-plan`,
  },
  {
    key: 'issue-legal-context',
    label: 'Issue Legal Context · Stage 13D',
    artifact: 'issue-legal-context.json',
    endpoint: (jobId) => `/api/documents/${jobId}/issue-legal-context`,
  },
  {
    key: 'issue-primary-audit',
    label: 'Issue Primary Audit · Stage 13E',
    artifact: 'issue-primary-audit.json',
    endpoint: (jobId) => `/api/documents/${jobId}/issue-primary-audit`,
  },
  {
    key: 'issue-secondary-review',
    label: 'Issue Secondary Review · Stage 13F',
    artifact: 'issue-secondary-review.json',
    endpoint: (jobId) => `/api/documents/${jobId}/issue-secondary-review`,
  },
  {
    key: 'issue-review-report',
    label: 'Issue Comparison · Stage 13G',
    artifact: 'issue-review-report.json',
    endpoint: (jobId) => `/api/documents/${jobId}/issue-review-report`,
  },
  {
    key: 'human-review',
    label: 'Human Review',
    artifact: 'human-review.json',
    endpoint: (jobId) => `/api/documents/${jobId}/human-review`,
  },
]

function responseDetail(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== 'object') return fallback
  const value = (payload as { detail?: unknown }).detail
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    const nested = value as { code?: unknown; detail?: unknown }
    const code = typeof nested.code === 'string' ? nested.code : ''
    const detail = typeof nested.detail === 'string' ? nested.detail : ''
    if (code || detail) return [code, detail].filter(Boolean).join(' · ')
  }
  return fallback
}

function stateForStatus(status: number): DiagnosticState {
  if (status === 404) return 'MISSING'
  if (status === 409) return 'STALE'
  if (status === 422) return 'INVALID'
  return 'ERROR'
}

function stateLabel(state: DiagnosticState) {
  if (state === 'AVAILABLE') return 'AVAILABLE'
  if (state === 'MISSING') return 'MISSING'
  if (state === 'STALE') return 'STALE / CONFLICT'
  if (state === 'INVALID') return 'INVALID'
  if (state === 'ERROR') return 'ERROR'
  if (state === 'LOADING') return 'LOADING'
  return 'NOT LOADED'
}

function prettyJson(value: unknown) {
  if (value === null || value === undefined) return ''
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export default function Stage13DiagnosticsPanel() {
  const initialJob = new URLSearchParams(window.location.search).get('job') ?? ''
  const [jobId, setJobId] = useState(initialJob)
  const [results, setResults] = useState<Record<string, DiagnosticResult>>({})
  const [activeKey, setActiveKey] = useState('audit-plan')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('输入 Job ID 后，只读取本机已保存的 Stage 13 产物。')

  const architecture = results.architecture?.payload as { architecture?: string; warnings?: string[] } | undefined
  const active = results[activeKey]
  const artifactRows = useMemo(
    () => DEFINITIONS.map((definition) => results[definition.key] ?? {
      key: definition.key,
      label: definition.label,
      artifact: definition.artifact,
      endpoint: definition.endpoint(jobId.trim()),
      state: 'IDLE' as DiagnosticState,
      httpStatus: null,
      payload: null,
      detail: '',
    }),
    [jobId, results],
  )

  const loadDiagnostics = async () => {
    const normalized = jobId.trim()
    if (!normalized || loading) return
    setLoading(true)
    setMessage('正在执行只读诊断；不会创建、重跑或调用任何模型阶段。')

    const entries = await Promise.all(DEFINITIONS.map(async (definition): Promise<[string, DiagnosticResult]> => {
      const endpoint = definition.endpoint(encodeURIComponent(normalized))
      try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, { method: 'GET' })
        const payload = await response.json().catch(() => null)
        if (response.ok) {
          return [definition.key, {
            key: definition.key,
            label: definition.label,
            artifact: definition.artifact,
            endpoint,
            state: 'AVAILABLE',
            httpStatus: response.status,
            payload,
            detail: '已读取本机持久化产物。',
          }]
        }
        return [definition.key, {
          key: definition.key,
          label: definition.label,
          artifact: definition.artifact,
          endpoint,
          state: stateForStatus(response.status),
          httpStatus: response.status,
          payload,
          detail: responseDetail(payload, `HTTP ${response.status}`),
        }]
      } catch (error) {
        return [definition.key, {
          key: definition.key,
          label: definition.label,
          artifact: definition.artifact,
          endpoint,
          state: 'ERROR',
          httpStatus: null,
          payload: null,
          detail: error instanceof Error ? error.message : '无法连接本机 Law-Rag 服务。',
        }]
      }
    }))

    const next = Object.fromEntries(entries)
    setResults(next)
    const arch = next.architecture?.payload as { architecture?: string } | undefined
    const available = entries.filter(([, value]) => value.state === 'AVAILABLE').length
    setMessage(
      arch?.architecture
        ? `权威架构 ${arch.architecture} · ${available}/${DEFINITIONS.length} 个诊断端点可读取。所有请求均为 GET。`
        : `${available}/${DEFINITIONS.length} 个诊断端点可读取；架构未能安全解析。`,
    )
    setLoading(false)
  }

  return (
    <section className="developer-stage13" aria-label="Stage 13 只读诊断">
      <header className="developer-stage13-header">
        <div>
          <p className="intake-eyebrow">STAGE 13 · READ ONLY</p>
          <h1>Issue 审计诊断</h1>
          <p>查看 AuditPlan、Issue Legal RAG、DeepSeek、Kimi、确定性比较与人工复核的原始持久化结果。</p>
        </div>
        <div className="developer-readonly-badge">GET ONLY · NO MODEL RUN</div>
      </header>

      <div className="developer-job-bar">
        <label>
          <span>Job ID</span>
          <input
            value={jobId}
            onChange={(event) => setJobId(event.target.value)}
            placeholder="粘贴 job_id，或使用 /developer?job=..."
          />
        </label>
        <button type="button" onClick={() => void loadDiagnostics()} disabled={!jobId.trim() || loading}>
          {loading ? '正在读取…' : '读取 Stage 13 诊断'}
        </button>
        {jobId.trim() && <a href={`/workspace?job=${encodeURIComponent(jobId.trim())}`}>打开工作台</a>}
      </div>

      <p className="developer-readonly-note">{message}</p>

      {architecture?.architecture === 'LEGACY_RC2' && (
        <div className="developer-architecture-warning">
          当前 Job 的权威架构是 LEGACY_RC2。Stage 13 产物缺失属于预期；请使用页面下方 Legacy / RC2 工具查看历史链。
        </div>
      )}
      {architecture?.architecture === 'CONFLICT' && (
        <div className="developer-architecture-warning danger">
          当前 Job 架构为 CONFLICT。诊断面板只展示服务器返回状态，不猜测哪套结果具有权威性。
        </div>
      )}

      <div className="developer-artifact-grid">
        {artifactRows.map((row) => (
          <button
            type="button"
            key={row.key}
            className={`developer-artifact-card state-${row.state.toLowerCase()}${activeKey === row.key ? ' active' : ''}`}
            onClick={() => setActiveKey(row.key)}
          >
            <strong>{row.label}</strong>
            <span>{row.artifact}</span>
            <small>{stateLabel(row.state)}{row.httpStatus ? ` · HTTP ${row.httpStatus}` : ''}</small>
          </button>
        ))}
      </div>

      <div className="developer-diagnostic-tabs" role="tablist" aria-label="Stage 13 原始产物">
        {DEFINITIONS.filter((item) => !['architecture', 'pipeline', 'human-review'].includes(item.key)).map((definition) => (
          <button
            type="button"
            key={definition.key}
            className={activeKey === definition.key ? 'active' : ''}
            onClick={() => setActiveKey(definition.key)}
          >
            {definition.label.replace(/ · Stage .*/, '')}
          </button>
        ))}
        <button type="button" className={activeKey === 'architecture' ? 'active' : ''} onClick={() => setActiveKey('architecture')}>Artifacts</button>
        <button type="button" className={activeKey === 'human-review' ? 'active' : ''} onClick={() => setActiveKey('human-review')}>Human Review</button>
      </div>

      <article className="developer-raw-panel">
        <div className="developer-raw-heading">
          <div>
            <strong>{active?.label ?? '选择一个诊断面板'}</strong>
            <span>{active?.artifact ?? '尚未读取'}</span>
          </div>
          {active && <code>{active.endpoint}</code>}
        </div>
        {active?.detail && active.state !== 'AVAILABLE' && <p className="developer-raw-error">{active.detail}</p>}
        {active?.payload ? (
          <pre>{prettyJson(active.payload)}</pre>
        ) : (
          <div className="developer-raw-empty">点击“读取 Stage 13 诊断”后显示服务器原始 JSON；这里没有 POST、重跑或 provider 调用。</div>
        )}
      </article>

      <details className="developer-artifact-index">
        <summary>查看全部 Artifact 状态</summary>
        <div>
          {artifactRows.map((row) => (
            <p key={row.key}>
              <strong>{row.artifact}</strong>
              <span>{stateLabel(row.state)}</span>
              <code>{row.endpoint}</code>
            </p>
          ))}
        </div>
      </details>
    </section>
  )
}
