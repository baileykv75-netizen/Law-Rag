import { useCallback, useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type LegalStoreSummary = {
  ready: boolean
  schema_version: string | null
  authority_count: number
  version_count: number
  article_count: number
  effective_version_count: number
  excerpt_version_count: number
}

type SourceRef = {
  name: string
  url: string
  role: 'PRIMARY' | 'TEXT' | 'METADATA' | 'CROSS_CHECK'
}

type LegalVersion = {
  authority_id: string
  version_id: string
  status: 'NOT_YET_EFFECTIVE' | 'EFFECTIVE' | 'SUPERSEDED' | 'AMENDED' | 'REPEALED' | 'UNKNOWN'
  publication_date: string | null
  effective_date: string
  end_date_exclusive: string | null
  coverage_type: 'FULL_TEXT' | 'CURATED_EXCERPT'
  coverage_note: string | null
  source_refs: SourceRef[]
  verified_on: string | null
}

type AuthoritySummary = {
  authority: {
    authority_id: string
    title: string
    authority_type: 'LAW' | 'ADMINISTRATIVE_REGULATION' | 'JUDICIAL_INTERPRETATION'
    issuing_body: string
    document_number: string | null
    jurisdiction: string
  }
  versions: LegalVersion[]
  article_count: number
}

type LoadState = 'loading' | 'ready' | 'empty' | 'error'

function coverageLabel(value: LegalVersion['coverage_type']) {
  return value === 'FULL_TEXT' ? '全文' : '核验选摘'
}

function authorityTypeLabel(value: AuthoritySummary['authority']['authority_type']) {
  if (value === 'LAW') return '法律'
  if (value === 'ADMINISTRATIVE_REGULATION') return '行政法规'
  return '司法解释'
}

export default function LegalKnowledgePanel() {
  const [state, setState] = useState<LoadState>('loading')
  const [message, setMessage] = useState('正在检查本地法律知识库…')
  const [summary, setSummary] = useState<LegalStoreSummary | null>(null)
  const [authorities, setAuthorities] = useState<AuthoritySummary[]>([])

  const refresh = useCallback(async () => {
    setState('loading')
    setMessage('正在检查本地法律知识库…')
    try {
      const summaryResponse = await fetch(`${API_BASE_URL}/api/legal/summary`)
      const summaryBody = await summaryResponse.json().catch(() => null)
      if (!summaryResponse.ok) {
        const detail = summaryBody && typeof summaryBody.detail === 'string'
          ? summaryBody.detail
          : `法律库检查失败（HTTP ${summaryResponse.status}）`
        throw new Error(detail)
      }

      const nextSummary = summaryBody as LegalStoreSummary
      setSummary(nextSummary)
      if (!nextSummary.ready) {
        setAuthorities([])
        setState('empty')
        setMessage('法律库尚未构建。请先在仓库根目录运行 rebuild-legal-seed.bat。')
        return
      }

      const authorityResponse = await fetch(`${API_BASE_URL}/api/legal/authorities`)
      const authorityBody = await authorityResponse.json().catch(() => null)
      if (!authorityResponse.ok) {
        const detail = authorityBody && typeof authorityBody.detail === 'string'
          ? authorityBody.detail
          : `法源读取失败（HTTP ${authorityResponse.status}）`
        throw new Error(detail)
      }
      setAuthorities(authorityBody as AuthoritySummary[])
      setState('ready')
      setMessage('本地版本化法律知识库已就绪。当前面板仅检查法源身份、版本和覆盖范围，不执行法律检索。')
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setState('error')
      setMessage(`法律知识库无法检查：${detail}`)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <section
      className="result-card"
      aria-label="法律知识库状态"
      style={{ width: 'min(920px, calc(100% - 32px))', margin: '0 auto 40px' }}
    >
      <div className="result-heading">
        <div>
          <span className="meta-label">Legal Evidence · Stage 6</span>
          <h2>版本化法律知识库</h2>
        </div>
        <span className="success-pill">{summary?.ready ? 'READY' : 'LOCAL'}</span>
      </div>

      {summary?.ready && (
        <div className="structure-metrics">
          <div><span>法源</span><strong>{summary.authority_count}</strong></div>
          <div><span>版本</span><strong>{summary.version_count}</strong></div>
          <div><span>条文</span><strong>{summary.article_count}</strong></div>
          <div><span>选摘版本</span><strong>{summary.excerpt_version_count}</strong></div>
        </div>
      )}

      <div className={`status status-${state === 'error' ? 'error' : 'ready'}`}>{message}</div>

      {state === 'empty' && (
        <button className="secondary-action" type="button" onClick={() => void refresh()}>
          重新检查法律库
        </button>
      )}

      {authorities.length > 0 && (
        <div className="structure-section">
          <div className="section-label">已核验法源</div>
          {authorities.map((item) => (
            <div className="page-route" key={item.authority.authority_id}>
              <div>
                <strong>{item.authority.title}</strong>
                <span className="mono">{item.authority.authority_id} · {authorityTypeLabel(item.authority.authority_type)}</span>
              </div>
              <div className="page-route-detail">
                <span>{item.article_count} 条</span>
                {item.versions.map((version) => (
                  <small key={version.version_id}>
                    {version.status} · {version.effective_date} 起 · {coverageLabel(version.coverage_type)}
                  </small>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {summary?.ready && summary.excerpt_version_count > 0 && (
        <p className="stage-boundary">
          当前 seed 明确包含选摘版本。缺少某条法条不能解释为“该法律不存在该规定”；Stage 7 检索必须继续携带覆盖范围信息。
        </p>
      )}

      <button className="secondary-action" type="button" onClick={() => void refresh()} disabled={state === 'loading'}>
        {state === 'loading' ? '正在检查…' : '刷新法律库状态'}
      </button>
    </section>
  )
}
