import { useCallback, useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type RetrievalChannel = 'EXACT' | 'LEXICAL' | 'SEMANTIC'
type RetrievalState =
  | 'OK'
  | 'PARTIAL_COVERAGE'
  | 'INSUFFICIENT_CORPUS'
  | 'NO_APPLICABLE_VERSION'
  | 'VERSION_AMBIGUOUS'
  | 'INDEX_NOT_READY'

type RetrievalIndexSummary = {
  ready: boolean
  schema_version: string | null
  legal_source_fingerprint: string | null
  lexical_ready: boolean
  lexical_tokenizer: string | null
  article_count: number
  semantic_ready: boolean
  semantic_provider: string | null
  semantic_model: string | null
  semantic_dimension: number | null
}

type ChannelScore = {
  channel: RetrievalChannel
  rank: number
  raw_score: number | null
  contribution: number
}

type Candidate = {
  legal_evidence_id: string
  authority_id: string
  authority_title: string
  version_id: string
  article_id: string
  article_token: string
  article_text: string
  coverage_type: 'FULL_TEXT' | 'CURATED_EXCERPT'
  effective_date: string
  end_date_exclusive: string | null
  exact_hit: boolean
  fused_score: number
  channels: ChannelScore[]
  matched_snippet: string | null
}

type RetrievalResponse = {
  schema_version: string
  engine_version: string
  query: string
  as_of: string
  state: RetrievalState
  channels_executed: RetrievalChannel[]
  candidates: Candidate[]
  warnings: string[]
  semantic_provider: string | null
  semantic_model: string | null
  lexical_index_version: string | null
}

type LoadState = 'loading' | 'ready' | 'empty' | 'error'
type SearchState = 'idle' | 'running' | 'success' | 'error'

function localToday() {
  const now = new Date()
  const offsetMs = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10)
}

function stateLabel(state: RetrievalState) {
  if (state === 'OK') return '检索完成'
  if (state === 'PARTIAL_COVERAGE') return '选摘语料命中'
  if (state === 'INSUFFICIENT_CORPUS') return '语料覆盖不足'
  if (state === 'NO_APPLICABLE_VERSION') return '无可确认适用版本'
  if (state === 'VERSION_AMBIGUOUS') return '版本存在歧义'
  return '索引未就绪'
}

function channelLabel(channel: RetrievalChannel) {
  if (channel === 'EXACT') return '精确'
  if (channel === 'LEXICAL') return 'BM25'
  return '语义'
}

export default function LegalRetrievalPanel() {
  const [indexState, setIndexState] = useState<LoadState>('loading')
  const [indexMessage, setIndexMessage] = useState('正在检查本地法律检索索引…')
  const [indexSummary, setIndexSummary] = useState<RetrievalIndexSummary | null>(null)
  const [query, setQuery] = useState('民法典第五百八十五条违约金')
  const [asOf, setAsOf] = useState(localToday())
  const [useSemantic, setUseSemantic] = useState(false)
  const [searchState, setSearchState] = useState<SearchState>('idle')
  const [searchMessage, setSearchMessage] = useState('')
  const [result, setResult] = useState<RetrievalResponse | null>(null)

  const refreshIndex = useCallback(async () => {
    setIndexState('loading')
    setIndexMessage('正在检查本地法律检索索引…')
    try {
      const response = await fetch(`${API_BASE_URL}/api/legal/retrieval/summary`)
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string'
          ? body.detail
          : `检索索引检查失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      const summary = body as RetrievalIndexSummary
      setIndexSummary(summary)
      if (!summary.ready) {
        setIndexState('empty')
        setIndexMessage('检索索引尚未构建或已与 legal.db 不一致。请运行 build-retrieval-index.bat。')
        setUseSemantic(false)
        return
      }
      setIndexState('ready')
      setIndexMessage(
        summary.semantic_ready
          ? 'Exact + FTS5/BM25 + 本地语义索引已就绪。'
          : 'Exact + FTS5/BM25 已就绪；语义通道尚未构建，基础检索仍可正常使用。',
      )
      if (!summary.semantic_ready) setUseSemantic(false)
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setIndexState('error')
      setIndexMessage(`检索索引无法检查：${detail}`)
    }
  }, [])

  useEffect(() => {
    void refreshIndex()
  }, [refreshIndex])

  const retrieve = async () => {
    if (!query.trim() || !asOf || searchState === 'running') return
    setSearchState('running')
    setSearchMessage('正在按指定日期解析法律版本并检索 Legal Evidence…')
    setResult(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/legal/retrieve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: query.trim(),
          as_of: asOf,
          top_k: 8,
          use_semantic: useSemantic && Boolean(indexSummary?.semantic_ready),
        }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string'
          ? body.detail
          : `法律检索失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      const next = body as RetrievalResponse
      setResult(next)
      setSearchState('success')
      setSearchMessage(`${stateLabel(next.state)}。返回 ${next.candidates.length} 条候选法律证据；检索结果本身不是法律结论。`)
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setSearchState('error')
      setSearchMessage(`法律检索无法运行：${detail}`)
    }
  }

  return (
    <section
      className="result-card"
      aria-label="法律检索"
      style={{ width: 'min(920px, calc(100% - 32px))', margin: '0 auto 40px' }}
    >
      <div className="result-heading">
        <div>
          <span className="meta-label">Hybrid Legal RAG · Stage 7</span>
          <h2>版本约束法律检索</h2>
        </div>
        <span className="success-pill">RETRIEVAL ONLY</span>
      </div>

      {indexSummary?.ready && (
        <div className="structure-metrics">
          <div><span>索引条文</span><strong>{indexSummary.article_count}</strong></div>
          <div><span>BM25</span><strong>{indexSummary.lexical_ready ? 'READY' : 'OFF'}</strong></div>
          <div><span>语义</span><strong>{indexSummary.semantic_ready ? 'READY' : 'OFF'}</strong></div>
          <div><span>维度</span><strong>{indexSummary.semantic_dimension ?? '—'}</strong></div>
        </div>
      )}

      <div className={`status status-${indexState === 'error' ? 'error' : 'ready'}`}>{indexMessage}</div>

      <div className="structure-section">
        <div className="section-label">检索请求</div>
        <label style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
          <span>问题 / 条款 / 明确法条引用</span>
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            rows={3}
            style={{ width: '100%', resize: 'vertical', padding: 12, borderRadius: 10 }}
          />
        </label>
        <label style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
          <span>法律适用日期（as_of）</span>
          <input
            type="date"
            value={asOf}
            onChange={(event) => setAsOf(event.target.value)}
            style={{ width: 'min(260px, 100%)', padding: 10, borderRadius: 10 }}
          />
        </label>
        <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14 }}>
          <input
            type="checkbox"
            checked={useSemantic}
            disabled={!indexSummary?.semantic_ready}
            onChange={(event) => setUseSemantic(event.target.checked)}
          />
          <span>启用本地语义通道</span>
        </label>
        <button
          className="primary-action"
          type="button"
          onClick={() => void retrieve()}
          disabled={!query.trim() || !asOf || searchState === 'running'}
        >
          {searchState === 'running' ? '正在检索…' : '检索法律依据'}
        </button>
        <button
          className="secondary-action"
          type="button"
          onClick={() => void refreshIndex()}
          disabled={indexState === 'loading'}
          style={{ marginLeft: 10 }}
        >
          刷新索引状态
        </button>
        {searchMessage && (
          <div className={`status status-${searchState === 'error' ? 'error' : 'ready'}`} style={{ marginTop: 12 }}>
            {searchMessage}
          </div>
        )}
      </div>

      {result && (
        <>
          <div className="structure-section">
            <div className="section-label">检索状态</div>
            <div className="page-route">
              <div>
                <strong>{stateLabel(result.state)}</strong>
                <span>as_of · {result.as_of}</span>
              </div>
              <div className="page-route-detail">
                <span>{result.channels_executed.map(channelLabel).join(' + ') || '无通道'}</span>
                <small>{result.engine_version}</small>
              </div>
            </div>
            {result.warnings.map((warning) => (
              <p className="stage-boundary" key={warning}>{warning}</p>
            ))}
          </div>

          <div className="structure-section">
            <div className="section-label">候选 Legal Evidence</div>
            {result.candidates.length === 0 && <p className="empty-note">当前语料没有可安全返回的候选证据。</p>}
            {result.candidates.map((candidate, index) => (
              <article className="rule-result" key={candidate.legal_evidence_id}>
                <div className="rule-result-heading">
                  <div>
                    <span className="mono">#{index + 1} · {candidate.legal_evidence_id}</span>
                    <h3>{candidate.authority_title} · {candidate.article_token}</h3>
                  </div>
                  <span className="success-pill">{candidate.exact_hit ? 'EXACT' : candidate.coverage_type}</span>
                </div>
                <p>{candidate.matched_snippet ?? candidate.article_text}</p>
                <div className="rule-meta">
                  <span>版本：<span className="mono">{candidate.version_id}</span></span>
                  <span>生效：{candidate.effective_date}</span>
                  <span>融合分：{candidate.fused_score.toFixed(5)}</span>
                </div>
                <div className="observed-values">
                  {candidate.channels.map((channel) => (
                    <span key={`${candidate.legal_evidence_id}-${channel.channel}`}>
                      <strong>{channelLabel(channel.channel)}</strong> rank #{channel.rank}
                      {channel.raw_score !== null ? ` · raw ${channel.raw_score.toFixed(4)}` : ''}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </>
      )}

      <p className="stage-boundary">
        Stage 7 只负责寻找版本匹配的法律证据，不判断合同是否违法、无效或高风险。当前公开 seed 为核验选摘，未命中不能解释为法律没有规定。
      </p>
    </section>
  )
}
