import { useEffect, useState } from 'react'
import type { FindingComparison, OmissionComparison, SelectedAuditItem } from './workstation-review-types'

import { API_BASE_URL } from './apiBase'

type LegalEvidenceRecord = {
  authority: {
    authority_id: string
    title: string
    authority_type: string
    issuing_body: string
    document_number: string | null
    jurisdiction: string
  }
  version: {
    version_id: string
    status: string
    publication_date: string | null
    effective_date: string
    end_date_exclusive: string | null
    coverage_type: 'FULL_TEXT' | 'CURATED_EXCERPT'
    coverage_note: string | null
    source_refs: Array<{ name: string; url: string; role: string }>
    verified_on: string | null
    verification_note: string | null
  }
  article: {
    article_id: string
    article_token: string
    text: string
    legal_evidence_id: string
    heading_context: string[]
  }
}

type Props = {
  selectedItem: SelectedAuditItem | null
  legalEvidenceId: string | null
  onContractEvidence: (evidenceId: string) => void
  onLegalEvidence: (evidenceId: string) => void
  finalReviewState: string | null
  agentActionCount: number
}

function comparisonReasons(comparison: FindingComparison | OmissionComparison | undefined) {
  if (!comparison) return []
  if ('material_reasons' in comparison) return comparison.material_reasons
  return [comparison.reason]
}

function applicability(record: LegalEvidenceRecord, asOf: string) {
  const begins = record.version.effective_date <= asOf
  const beforeEnd = !record.version.end_date_exclusive || asOf < record.version.end_date_exclusive
  return begins && beforeEnd ? '适用于当前 as_of' : '不适用于当前 as_of'
}

export default function ReviewContextPane({
  selectedItem,
  legalEvidenceId,
  onContractEvidence,
  onLegalEvidence,
  finalReviewState,
  agentActionCount,
}: Props) {
  const [legalEvidence, setLegalEvidence] = useState<LegalEvidenceRecord | null>(null)
  const [legalMessage, setLegalMessage] = useState('点击 Legal Evidence 查看法条版本和官方来源。')

  useEffect(() => {
    if (!legalEvidenceId) {
      setLegalEvidence(null)
      setLegalMessage('点击 Legal Evidence 查看法条版本和官方来源。')
      return
    }

    let cancelled = false
    const load = async () => {
      setLegalEvidence(null)
      setLegalMessage('正在读取本地 Legal Evidence…')
      try {
        const response = await fetch(`${API_BASE_URL}/api/legal/evidence/${encodeURIComponent(legalEvidenceId)}`)
        const body = await response.json().catch(() => null)
        if (!response.ok) {
          const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
          throw new Error(detail)
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

  if (!selectedItem) {
    return (
      <div className="review-context-empty">
        <strong>选择一个审计项</strong>
        <p>中栏选择风险后，这里会并排保留 DeepSeek、Kimi 和程序 Comparison，不会合并成一段新的模型结论。</p>
      </div>
    )
  }

  const reasons = comparisonReasons(selectedItem.comparison)

  return (
    <div className="review-context-detail">
      <section className="context-section">
        <span className="context-eyebrow">SELECTED AUDIT ITEM</span>
        <h3>{selectedItem.title}</h3>
        <p className="context-subtitle">{selectedItem.riskCategory} · {selectedItem.itemId} · as_of {selectedItem.asOf}</p>
      </section>

      {selectedItem.primary && (
        <section className="model-opinion primary-opinion">
          <div className="model-opinion-heading">
            <span>DEEPSEEK PRIMARY</span>
            <strong>{selectedItem.primary.severity} · {selectedItem.primary.state}</strong>
          </div>
          <p>{selectedItem.primary.reasoning_summary}</p>
          <small><b>建议：</b>{selectedItem.primary.suggestion}</small>
          <small><b>证据充足度：</b>{selectedItem.primary.evidence_sufficiency}</small>
        </section>
      )}

      {selectedItem.secondary && (
        <section className="model-opinion secondary-opinion">
          <div className="model-opinion-heading">
            <span>KIMI SECONDARY</span>
            <strong>{selectedItem.secondary.severity} · {selectedItem.secondary.assessment}</strong>
          </div>
          <p>{selectedItem.secondary.reasoning_summary}</p>
          <small><b>建议：</b>{selectedItem.secondary.suggestion}</small>
          {selectedItem.secondary.disagreement_categories.length > 0 && (
            <small><b>二审标签：</b>{selectedItem.secondary.disagreement_categories.join(' · ')}</small>
          )}
        </section>
      )}

      {selectedItem.omission && (
        <section className="model-opinion omission-opinion">
          <div className="model-opinion-heading">
            <span>KIMI POSSIBLE OMISSION</span>
            <strong>{selectedItem.omission.severity}</strong>
          </div>
          <p>{selectedItem.omission.reasoning_summary}</p>
          <small><b>建议：</b>{selectedItem.omission.suggestion}</small>
          <small>该项仍是“可能漏审项”，不是程序自动确认的新风险。</small>
        </section>
      )}

      <section className="comparison-detail">
        <div className="context-eyebrow">DETERMINISTIC COMPARISON</div>
        {selectedItem.comparison ? (
          <>
            <div className="comparison-state-row">
              <strong>{selectedItem.comparison.overall_state}</strong>
              {'risk_state' in selectedItem.comparison && <span>{selectedItem.comparison.risk_state}</span>}
              <span>{selectedItem.comparison.follow_up}</span>
            </div>
            {'contract_evidence' in selectedItem.comparison && (
              <div className="comparison-grid">
                <div><span>严重度</span><strong>{selectedItem.comparison.severity.state} · distance {selectedItem.comparison.severity.distance}</strong></div>
                <div><span>合同证据</span><strong>{selectedItem.comparison.contract_evidence.state}</strong></div>
                <div><span>法律依据</span><strong>{selectedItem.comparison.legal_basis.state}</strong></div>
              </div>
            )}
            {reasons.length > 0 && <p className="comparison-reasons">{reasons.join(' ｜ ')}</p>}
          </>
        ) : (
          <p className="quiet-state">没有对应的程序 Comparison 记录。</p>
        )}
      </section>

      {selectedItem.agentActions.length > 0 && (
        <section className="agent-trace-detail">
          <div className="context-eyebrow">AGENT TRACE</div>
          {selectedItem.agentActions.map((action) => (
            <article key={action.action_id}>
              <div>
                <strong>Cycle {action.cycle} · {action.tool_name}</strong>
                <span>{action.state}</span>
              </div>
              <p>{action.reason}</p>
              <small>Input {action.input_evidence_ids.length} · Output {action.output_evidence_ids.length}</small>
              <small>Provider call: {action.provider_call_occurred ? 'YES' : 'NO'} · Contract left machine: {action.private_contract_evidence_left_machine ? 'YES' : 'NO'}</small>
              {action.validation_or_error && <em>{action.validation_or_error}</em>}
            </article>
          ))}
        </section>
      )}

      <section className="context-evidence-links">
        <div>
          <span className="context-eyebrow">CONTRACT EVIDENCE</span>
          <div className="context-chip-list">
            {selectedItem.contractEvidenceIds.length === 0 && <em>无</em>}
            {selectedItem.contractEvidenceIds.map((id) => (
              <button type="button" key={id} onClick={() => onContractEvidence(id)}>{id}</button>
            ))}
          </div>
        </div>
        <div>
          <span className="context-eyebrow">LEGAL EVIDENCE</span>
          <div className="context-chip-list">
            {selectedItem.legalEvidenceIds.length === 0 && <em>无</em>}
            {selectedItem.legalEvidenceIds.map((id) => (
              <button type="button" key={id} onClick={() => onLegalEvidence(id)}>{id}</button>
            ))}
          </div>
        </div>
      </section>

      <section className="legal-evidence-detail">
        <div className="context-eyebrow">LEGAL AUTHORITY</div>
        <p className="legal-load-state">{legalMessage}</p>
        {legalEvidence && (
          <>
            <div className="legal-heading">
              <strong>{legalEvidence.authority.title}</strong>
              <span>{legalEvidence.article.article_token}</span>
            </div>
            <p className="legal-article-text">{legalEvidence.article.text}</p>
            <div className="legal-meta-grid">
              <div><span>版本</span><strong>{legalEvidence.version.version_id}</strong></div>
              <div><span>生效</span><strong>{legalEvidence.version.effective_date}</strong></div>
              <div><span>终止（exclusive）</span><strong>{legalEvidence.version.end_date_exclusive ?? '—'}</strong></div>
              <div><span>Coverage</span><strong>{legalEvidence.version.coverage_type}</strong></div>
              <div><span>as_of</span><strong>{selectedItem.asOf}</strong></div>
              <div><span>适用性</span><strong>{applicability(legalEvidence, selectedItem.asOf)}</strong></div>
            </div>
            {legalEvidence.version.coverage_type === 'CURATED_EXCERPT' && (
              <p className="coverage-warning">当前法律库是节选覆盖；“库中没有”不能解释为“法律上不存在”。</p>
            )}
            {legalEvidence.version.coverage_note && <p className="coverage-note">{legalEvidence.version.coverage_note}</p>}
            <div className="official-source-list">
              {legalEvidence.version.source_refs.map((source) => (
                <a key={`${source.role}-${source.url}`} href={source.url} target="_blank" rel="noreferrer">
                  {source.role} · {source.name}
                </a>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="stage9-boundary-card">
        <span className="context-eyebrow">STAGE 9 BOUNDARY</span>
        <strong>{finalReviewState ?? '尚无最终 Stage 9 状态'}</strong>
        <p>关联 Agent 动作 {selectedItem.agentActions.length} / 全任务 {agentActionCount}。工作台不会把补证据动作自动改写成新的模型裁决。</p>
      </section>
    </div>
  )
}
