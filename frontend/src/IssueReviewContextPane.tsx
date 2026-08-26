import { useEffect, useMemo, useState } from 'react'
import IssueHumanDecisionPanel from './IssueHumanDecisionPanel'
import type { IssueWorkspaceDetail } from './issue-workspace-types'

import { API_BASE_URL } from './apiBase'

type SourceEvidenceDetail = {
  evidence_id: string
  page_number: number | null
  source_method: string
  text: string
  confidence: number | null
  source_locator: string | null
}

type Props = {
  detail: IssueWorkspaceDetail | null
  loading: boolean
  message: string
  onContractEvidence: (evidenceId: string) => void
  onHumanReviewSaved: () => void
}

function unique(values: string[]) {
  return [...new Set(values.filter(Boolean))]
}

function secondaryStatusLabel(value: string | undefined) {
  if (value === 'SKIPPED_CLEAR') return '无需复核'
  if (value === 'PENDING_CONFIRMATION') return '二审未完成，待确认'
  return '已复核'
}

function assessmentLabel(value: string | undefined) {
  if (value === 'SUPPORTED') return '支持主审结论'
  if (value === 'PARTIALLY_SUPPORTED') return '部分支持'
  if (value === 'DISAGREED') return '存在分歧'
  if (value === 'INSUFFICIENT_EVIDENCE') return '证据不足'
  if (value === 'REVIEW_REQUIRED') return '建议确认'
  return '尚未完成'
}

function locationLabel(evidence: SourceEvidenceDetail) {
  if (evidence.page_number != null) return `第 ${evidence.page_number} 页`
  if (evidence.source_locator) return evidence.source_locator
  return '源文档位置'
}

export default function IssueReviewContextPane({ detail, loading, message, onContractEvidence, onHumanReviewSaved }: Props) {
  const [contractEvidence, setContractEvidence] = useState<SourceEvidenceDetail[]>([])
  const [evidenceMessage, setEvidenceMessage] = useState('')

  const contractEvidenceIds = useMemo(() => {
    if (!detail) return []
    return unique([
      ...detail.plan_issue.contract_evidence_ids,
      ...(detail.primary?.contract_evidence_ids ?? []),
      ...(detail.secondary?.contract_evidence_ids ?? []),
    ]).slice(0, 6)
  }, [detail])

  useEffect(() => {
    setContractEvidence([])
    setEvidenceMessage('')
    if (!detail || contractEvidenceIds.length === 0) return
    let cancelled = false
    const load = async () => {
      setEvidenceMessage('正在读取合同原文依据…')
      const rows: SourceEvidenceDetail[] = []
      for (const id of contractEvidenceIds) {
        try {
          const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(detail.job_id)}/evidence/${encodeURIComponent(id)}`)
          const body = await response.json().catch(() => null)
          if (response.ok && body) rows.push(body as SourceEvidenceDetail)
        } catch {
          // Evidence is helpful context; a single lookup failure should not hide the review result.
        }
      }
      if (!cancelled) {
        setContractEvidence(rows)
        setEvidenceMessage(rows.length ? '已读取合同原文依据。' : '合同原文依据暂时无法读取。')
      }
    }
    void load()
    return () => { cancelled = true }
  }, [contractEvidenceIds, detail])

  if (loading) {
    return <div className="review-context-empty"><strong>正在读取风险详情</strong><p>{message}</p></div>
  }
  if (!detail) {
    return <div className="review-context-empty"><strong>选择风险点</strong><p>{message}</p></div>
  }

  return (
    <div className="report-drawer-content">
      <section className="drawer-section">
        <span className="report-kicker">审查问题</span>
        <p>{detail.plan_issue.questions[0] ?? detail.plan_issue.topic}</p>
        {detail.plan_issue.why_review.length > 0 && (
          <ul>
            {detail.plan_issue.why_review.slice(0, 3).map((item) => <li key={item}>{item}</li>)}
          </ul>
        )}
      </section>

      {detail.primary && (
        <section className="drawer-section">
          <span className="report-kicker">风险判断</span>
          <h3>{detail.primary.title}</h3>
          <p>{detail.primary.reasoning_summary}</p>
          <div className="drawer-callout">
            <strong>修改建议</strong>
            <p>{detail.primary.suggestion}</p>
          </div>
        </section>
      )}

      <section className="drawer-section">
        <span className="report-kicker">合同证据原文</span>
        {contractEvidence.length === 0 ? (
          <p className="report-muted">{evidenceMessage || '暂无可展示的合同原文依据。'}</p>
        ) : (
          <div className="evidence-quote-list">
            {contractEvidence.map((item) => (
              <button type="button" key={item.evidence_id} onClick={() => onContractEvidence(item.evidence_id)}>
                <strong>{locationLabel(item)}</strong>
                <span>{item.text}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="drawer-section">
        <span className="report-kicker">法律依据</span>
        {detail.legal_evidence.length === 0 ? (
          <p className="report-muted">未在本地法律知识库中找到直接匹配条文。</p>
        ) : (
          <div className="legal-article-list">
            {detail.legal_evidence.slice(0, 5).map((hit) => (
              <article key={hit.legal_evidence_id}>
                <strong>{hit.candidate.authority_title} · {hit.candidate.article_token}</strong>
                <p>{hit.candidate.article_text}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="drawer-section">
        <span className="report-kicker">争议复审</span>
        {detail.secondary ? (
          <div className="secondary-review-summary">
            <strong>{secondaryStatusLabel(detail.secondary.review_status)} · {assessmentLabel(detail.secondary.assessment)}</strong>
            <p>{detail.secondary.reasoning_summary}</p>
            {detail.secondary.suggestion && <p>{detail.secondary.suggestion}</p>}
            {detail.secondary.omission_title && (
              <div className="drawer-callout warning">
                <strong>{detail.secondary.omission_title}</strong>
                <p>{detail.secondary.omission_reasoning}</p>
              </div>
            )}
          </div>
        ) : (
          <p className="report-muted">尚未生成争议复审结果。</p>
        )}
      </section>

      <IssueHumanDecisionPanel detail={detail} onSaved={onHumanReviewSaved} />

      {detail.warnings.length > 0 && (
        <section className="drawer-section subdued">
          <span className="report-kicker">审查说明</span>
          <ul>{detail.warnings.slice(0, 4).map((warning) => <li key={warning}>{warning}</li>)}</ul>
        </section>
      )}
    </div>
  )
}
