import { useEffect, useMemo, useState } from 'react'
import type { KeyboardEvent } from 'react'
import type {
  AgentAction,
  FindingComparison,
  OmissionComparison,
  ReviewReport,
  SelectedAuditItem,
  Severity,
} from './workstation-review-types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type Props = {
  jobId: string
  reportAvailable: boolean
  onSelectionChange: (item: SelectedAuditItem | null) => void
  onContractEvidence: (evidenceId: string) => void
  onLegalEvidence: (evidenceId: string) => void
}

type QueueItem = SelectedAuditItem & {
  severity: Severity
  state: string
  needsHumanReview: boolean
}

const severityRank: Record<Severity, number> = {
  INFO: 0,
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
  CRITICAL: 4,
}

function unique(values: string[]) {
  return [...new Set(values)]
}

function stateLabel(value: string) {
  if (value === 'AGREEMENT') return '一致'
  if (value === 'AGREEMENT_WITH_REVIEW') return '一致但需复核'
  if (value === 'MINOR_DISAGREEMENT') return '轻度分歧'
  if (value === 'REQUIRES_MORE_EVIDENCE') return '需要补证据'
  if (value === 'MATERIAL_DISAGREEMENT') return '实质分歧'
  return value
}

function severityClass(severity: Severity) {
  return `severity-${severity.toLowerCase()}`
}

function actionsForItem(actions: AgentAction[], itemId: string, evidenceIds: string[]) {
  const evidence = new Set(evidenceIds)
  return actions.filter((action) => {
    if (action.reason.includes(itemId)) return true
    return [...action.input_evidence_ids, ...action.output_evidence_ids].some((id) => evidence.has(id))
  })
}

export default function AuditQueuePane({
  jobId,
  reportAvailable,
  onSelectionChange,
  onContractEvidence,
  onLegalEvidence,
}: Props) {
  const [report, setReport] = useState<ReviewReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [minimumSeverity, setMinimumSeverity] = useState<Severity>('INFO')
  const [showOnlyAttention, setShowOnlyAttention] = useState(false)
  const [comparisonFilter, setComparisonFilter] = useState('ALL')
  const [query, setQuery] = useState('')

  useEffect(() => {
    setReport(null)
    setSelectedId(null)
    onSelectionChange(null)
    if (!reportAvailable) {
      setMessage('review-report.json 尚未生成；工作台不会自动补跑 Stage 8/9。')
      return
    }

    let cancelled = false
    const load = async () => {
      setLoading(true)
      setMessage('正在读取本机 review-report.json…')
      try {
        const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/review-report`)
        const body = await response.json().catch(() => null)
        if (!response.ok) {
          const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
          throw new Error(detail)
        }
        if (!cancelled) {
          setReport(body as ReviewReport)
          setMessage('已载入双模型比较报告。筛选与点击操作均为本地展示。')
        }
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : '无法读取 review-report.json。')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [jobId, reportAvailable, onSelectionChange])

  const queueItems = useMemo<QueueItem[]>(() => {
    if (!report) return []
    const comparisons = new Map<string, FindingComparison>(
      report.comparison.finding_comparisons.map((item) => [item.primary_finding_id, item]),
    )
    const secondary = new Map(report.secondary_reviews.map((item) => [item.primary_finding_id, item]))

    const findings: QueueItem[] = report.primary_findings.map((primary) => {
      const comparison = comparisons.get(primary.finding_id)
      const reviewer = secondary.get(primary.finding_id)
      const contractEvidenceIds = unique([
        ...primary.contract_evidence_ids,
        ...(reviewer?.contract_evidence_ids ?? []),
      ])
      const legalEvidenceIds = unique([
        ...primary.legal_evidence_ids,
        ...(reviewer?.legal_evidence_ids ?? []),
      ])
      const comparisonState = comparison?.overall_state ?? 'UNCOMPARED'
      const needsHumanReview = [
        'MATERIAL_DISAGREEMENT',
        'REQUIRES_MORE_EVIDENCE',
        'AGREEMENT_WITH_REVIEW',
      ].includes(comparisonState) || primary.state === 'REVIEW_REQUIRED' || primary.state === 'INSUFFICIENT_EVIDENCE'
      const allEvidence = [...contractEvidenceIds, ...legalEvidenceIds]

      return {
        itemType: 'finding',
        itemId: primary.finding_id,
        title: primary.title,
        riskCategory: primary.risk_category,
        asOf: report.as_of,
        primary,
        secondary: reviewer,
        comparison,
        contractEvidenceIds,
        legalEvidenceIds,
        agentActions: actionsForItem(report.action_trace, primary.finding_id, allEvidence),
        severity: primary.severity,
        state: comparisonState,
        needsHumanReview,
      }
    })

    const omissionComparisons = new Map<string, OmissionComparison>(
      report.comparison.omission_comparisons.map((item) => [item.omission_id, item]),
    )
    const omissions: QueueItem[] = report.possible_primary_omissions.map((omission) => {
      const allEvidence = [...omission.contract_evidence_ids, ...omission.legal_evidence_ids]
      return {
        itemType: 'omission',
        itemId: omission.omission_id,
        title: omission.title,
        riskCategory: omission.risk_category,
        asOf: report.as_of,
        omission,
        comparison: omissionComparisons.get(omission.omission_id),
        contractEvidenceIds: omission.contract_evidence_ids,
        legalEvidenceIds: omission.legal_evidence_ids,
        agentActions: actionsForItem(report.action_trace, omission.omission_id, allEvidence),
        severity: omission.severity,
        state: omissionComparisons.get(omission.omission_id)?.overall_state ?? 'MATERIAL_DISAGREEMENT',
        needsHumanReview: true,
      }
    })

    return [...findings, ...omissions].sort((a, b) => {
      const severityDelta = severityRank[b.severity] - severityRank[a.severity]
      if (severityDelta) return severityDelta
      if (a.needsHumanReview !== b.needsHumanReview) return a.needsHumanReview ? -1 : 1
      return a.itemId.localeCompare(b.itemId)
    })
  }, [report])

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return queueItems.filter((item) => {
      if (severityRank[item.severity] < severityRank[minimumSeverity]) return false
      if (showOnlyAttention && !item.needsHumanReview) return false
      if (comparisonFilter !== 'ALL' && item.state !== comparisonFilter) return false
      if (normalizedQuery && !`${item.title} ${item.riskCategory} ${item.itemId}`.toLowerCase().includes(normalizedQuery)) return false
      return true
    })
  }, [comparisonFilter, minimumSeverity, query, queueItems, showOnlyAttention])

  useEffect(() => {
    if (filtered.length === 0) {
      if (selectedId !== null) {
        setSelectedId(null)
        onSelectionChange(null)
      }
      return
    }
    if (!selectedId || !filtered.some((item) => item.itemId === selectedId)) {
      setSelectedId(filtered[0].itemId)
      onSelectionChange(filtered[0])
    }
  }, [filtered, onSelectionChange, selectedId])

  const selectItem = (item: QueueItem) => {
    setSelectedId(item.itemId)
    onSelectionChange(item)
  }

  const onCardKeyDown = (event: KeyboardEvent<HTMLElement>, item: QueueItem) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      selectItem(item)
    }
  }

  return (
    <div className="audit-queue">
      <div className="queue-toolbar">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索风险标题 / 类型 / ID"
          aria-label="搜索审计项"
        />
        <select value={minimumSeverity} onChange={(event) => setMinimumSeverity(event.target.value as Severity)} aria-label="最低严重度">
          <option value="INFO">INFO+</option>
          <option value="LOW">LOW+</option>
          <option value="MEDIUM">MEDIUM+</option>
          <option value="HIGH">HIGH+</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
        <select value={comparisonFilter} onChange={(event) => setComparisonFilter(event.target.value)} aria-label="比较状态">
          <option value="ALL">全部比较状态</option>
          <option value="AGREEMENT">一致</option>
          <option value="AGREEMENT_WITH_REVIEW">一致但需复核</option>
          <option value="MINOR_DISAGREEMENT">轻度分歧</option>
          <option value="REQUIRES_MORE_EVIDENCE">需要补证据</option>
          <option value="MATERIAL_DISAGREEMENT">实质分歧</option>
        </select>
        <label>
          <input
            type="checkbox"
            checked={showOnlyAttention}
            onChange={(event) => setShowOnlyAttention(event.target.checked)}
          />
          只看需关注
        </label>
      </div>

      <div className="queue-status" aria-live="polite">{loading ? '读取中…' : message}</div>

      {report && (
        <div className="queue-summary">
          <span>最终：{report.final_state}</span>
          <span>比较：{report.comparison.overall_state}</span>
          <span>筛选后 {filtered.length} / {queueItems.length} 项</span>
        </div>
      )}

      {!loading && reportAvailable && report && filtered.length === 0 && (
        <div className="quiet-state">当前筛选条件下没有审计项。</div>
      )}

      <div className="queue-list" aria-label="审计项列表">
        {filtered.map((item) => (
          <article
            key={`${item.itemType}-${item.itemId}`}
            className={`queue-card ${selectedId === item.itemId ? 'is-selected' : ''} ${item.needsHumanReview ? 'needs-review' : ''}`}
            role="button"
            tabIndex={0}
            aria-pressed={selectedId === item.itemId}
            onClick={() => selectItem(item)}
            onKeyDown={(event) => onCardKeyDown(event, item)}
          >
            <div className="queue-card-heading">
              <span className={`severity-pill ${severityClass(item.severity)}`}>{item.severity}</span>
              <span className="comparison-pill">{stateLabel(item.state)}</span>
              {item.itemType === 'omission' && <span className="omission-pill">Kimi 漏审提示</span>}
              {item.agentActions.length > 0 && <span className="agent-pill">Agent {item.agentActions.length}</span>}
            </div>
            <h3>{item.title}</h3>
            <p>{item.riskCategory} · {item.itemId}</p>

            {item.primary && item.secondary && (
              <div className="model-compare-row">
                <span>DeepSeek：{item.primary.state}</span>
                <span>Kimi：{item.secondary.assessment}</span>
              </div>
            )}

            <div className="queue-evidence-groups">
              <div>
                <strong>合同 Evidence</strong>
                <div>
                  {item.contractEvidenceIds.length === 0 && <em>无</em>}
                  {item.contractEvidenceIds.map((id) => (
                    <button
                      type="button"
                      key={id}
                      onClick={(event) => { event.stopPropagation(); selectItem(item); onContractEvidence(id) }}
                    >
                      {id}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <strong>Legal Evidence</strong>
                <div>
                  {item.legalEvidenceIds.length === 0 && <em>无</em>}
                  {item.legalEvidenceIds.map((id) => (
                    <button
                      type="button"
                      key={id}
                      onClick={(event) => { event.stopPropagation(); selectItem(item); onLegalEvidence(id) }}
                    >
                      {id}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
