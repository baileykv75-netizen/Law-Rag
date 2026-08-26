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
    legal_evidence_id: string
  }
}

type LegalPackTreeNode = {
  pack_id: string
  display_name: string
  description: string
  state: 'INSTALLED' | 'AVAILABLE' | 'DOWNLOADING' | 'FAILED' | 'ADAPTER_PENDING'
  authority_count: number
  installed_authority_count: number
  law_refs: string[]
  adapter_note: string | null
  source_refs: Array<{ name: string; url: string }>
  children: LegalPackTreeNode[]
}

type LegalPackDownloadTask = {
  task_id: string
  pack_id: string
  state: 'QUEUED' | 'RUNNING' | 'COMPLETE' | 'FAILED'
  message: string
  progress_percent: number
  result: {
    state: 'INSTALLED' | 'FAILED' | 'UNAVAILABLE'
    summary: LegalStoreSummary
    imported_records: number
    no_change_records: number
    rejected_records: number
  } | null
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

function versionStatusLabel(value: string) {
  if (value === 'EFFECTIVE') return '现行有效'
  if (value === 'NOT_YET_EFFECTIVE') return '已公布未生效'
  if (value === 'SUPERSEDED') return '已被替代'
  if (value === 'AMENDED') return '已修正'
  if (value === 'REPEALED') return '已废止'
  return '状态待核验'
}

function packStateLabel(value: LegalPackTreeNode['state']) {
  if (value === 'INSTALLED') return '已内置'
  if (value === 'AVAILABLE') return '可下载/更新'
  if (value === 'DOWNLOADING') return '下载中'
  if (value === 'FAILED') return '更新失败'
  return '待补充适配'
}

function defaultVersion(versions: LegalVersion[]) {
  const today = new Date().toISOString().slice(0, 10)
  return (
    versions.find((version) =>
      version.status === 'EFFECTIVE'
      && version.effective_date <= today
      && (!version.end_date_exclusive || today < version.end_date_exclusive),
    )
    ?? versions.find((version) => version.status === 'EFFECTIVE')
    ?? versions[0]
    ?? null
  )
}

function PackNode({
  node,
  onDownload,
  onSelect,
  working,
}: {
  node: LegalPackTreeNode
  onDownload: (packId: string) => void
  onSelect: (node: LegalPackTreeNode) => void
  working: boolean
}) {
  const canDownload = node.state === 'AVAILABLE'
  return (
    <article className={`legal-pack-node state-${node.state.toLowerCase()}`}>
      <div>
        <strong>{node.display_name}</strong>
        <span>{packStateLabel(node.state)}</span>
      </div>
      <p>{node.description}</p>
      <small>
        已安装 {node.installed_authority_count} / {node.authority_count || '待整理'} 项法源
      </small>
      {node.law_refs.length > 0 && (
        <div className="legal-pack-laws">
          {node.law_refs.slice(0, 8).map((name) => <span key={name}>{name}</span>)}
        </div>
      )}
      {node.adapter_note && <p className="legal-pack-note">{node.adapter_note}</p>}
      <div className="legal-pack-actions">
        <button type="button" onClick={() => onSelect(node)}>
          查看领域
        </button>
        <button type="button" disabled={!canDownload || working} onClick={() => onDownload(node.pack_id)}>
          {working ? '更新中…' : canDownload ? '一键下载/更新' : packStateLabel(node.state)}
        </button>
        {node.source_refs.slice(0, 2).map((source) => (
          <a key={source.url} href={source.url} target="_blank" rel="noreferrer">
            {source.name}
          </a>
        ))}
      </div>
      {node.children.length > 0 && (
        <div className="legal-pack-children">
          {node.children.map((child) => (
            <PackNode key={child.pack_id} node={child} onDownload={onDownload} onSelect={onSelect} working={working} />
          ))}
        </div>
      )}
    </article>
  )
}

export default function LegalKnowledgePanel() {
  const [state, setState] = useState<LoadState>('loading')
  const [message, setMessage] = useState('正在读取法律知识库…')
  const [summary, setSummary] = useState<LegalStoreSummary | null>(null)
  const [authorities, setAuthorities] = useState<AuthoritySummary[]>([])
  const [articles, setArticles] = useState<LegalArticleItem[]>([])
  const [packs, setPacks] = useState<LegalPackTreeNode[]>([])
  const [query, setQuery] = useState('')
  const [selectedAuthorityId, setSelectedAuthorityId] = useState<string | null>(null)
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [selected, setSelected] = useState<LegalArticleItem | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [workingPackId, setWorkingPackId] = useState<string | null>(null)
  const [selectedPack, setSelectedPack] = useState<LegalPackTreeNode | null>(null)

  const selectedAuthority = useMemo(
    () => authorities.find((item) => item.authority.authority_id === selectedAuthorityId) ?? null,
    [authorities, selectedAuthorityId],
  )
  const selectedVersion = useMemo(
    () => selectedAuthority?.versions.find((version) => version.version_id === selectedVersionId) ?? null,
    [selectedAuthority, selectedVersionId],
  )

  const loadArticles = useCallback(async (keyword: string, authorityId: string | null, versionId: string | null) => {
    const params = new URLSearchParams()
    if (keyword.trim()) params.set('query', keyword.trim())
    if (authorityId) params.set('authority_id', authorityId)
    if (versionId) params.set('version_id', versionId)
    params.set('limit', '1000')
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

      const [authorityResponse, packResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/legal/authorities`),
        fetch(`${API_BASE_URL}/api/legal/packs`),
      ])
      const authorityBody = await authorityResponse.json().catch(() => null)
      if (!authorityResponse.ok) throw new Error(authorityBody?.detail ?? `法源读取失败（HTTP ${authorityResponse.status}）。`)
      const packBody = await packResponse.json().catch(() => null)
      if (!packResponse.ok) throw new Error(packBody?.detail ?? `领域包读取失败（HTTP ${packResponse.status}）。`)

      const nextAuthorities = authorityBody as AuthoritySummary[]
      setAuthorities(nextAuthorities)
      setPacks(packBody as LegalPackTreeNode[])

      const nextAuthority =
        nextAuthorities.find((item) => item.authority.authority_id === selectedAuthorityId)
        ?? nextAuthorities[0]
        ?? null
      const nextVersion =
        nextAuthority?.versions.find((version) => version.version_id === selectedVersionId)
        ?? (nextAuthority ? defaultVersion(nextAuthority.versions) : null)
      setSelectedAuthorityId(nextAuthority?.authority.authority_id ?? null)
      setSelectedVersionId(nextVersion?.version_id ?? null)
      await loadArticles(query, nextAuthority?.authority.authority_id ?? null, nextVersion?.version_id ?? null)
      setState('ready')
      setMessage('法律知识库已就绪。')
    } catch (error) {
      setState('error')
      setMessage(error instanceof Error ? error.message : '法律知识库无法读取。')
    }
  }, [loadArticles, query, selectedAuthorityId, selectedVersionId])

  useEffect(() => {
    void refresh()
    // Initial load only; explicit refresh/search actions preserve cached pane state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filteredAuthorities = useMemo(() => {
    const term = query.trim()
    const packTerms = selectedPack?.law_refs ?? []
    return authorities.filter((item) => {
      const haystack = `${item.authority.title} ${item.authority.issuing_body} ${item.authority.document_number ?? ''}`
      const matchesQuery = !term || haystack.includes(term)
      const matchesPack = !packTerms.length || packTerms.some((law) => haystack.includes(law) || law.includes(item.authority.title))
      return matchesQuery && matchesPack
    })
  }, [authorities, query, selectedPack])

  const selectAuthority = async (item: AuthoritySummary) => {
    const nextVersion = defaultVersion(item.versions)
    setSelectedAuthorityId(item.authority.authority_id)
    setSelectedVersionId(nextVersion?.version_id ?? null)
    setMessage(`正在打开《${item.authority.title}》…`)
    try {
      await loadArticles(query, item.authority.authority_id, nextVersion?.version_id ?? null)
      setMessage(`已打开《${item.authority.title}》。`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '条文读取失败。')
    }
  }

  const selectVersion = async (versionId: string) => {
    setSelectedVersionId(versionId)
    try {
      await loadArticles(query, selectedAuthorityId, versionId)
      setMessage('版本已切换。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '条文读取失败。')
    }
  }

  const search = async () => {
    try {
      setMessage('正在搜索当前法规条文…')
      await loadArticles(query, selectedAuthorityId, selectedVersionId)
      setMessage('搜索完成。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '条文搜索失败。')
    }
  }

  const selectPack = (node: LegalPackTreeNode) => {
    setSelectedPack(node)
    setDrawerOpen(false)
    setMessage(`已按「${node.display_name}」筛选法规；未安装的法源可在领域抽屉中下载/更新。`)
  }

  const downloadPack = async (packId: string) => {
    setWorkingPackId(packId)
    setMessage('正在更新法律包并重建本地索引…')
    try {
      const response = await fetch(`${API_BASE_URL}/api/legal/packs/${packId}/download`, { method: 'POST' })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body?.detail
        throw new Error(typeof detail === 'string' ? detail : detail?.message ?? `法律包更新失败（HTTP ${response.status}）。`)
      }
      const task = body as LegalPackDownloadTask
      if (task.state === 'FAILED') {
        setMessage(task.message || '法律包暂时无法自动下载；可打开官方来源核验。')
      } else {
        setMessage(task.message || '法律包已更新。')
      }
      await refresh()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '法律包更新失败。')
    } finally {
      setWorkingPackId(null)
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
        <div className="legal-header-actions">
          <button type="button" onClick={() => setDrawerOpen(true)}>
            法规领域
          </button>
          <button type="button" onClick={() => void refresh()} disabled={state === 'loading'}>
            {state === 'loading' ? '刷新中…' : '刷新'}
          </button>
        </div>
      </header>

      {summary?.ready && (
        <>
          <section className="legal-browser-metrics">
            <article><span>法规库</span><strong>{summary.authority_count}</strong></article>
            <article><span>法规版本</span><strong>{summary.version_count}</strong></article>
            <article><span>条文总数</span><strong>{summary.article_count}</strong></article>
            <article><span>现行有效版本</span><strong>{summary.effective_version_count}</strong></article>
          </section>
          <p className="legal-metric-note">上方统计为本机法规库规模，不是当前搜索结果条数。</p>
        </>
      )}

      <section className={`batch-results-message ${state === 'error' ? 'error' : ''}`}>{message}</section>

      <section className="legal-browser-search">
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索法规名称、条号或当前法规关键词" />
        <button type="button" onClick={() => void search()} disabled={state !== 'ready'}>
          搜索
        </button>
      </section>
      {selectedPack && (
        <section className="legal-domain-filter">
          <div>
            <strong>{selectedPack.display_name}</strong>
            <span>{selectedPack.law_refs.length ? selectedPack.law_refs.join('、') : '该领域法源清单待补充。'}</span>
          </div>
          <button type="button" onClick={() => setSelectedPack(null)}>取消领域筛选</button>
        </section>
      )}

      <section className="legal-browser-layout">
        <aside className="legal-authority-list" aria-label="法规列表">
          {filteredAuthorities.map((item) => (
            <button
              type="button"
              className={item.authority.authority_id === selectedAuthorityId ? 'is-active' : ''}
              key={item.authority.authority_id}
              onClick={() => void selectAuthority(item)}
            >
              <strong>{item.authority.title}</strong>
              <span>{typeLabel(item.authority.authority_type)} · {item.article_count} 条</span>
              {item.versions.map((version) => (
                <small key={version.version_id}>
                  {version.effective_date} 起 · {versionStatusLabel(version.status)} · {coverageLabel(version.coverage_type)}
                </small>
              ))}
            </button>
          ))}
        </aside>

        <section className="legal-article-browser" aria-label="条文列表">
          <div className="legal-article-list">
            <div className="legal-article-toolbar">
              <strong>{selectedAuthority?.authority.title ?? '选择法规'}</strong>
              {selectedAuthority && (
                <select value={selectedVersionId ?? ''} onChange={(event) => void selectVersion(event.target.value)}>
                  {selectedAuthority.versions.map((version) => (
                    <option key={version.version_id} value={version.version_id}>
                      {version.effective_date} · {versionStatusLabel(version.status)}
                    </option>
                  ))}
                </select>
              )}
            </div>
            {articles.map((item) => (
              <button
                type="button"
                className={selected?.article.legal_evidence_id === item.article.legal_evidence_id ? 'is-active' : ''}
                key={item.article.legal_evidence_id}
                onClick={() => setSelected(item)}
              >
                <strong>{item.article.article_token}</strong>
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
                  <span>{versionStatusLabel(selected.version.status)}</span>
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

      {drawerOpen && (
        <div className="legal-pack-overlay" role="presentation" onClick={() => setDrawerOpen(false)}>
          <aside className="legal-pack-drawer" role="dialog" aria-modal="true" aria-label="法规领域" onClick={(event) => event.stopPropagation()}>
            <header>
              <div>
                <span className="report-kicker">法规领域</span>
                <h2>按合同领域扩展法律库</h2>
                <p>已整理的领域可直接安装/更新；待适配领域会保留官方来源入口。</p>
              </div>
              <button type="button" onClick={() => setDrawerOpen(false)}>关闭</button>
            </header>
            <div className="legal-pack-list">
              {packs.map((pack) => (
                <PackNode key={pack.pack_id} node={pack} onDownload={downloadPack} onSelect={selectPack} working={workingPackId === pack.pack_id} />
              ))}
            </div>
          </aside>
        </div>
      )}
    </main>
  )
}
