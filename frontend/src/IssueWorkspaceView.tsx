import { useEffect, useMemo, useState } from 'react'
import IssueReviewContextPane from './IssueReviewContextPane'
import ReportExportControls from './ReportExportControls'
import type {
  ArtifactState,
  IssueQueueItem,
  IssueWorkspaceDetail,
  IssueWorkspacePresentationSummary,
  IssueWorkspaceRiskSummary,
  IssueWorkspaceSummary,
  OverallState,
} from './issue-workspace-types'

import { API_BASE_URL } from './apiBase'

type Props = {
  summary: IssueWorkspaceSummary
  onRefresh: () => void
}

function stateClass(state: ArtifactState | OverallState | string) {
  if (state === 'READY' || state === 'COMPLETE') return 'is-ready'
  if (state === 'NOT_REQUIRED') return 'is-muted'
  if (state === 'HUMAN_REVIEW_REQUIRED') return 'is-review'
  if (state === 'INVALID') return 'is-invalid'
  return 'is-missing'
}

function riskClass(risk: string) {
  if (risk === '低风险') return 'risk-low'
  if (risk === '中风险') return 'risk-medium'
  if (risk === '高风险') return 'risk-high'
  if (risk === '重大风险') return 'risk-critical'
  return 'risk-pending'
}

function stageLabel(stage: string) {
  if (stage === 'upload') return '上传完成'
  if (stage === 'ocr') return '文本识别'
  if (stage === 'structure') return '条款整理'
  if (stage === 'analysis') return '风险分析'
  if (stage === 'secondary') return '争议复审'
  return '报告生成'
}

function stageState(summary: IssueWorkspaceSummary, stage: string): ArtifactState {
  if (stage === 'upload') return summary.source_available ? 'READY' : 'MISSING'
  const relevant = summary.stages.filter((item) => {
    if (stage === 'ocr') return item.stage === '3'
    if (stage === 'structure') return item.stage === '4'
    if (stage === 'analysis') return ['5', '6', '7', '13B/C', '13D', '13E'].includes(item.stage)
    if (stage === 'secondary') return item.stage === '13F'
    return item.stage === '13G'
  })
  if (!relevant.length) return 'MISSING'
  if (relevant.some((item) => item.state === 'INVALID')) return 'INVALID'
  if (relevant.every((item) => item.state === 'READY' || item.state === 'NOT_REQUIRED')) return 'READY'
  return 'MISSING'
}

function fallbackPresentation(summary: IssueWorkspaceSummary): IssueWorkspacePresentationSummary {
  const unfinished = summary.overall_state === 'INCOMPLETE' || summary.overall_state === 'INVALID'
  const pending = summary.review.secondary_pending_confirmation_count > 0
  const hasHigh = summary.issues.some((item) => item.primary_severity === 'HIGH' || item.primary_severity === 'CRITICAL')
  const overall = unfinished || pending ? '待确认' : hasHigh ? '高风险' : '低风险'
  return {
    overall_risk: overall,
    signing_recommendation: unfinished
      ? '审查尚未完成，不能作为低风险或签署结论；请等待风险分析和报告生成完成。'
      : pending ? '存在未完成复审事项，建议确认后再推进签署。' : '未发现优先级较高的风险，建议结合交易背景复核。',
    top_risks: [],
    suggested_actions: [],
    evidence_confidence: unfinished
      ? '待确认：审计链尚未完整生成，现有发现只能作为阶段性线索。'
      : pending ? '待确认：部分争议复审可稍后补跑。' : '较充分：关键问题已完成证据审查。',
    secondary_review_status_counts: {
      REVIEWED: summary.review.secondary_reviewed_count,
      SKIPPED_CLEAR: summary.review.secondary_skipped_clear_count,
      PENDING_CONFIRMATION: summary.review.secondary_pending_confirmation_count,
    },
  }
}

function decisionText(issue: IssueQueueItem | undefined) {
  if (!issue?.human_decision_state || issue.human_decision_state === 'UNREVIEWED') return '待处理'
  if (issue.human_decision_state === 'CONFIRMED') return '已确认风险'
  if (issue.human_decision_state === 'ACCEPTED_RISK') return '已接受风险'
  if (issue.human_decision_state === 'FALSE_POSITIVE' || issue.human_decision_state === 'REJECTED') return '误报'
  if (issue.human_decision_state === 'MODIFIED') return '已修改'
  if (issue.human_decision_state === 'NEEDS_LAWYER_REVIEW' || issue.human_decision_state === 'NEEDS_MORE_REVIEW') return '需律师复核'
  return '待处理'
}

export default function IssueWorkspaceView({ summary, onRefresh }: Props) {
  const presentation = summary.presentation ?? fallbackPresentation(summary)
  const initialIssueId = presentation.top_risks[0]?.issue_id ?? summary.issues[0]?.issue_id ?? null
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null)
  const [detail, setDetail] = useState<IssueWorkspaceDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailMessage, setDetailMessage] = useState('选择一个风险点查看依据。')
  const [secondaryMessage, setSecondaryMessage] = useState<string | null>(null)
  const [secondaryBusy, setSecondaryBusy] = useState(false)

  useEffect(() => {
    if (!selectedIssueId) {
      setDetail(null)
      setDetailMessage('选择一个风险点查看依据。')
      return
    }
    let cancelled = false
    const load = async () => {
      setDetailLoading(true)
      setDetailMessage('正在读取风险依据…')
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/documents/${encodeURIComponent(summary.job_id)}/workspace/issues/${encodeURIComponent(selectedIssueId)}`,
        )
        const body = await response.json().catch(() => null)
        if (!response.ok) {
          const message = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
          throw new Error(message)
        }
        if (!cancelled) {
          setDetail(body as IssueWorkspaceDetail)
          setDetailMessage('风险依据已读取。')
        }
      } catch (error) {
        if (!cancelled) {
          setDetail(null)
          setDetailMessage(error instanceof Error ? error.message : '风险依据无法读取。')
        }
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [selectedIssueId, summary.job_id])

  const selectedIssue = useMemo(
    () => summary.issues.find((item) => item.issue_id === selectedIssueId),
    [selectedIssueId, summary.issues],
  )
  const selectedRisk = useMemo(
    () => presentation.top_risks.find((item) => item.issue_id === selectedIssueId),
    [presentation.top_risks, selectedIssueId],
  )
  const reportExportEnabled = summary.overall_state === 'COMPLETE' || summary.overall_state === 'HUMAN_REVIEW_REQUIRED'
  const stages = ['upload', 'ocr', 'structure', 'analysis', 'secondary', 'report']

  const openRisk = (risk: IssueWorkspaceRiskSummary) => {
    setSelectedIssueId(risk.issue_id)
  }

  const retrySecondary = async () => {
    setSecondaryBusy(true)
    setSecondaryMessage(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(summary.job_id)}/issue-secondary-review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: 'kimi' }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const message = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(message)
      }
      setSecondaryMessage('已重新提交争议复审并刷新报告。')
      onRefresh()
    } catch (error) {
      setSecondaryMessage(error instanceof Error ? error.message : '争议复审暂时无法提交。')
    } finally {
      setSecondaryBusy(false)
    }
  }

  return (
    <main className="legal-report-shell">
      <section className="legal-report-hero">
        <div>
          <span className="report-kicker">法律审查报告</span>
          <h1>{summary.document?.filename ?? '文档元数据不可用'}</h1>
          <p>{presentation.signing_recommendation}</p>
        </div>
        <div className={`report-risk-card ${riskClass(presentation.overall_risk)}`}>
          <span>总体风险</span>
          <strong>{presentation.overall_risk}</strong>
        </div>
      </section>

      <section className="report-progress-strip" aria-label="审查进度">
        {stages.map((stage) => {
          const state = stageState(summary, stage)
          return (
            <div className={stateClass(state)} key={stage}>
              <span />
              <strong>{stageLabel(stage)}</strong>
            </div>
          )
        })}
      </section>

      <section className="report-overview-grid">
        <article>
          <span>签署建议</span>
          <strong>{presentation.signing_recommendation}</strong>
        </article>
        <article>
          <span>证据可信度</span>
          <strong>{presentation.evidence_confidence}</strong>
        </article>
        <article>
          <span>争议复审</span>
          <strong>
            已复核 {presentation.secondary_review_status_counts.REVIEWED ?? 0} ·
            无需复核 {presentation.secondary_review_status_counts.SKIPPED_CLEAR ?? 0} ·
            待确认 {presentation.secondary_review_status_counts.PENDING_CONFIRMATION ?? 0}
          </strong>
          {(presentation.secondary_review_status_counts.PENDING_CONFIRMATION ?? 0) > 0 && (
            <button type="button" onClick={() => void retrySecondary()} disabled={secondaryBusy}>
              {secondaryBusy ? '提交中…' : '重新提交二审'}
            </button>
          )}
        </article>
      </section>

      {secondaryMessage && <p className="report-inline-message">{secondaryMessage}</p>}

      <section className="report-section">
        <div className="report-section-head">
          <div>
            <span className="report-kicker">关键风险</span>
            <h2>优先处理事项</h2>
          </div>
          <ReportExportControls
            jobId={summary.job_id}
            enabled={reportExportEnabled}
            outstandingHumanReview={summary.review.human_review_outstanding_required_count}
          />
        </div>

        {presentation.top_risks.length === 0 ? (
          <div className="report-empty-state">暂未形成优先风险项。</div>
        ) : (
          <div className="risk-summary-list">
            {presentation.top_risks.map((risk, index) => {
              const issue = summary.issues.find((item) => item.issue_id === risk.issue_id)
              return (
                <button type="button" className="risk-summary-card" key={risk.issue_id} onClick={() => openRisk(risk)}>
                  <span className="risk-index">{index + 1}</span>
                  <div>
                    <h3>{risk.title}</h3>
                    <p>{risk.reason}</p>
                    <small>{decisionText(issue)}</small>
                  </div>
                  <strong className={`risk-level-badge ${riskClass(risk.risk_level)}`}>{risk.risk_level}</strong>
                </button>
              )
            })}
          </div>
        )}
      </section>

      <section className="report-section">
        <span className="report-kicker">建议动作</span>
        {presentation.suggested_actions.length === 0 ? (
          <p className="report-muted">暂无独立修改建议。</p>
        ) : (
          <ol className="action-list">
            {presentation.suggested_actions.map((action) => <li key={action}>{action}</li>)}
          </ol>
        )}
      </section>

      {selectedIssueId && (
        <aside className="risk-detail-drawer" aria-label="风险详情抽屉">
          <div className="risk-detail-card">
            <div className="drawer-titlebar">
              <div>
                <span className="report-kicker">风险详情</span>
                <h2>{selectedRisk?.title ?? selectedIssue?.topic ?? '审查事项'}</h2>
              </div>
              <button type="button" onClick={() => setSelectedIssueId(null)} aria-label="关闭风险详情">
                ×
              </button>
            </div>
            <IssueReviewContextPane
              detail={detail}
              loading={detailLoading}
              message={detailMessage}
              onContractEvidence={() => undefined}
              onHumanReviewSaved={onRefresh}
            />
          </div>
        </aside>
      )}
    </main>
  )
}
