import { useMemo, useState } from 'react'
import type { IssueQueueItem, ReviewPriority } from './issue-workspace-types'

type Props = {
  issues: IssueQueueItem[]
  selectedIssueId: string | null
  onSelect: (issue: IssueQueueItem) => void
}

function severityClass(severity: string | null) {
  return `severity-${(severity ?? 'INFO').toLowerCase()}`
}

function priorityLabel(priority: ReviewPriority) {
  if (priority === 'HIGH_ATTENTION') return '高关注'
  if (priority === 'IMPORTANT') return '重要'
  return '常规'
}

export default function IssueAuditQueuePane({ issues, selectedIssueId, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [attentionOnly, setAttentionOnly] = useState(false)
  const [priority, setPriority] = useState<'ALL' | ReviewPriority>('ALL')

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return issues.filter((issue) => {
      if (attentionOnly && !issue.requires_human_review) return false
      if (priority !== 'ALL' && issue.priority !== priority) return false
      if (!needle) return true
      return [
        issue.issue_id,
        issue.topic,
        issue.primary_state ?? '',
        issue.secondary_assessment ?? '',
        issue.comparison_state ?? '',
      ].some((value) => value.toLowerCase().includes(needle))
    })
  }, [issues, query, attentionOnly, priority])

  return (
    <div className="audit-queue issue-audit-queue">
      <div className="queue-toolbar">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索 Issue / 主题 / 状态"
          aria-label="搜索审计 Issue"
        />
        <select value={priority} onChange={(event) => setPriority(event.target.value as 'ALL' | ReviewPriority)}>
          <option value="ALL">全部优先级</option>
          <option value="HIGH_ATTENTION">高关注</option>
          <option value="IMPORTANT">重要</option>
          <option value="NORMAL">常规</option>
        </select>
        <label>
          <input
            type="checkbox"
            checked={attentionOnly}
            onChange={(event) => setAttentionOnly(event.target.checked)}
          />
          仅看需人工复核
        </label>
      </div>

      <div className="queue-summary">
        <span>全部 {issues.length}</span>
        <span>当前 {filtered.length}</span>
        <span>需人工 {issues.filter((item) => item.requires_human_review).length}</span>
        <span>分歧 {issues.filter((item) => item.comparison_state === 'MATERIAL_DISAGREEMENT').length}</span>
        <span>可能漏审 {issues.filter((item) => item.comparison_state === 'POSSIBLE_OMISSION').length}</span>
      </div>

      <div className="queue-list">
        {filtered.length === 0 && <p className="quiet-state">当前筛选条件下没有 Issue。</p>}
        {filtered.map((issue) => (
          <article
            key={issue.issue_id}
            className={`queue-card ${selectedIssueId === issue.issue_id ? 'is-selected' : ''} ${issue.requires_human_review ? 'needs-review' : ''}`}
            onClick={() => onSelect(issue)}
          >
            <div className="queue-card-heading">
              <span className={`severity-pill ${severityClass(issue.primary_severity)}`}>
                {issue.primary_severity ?? 'PENDING'}
              </span>
              <span className="comparison-pill">{issue.comparison_state ?? 'WAITING_COMPARISON'}</span>
              {issue.requires_human_review && <span className="omission-pill">HUMAN REVIEW</span>}
            </div>
            <h3>{issue.topic}</h3>
            <p>{issue.issue_id} · {priorityLabel(issue.priority)} · {issue.source_labels.join(' + ') || '未标记来源'}</p>
            <div className="model-compare-row">
              <span>DeepSeek · {issue.primary_state ?? '尚未完成'}</span>
              <span>Kimi · {issue.secondary_assessment ?? '尚未完成'}</span>
            </div>
            <div className="model-compare-row">
              <span>Coverage · {issue.coverage_assessment ?? '尚未复核'}</span>
              <span>Legal · {issue.legal_support_state ?? '尚未检索'}</span>
            </div>
            <div className="queue-evidence-groups issue-evidence-counts">
              <div><strong>合同证据</strong><span>{issue.contract_evidence_count} 条</span></div>
              <div><strong>法律证据</strong><span>{issue.legal_evidence_count} 条</span></div>
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
