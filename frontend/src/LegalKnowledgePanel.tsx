import { useCallback, useEffect, useMemo, useState } from 'react'

import { API_BASE_URL } from './apiBase'

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
  status: string
  effective_date: string
  end_date_exclusive: string | null
  coverage_type: 'FULL_TEXT' | 'CURATED_EXCERPT'
  coverage_note: string | null
  source_refs: SourceRef[]
}

type LegalAuthority = {
  authority_id: string
  title: string
  authority_type: 'LAW' | 'ADMINISTRATIVE_REGULATION' | 'JUDICIAL_INTERPRETATION'
  issuing_body: string
  document_number: string | null
  jurisdiction: string
}

type AuthoritySummary = {
  authority: LegalAuthority
  versions: LegalVersion[]
  article_count: number
}

type LegalArticleItem = {
  authority: LegalAuthority
  version: LegalVersion
  article: {
    article_token: string
    text: string
    heading_context: string[]
  }
}

type LoadState = 'loading' | 'ready' | 'empty' | 'error'

function typeLabel(value: LegalAuthority['authority_type']) {
  if (value === 'LAW') return '法律'
  if (value === 'ADMINISTRATIVE_REGULATION') return '行政法规'
  return '司法解释'
}

function coverageLabel(value: LegalVersion['coverage_type']) {
  return value === 'FULL_TEXT' ? '全文' : '核验选摘'
}

export default function LegalKnowledgePanel() {
  const [state, setState] = useState<LoadState>('loading')
  const [message, setMessage] = useState('正在读取法律知识库…')
  const [summary, setSummary] = useState<LegalStoreSummary | null>(null)
  const [authorities, setAuthorities] = useState<AuthoritySummary[]>([])
  const [articles, setArticles] = useState<LegalArticleItem[]>([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<LegalArticleItem | null>(null)

  const loadArticles = useCallback(async (keyword: string) => {
    const params = new URLSearchParams()
    if (keyword.trim()) params.set('query', keyword.trim())
    params.set('limit', '80')
    const response = await fetch(`${API_BASE_URL}/api/legal/articles?${params.toString()}`)
    const body = await response.json().catch(() => null)
    if (!response.ok) throw new Error(body?.detail ?? `条文读取失败（HTTP ${response.status}）。`)
    const next = body as LegalArticleItem[]
    setArticles(next)
    setSelected(next[0] ?? null)
  }, [])

  const refresh = useCallback(async () => {
    setState('loading')
    setMessage('正在读取法律知识库…')
    try {
      const summaryResponse = await fetch(`${API_BASE_URL}/api/legal/summary`)
      const summaryBody = await summaryResponse.json().catch(() => null)
      if (!summaryResponse.ok) throw new Error(summaryBody?.detail ?? `法律库检查失败（HTTP ${summaryResponse.status}）。`)
      const nextSummary = summaryBody as LegalStoreSummary
      setSummary(nextSummary)
      if (!nextSummary.ready) {
        setAuthorities([])
        setArticles([])
        setSelected(null)
        setState('empty')
        setMessage('法律库尚未构建。')
        return
      }

      const authorityResponse = await fetch(`${API_BASE_URL}/api/legal/authorities`)
      const authorityBody = await authorityResponse.json().catch(() => null)
      if (!authorityResponse.ok) throw new Error(authorityBody?.detail ?? `法源读取失败（HTTP ${authorityResponse.status}）。`)
      setAuthorities(authorityBody as AuthoritySummary[])
      await loadArticles(query)
      setState('ready')
      setMessage('法律知识库已就绪。')
    } catch (error) {
      setState('error')
      setMessage(error instanceof Error ? error.message : '法律知识库无法读取。')
    }
  }, [loadArticles, query])

  useEffect(() => {
    void refresh()
    // Initial load only; search has its own explicit submit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filteredAuthorities = useMemo(() => {
    const term = query.trim()
    if (!term) return authorities
    return authorities.filter((item) =>
      `${item.authority.title} ${item.authority.issuing_body} ${item.authority.document_number ?? ''}`.includes(term),
    )
  }, [authorities, query])

  const search = async () => {
    try {
      setMessage('正在搜索条文…')
      await loadArticles(query)
      setMessage('搜索完成。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '条文搜索失败。')
    }
  }

  return (
    <main className="legal-browser-shell">
      <header className="legal-browser-header">
        <div>
          <p className="intake-eyebrow">LAW-RAG</p>
          <h1>法律知识库</h1>
          <p>查看本机内置的法规和条文，审查报告中的法律依据来自这里。</p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={state === 'loading'}>
          {state === 'loading' ? '刷新中…' : '刷新'}
        </button>
      </header>

      {summary?.ready && (
        <section className="legal-browser-metrics">
          <article><span>法规</span><strong>{summary.authority_count}</strong></article>
          <article><span>版本</span><strong>{summary.version_count}</strong></article>
          <article><span>条文</span><strong>{summary.article_count}</strong></article>
          <article><span>当前有效</span><strong>{summary.effective_version_count}</strong></article>
        </section>
      )}

      <section className={`batch-results-message ${state === 'error' ? 'error' : ''}`}>{message}</section>

      <section className="legal-browser-search">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索法规名称、条号或关键词" />
        <button type="button" onClick={() => void search()} disabled={state !== 'ready'}>
          搜索
        </button>
      </section>

      <section className="legal-browser-layout">
        <aside className="legal-authority-list" aria-label="法规列表">
          {filteredAuthorities.map((item) => (
            <article key={item.authority.authority_id}>
              <strong>{item.authority.title}</strong>
              <span>{typeLabel(item.authority.authority_type)} · {item.article_count} 条</span>
              {item.versions.map((version) => (
                <small key={version.version_id}>
                  {version.effective_date} 起 · {coverageLabel(version.coverage_type)}
                </small>
              ))}
            </article>
          ))}
        </aside>

        <section className="legal-article-browser" aria-label="条文列表">
          <div className="legal-article-list">
            {articles.map((item) => (
              <button
                type="button"
                className={selected === item ? 'is-active' : ''}
                key={`${item.authority.authority_id}-${item.version.version_id}-${item.article.article_token}`}
                onClick={() => setSelected(item)}
              >
                <strong>{item.authority.title} · {item.article.article_token}</strong>
                <span>{item.article.text}</span>
              </button>
            ))}
            {state === 'ready' && articles.length === 0 && <p className="report-muted">没有匹配条文。</p>}
          </div>

          <article className="legal-article-detail">
            {selected ? (
              <>
                <span className="report-kicker">{coverageLabel(selected.version.coverage_type)}</span>
                <h2>{selected.authority.title}</h2>
                <h3>{selected.article.article_token}</h3>
                <p>{selected.article.text}</p>
                <div className="legal-detail-meta">
                  <span>{selected.authority.issuing_body}</span>
                  <span>{selected.version.effective_date} 起施行</span>
                  {selected.authority.document_number && <span>{selected.authority.document_number}</span>}
                </div>
                {selected.version.source_refs.map((source) => (
                  <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.name}</a>
                ))}
              </>
            ) : (
              <p className="report-muted">选择一条法条查看完整内容。</p>
            )}
          </article>
        </section>
      </section>
    </main>
  )
}
