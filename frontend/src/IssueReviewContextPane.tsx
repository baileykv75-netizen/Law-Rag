import { useEffect, useMemo, useState } from 'react'
import type { IssueWorkspaceDetail } from './issue-workspace-types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type LegalEvidenceRecord = {
  authority: { title: string }
  version: {
    version_id: string
    effective_date: string
    end_date_exclusive: string | null
    coverage_type: 'FULL_TEXT' | 'CURATED_EXCERPT'
    coverage_note: string | null
    source_refs: Array<{ name: string; url: string; role: string }>
  }
  article: {
    article_token: string
    text: string
    legal_evidence_id: string
  }
}

type Props = {
  detail: IssueWorkspaceDetail | null
  loading: boolean
  message: string
  onContractEvidence: (evidenceId: string) => void
}

function unique(values: string[]) {
  return [...new Set(values)]
}

export default function IssueReviewContextPane({ detail, loading, message, onContractEvidence }: Props) {
  const [legalEvidenceId, setLegalEvidenceId] = useState<string | null>(null)
  const [legalEvidence, setLegalEvidence] = useState<LegalEvidenceRecord | null>(null)
  const [legalMessage, setLegalMessage] = useState('点击 Legal Evidence 查看本地版本化法条。')

  useEffect(() => {
    setLegalEvidenceId(null)
    setLegalEvidence(null)
    setLegalMessage('点击 Legal Evidence 查看本地版本化法条。')
  }, [detail?.issue_id])

  useEffect(() => {
    if (!legalEvidenceId) return
    let cancelled = false
    const load = async () => {
      setLegalEvidence(null)
      setLegalMessage('正在读取本地 Legal Evidence…')
      try {
        const response = await fetch(`${API_BASE_URL}/api/legal/evidence/${encodeURIComponent(legalEvidenceId)}`)
        const body = await response.json().catch(() => null)
        if (!response.ok) {
          const detailText = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
          throw new Error(detailText)
        }
        if (!cancelled) {
          setLegalEvidence(body as LegalEvidenceRecord)
          setLegalMessage('已读取本地版本化法律证据。')
        }
      } catch (error) {
        if (!cancelled) setLegalMessage(error instanceof Error ? error.message : 'Legal Evidence 无法读取。')
      }
    }
    void load()
    return () => { cancelled = true }
  }, [legalEvidenceId])

  const contractEvidence = useMemo(() => {
    if (!detail) return []
    return unique([
      ...detail.plan_issue.contract_evidence_ids,
      ...(detail.primary?.contract_evidence_ids ?? []),
      ...(detail.secondary?.contract_evidence_ids ?? []),
    ])
  }, [detail])

  const legalEvidenceIds = useMemo(() => {
    if (!detail) return []
    return unique([
      ...detail.legal_evidence.map((item) => item.legal_evidence_id),
      ...(detail.primary?.legal_evidence_ids ?? []),
      ...(detail.secondary?.legal_evidence_ids ?? []),
    ])
  }, [detail])

  if (loading) {
    return <div className="review-context-empty"><strong>正在读取 Issue</strong><p>{message}</p></div>
  }
  if (!detail) {
    return <div className="review-context-empty"><strong>选择一个 AuditPlan Issue</strong><p>{message}</p></div>
  }

  const comparison = detail.comparison
  return (
    <div className="review-context-detail issue-review-context">
      <section className="context-section">
        <span className="context-eyebrow">AUDIT PLAN ISSUE</span>
        <h3>{detail.plan_issue.topic}</h3>
        <p className="context-subtitle">{detail.issue_id} · {detail.plan_issue.priority} · as_of {detail.as_of ?? '—'}</p>
        {detail.plan_issue.why_review.length > 0 && (
          <div className="issue-plan-block">
            <strong>为什么审</strong>
            <ul>{detail.plan_issue.why_review.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        )}
        {detail.plan_issue.questions.length > 0 && (
          <div className="issue-plan-block">
            <strong>审查问题</strong>
            <ol>{detail.plan_issue.questions.map((item) => <li key={item}>{item}</li>)}</ol>
          </div>
        )}
      </section>

      <section className="legal-rag-context comparison-detail">
        <div className="context-eyebrow">ISSUE LEGAL RAG</div>
        <div className="comparison-state-row">
          <strong>{detail.legal_support_state ?? '尚未完成'}</strong>
          <span>{detail.legal_evidence.length} 条 Legal Evidence</span>
        </div>
        {detail.legal_evidence.length > 0 ? (
          <div className="issue-legal-hit-list">
            {detail.legal_evidence.map((hit) => (
              <button type="button" key={hit.legal_evidence_id} onClick={() => setLegalEvidenceId(hit.legal_evidence_id)}>
                <strong>{hit.candidate.authority_title} · {hit.candidate.article_token}</strong>
                <span>{hit.candidate.matched_snippet ?? hit.candidate.article_text}</span>
                <small>{hit.candidate.coverage_type} · rank {hit.best_rank}</small>
              </button>
            ))}
          </div>
        ) : <p className="quiet-state">当前 Issue 没有可用 Legal Evidence；这不等于不存在适用法律。</p>}
      </section>

      {detail.primary ? (
        <section className="model-opinion primary-opinion">
          <div className="model-opinion-heading">
            <span>DEEPSEEK · ISSUE PRIMARY</span>
            <strong>{detail.primary.severity} · {detail.primary.state}</strong>
          </div>
          <h4>{detail.primary.title}</h4>
          <p>{detail.primary.reasoning_summary}</p>
          <small><b>建议：</b>{detail.primary.suggestion}</small>
          <small><b>证据充足度：</b>{detail.primary.evidence_sufficiency}</small>
          <small><b>法律结论：</b>{detail.primary.legal_conclusion ? 'YES' : 'NO'}</small>
        </section>
      ) : <p className="quiet-state">DeepSeek 尚未完成该 Issue。</p>}

      {detail.secondary ? (
        <section className="model-opinion secondary-opinion">
          <div className="model-opinion-heading">
            <span>KIMI · FINDING + COVERAGE REVIEW</span>
            <strong>{detail.secondary.severity} · {detail.secondary.assessment}</strong>
          </div>
          <p>{detail.secondary.reasoning_summary}</p>
          <small><b>Coverage：</b>{detail.secondary.coverage_assessment}</small>
          <small><b>建议：</b>{detail.secondary.suggestion}</small>
          {detail.secondary.omission_title && (
            <div className="issue-omission-box">
              <strong>Possible Omission · {detail.secondary.omission_title}</strong>
              <p>{detail.secondary.omission_reasoning}</p>
            </div>
          )}
        </section>
      ) : <p className="quiet-state">Kimi 尚未完成该 Issue。</p>}

      <section className="comparison-detail">
        <div className="context-eyebrow">DETERMINISTIC ISSUE COMPARISON</div>
        {comparison ? (
          <>
            <div className="comparison-state-row">
              <strong>{comparison.overall_state}</strong>
              <span>{comparison.requires_human_review ? '必须人工复核' : '无强制人工复核'}</span>
            </div>
            <div className="comparison-grid">
              <div><span>严重度距离</span><strong>{comparison.severity_distance}</strong></div>
              <div><span>合同证据</span><strong>{comparison.contract_evidence.state}</strong></div>
              <div><span>法律证据</span><strong>{comparison.legal_evidence.state}</strong></div>
              <div><span>DeepSeek</span><strong>{comparison.primary_state}</strong></div>
              <div><span>Kimi</span><strong>{comparison.secondary_assessment}</strong></div>
              <div><span>Coverage</span><strong>{comparison.coverage_assessment}</strong></div>
            </div>
            {comparison.reasons.length > 0 && <p className="comparison-reasons">{comparison.reasons.join(' ｜ ')}</p>}
          </>
        ) : <p className="quiet-state">尚无确定性 Issue Comparison。</p>}
      </section>

      <section className="context-evidence-links">
        <div>
          <span className="context-eyebrow">CONTRACT EVIDENCE</span>
          <div className="context-chip-list">
            {contractEvidence.length === 0 && <em>无</em>}
            {contractEvidence.map((id) => <button type="button" key={id} onClick={() => onContractEvidence(id)}>{id}</button>)}
          </div>
        </div>
        <div>
          <span className="context-eyebrow">LEGAL EVIDENCE</span>
          <div className="context-chip-list">
            {legalEvidenceIds.length === 0 && <em>无</em>}
            {legalEvidenceIds.map((id) => <button type="button" key={id} onClick={() => setLegalEvidenceId(id)}>{id}</button>)}
          </div>
        </div>
      </section>

      <section className="legal-evidence-detail">
        <div className="context-eyebrow">SELECTED LEGAL AUTHORITY</div>
        <p className="legal-load-state">{legalMessage}</p>
        {legalEvidence && (
          <>
            <div className="legal-heading"><strong>{legalEvidence.authority.title}</strong><span>{legalEvidence.article.article_token}</span></div>
            <p className="legal-article-text">{legalEvidence.article.text}</p>
            <div className="legal-meta-grid">
              <div><span>版本</span><strong>{legalEvidence.version.version_id}</strong></div>
              <div><span>生效</span><strong>{legalEvidence.version.effective_date}</strong></div>
              <div><span>终止（exclusive）</span><strong>{legalEvidence.version.end_date_exclusive ?? '—'}</strong></div>
              <div><span>Coverage</span><strong>{legalEvidence.version.coverage_type}</strong></div>
            </div>
            {legalEvidence.version.coverage_type === 'CURATED_EXCERPT' && <p className="coverage-warning">当前法律库是节选覆盖；本地无命中不能解释为法律上不存在相关规则。</p>}
            {legalEvidence.version.coverage_note && <p className="coverage-note">{legalEvidence.version.coverage_note}</p>}
            <div className="official-source-list">
              {legalEvidence.version.source_refs.map((source) => (
                <a key={`${source.role}-${source.url}`} href={source.url} target="_blank" rel="noreferrer">{source.role} · {source.name}</a>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="human-decision-placeholder issue-human-boundary">
        <span className="context-eyebrow">HUMAN REVIEW · STAGE 13G.6</span>
        <strong>{comparison?.requires_human_review ? '该 Issue 已被标记为人工复核优先项' : '当前仅展示审计链结果'}</strong>
        <p>13G.5 不会把旧 Finding/Omission 人工决策强行套到 Issue 上。Issue 级人工确认、驳回和修订将在下一迁移切片接入。</p>
      </section>

      {detail.warnings.length > 0 && (
        <section className="warning-panel"><div className="subheading">Issue 警告</div><ul>{detail.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></section>
      )}
    </div>
  )
}
