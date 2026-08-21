import { useEffect, useState } from 'react'
import IssueAuditQueuePane from './IssueAuditQueuePane'
import IssueReviewContextPane from './IssueReviewContextPane'
import SourceViewerPane from './SourceViewerPane'
import type {
  ArtifactState,
  IssueQueueItem,
  IssueWorkspaceDetail,
  IssueWorkspaceSummary,
  OverallState,
} from './issue-workspace-types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

function artifactLabel(state: ArtifactState) {
  if (state === 'READY') return '已就绪'
  if (state === 'NOT_REQUIRED') return '无需执行'
  if (state === 'INVALID') return '完整性异常'
  return '尚未完成'
}

function overallLabel(state: OverallState) {
  if (state === 'COMPLETE') return 'Issue 审计链完整'
  if (state === 'HUMAN_REVIEW_REQUIRED') return '需要人工复核'
  if (state === 'INVALID') return '存在完整性异常'
  return 'Issue 审计链未完成'
}

function stateClass(state: ArtifactState | OverallState) {
  if (state === 'READY' || state === 'COMPLETE') return 'is-ready'
  if (state === 'NOT_REQUIRED') return 'is-muted'
  if (state === 'HUMAN_REVIEW_REQUIRED') return 'is-review'
  if (state === 'INVALID') return 'is-invalid'
  return 'is-missing'
}

type Props = {
  summary: IssueWorkspaceSummary
  onRefresh: () => void
}

export default function IssueWorkspaceView({ summary, onRefresh }: Props) {
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(summary.issues[0]?.issue_id ?? null)
  const [detail, setDetail] = useState<IssueWorkspaceDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailMessage, setDetailMessage] = useState(
    summary.issues.length ? '正在读取第一个 AuditPlan Issue…' : 'Audit Planner 尚未产生可查看的 Issue。',
  )
  const [selectedContractEvidenceId, setSelectedContractEvidenceId] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedIssueId) {
      setDetail(null)
      return
    }
    let cancelled = false
    const load = async () => {
      setDetailLoading(true)
      setDetailMessage('正在读取本地 Issue 审计上下文…')
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
          setDetailMessage('已读取本地 Issue 审计链；未触发任何模型调用。')
        }
      } catch (error) {
        if (!cancelled) {
          setDetail(null)
          setDetailMessage(error instanceof Error ? error.message : 'Issue 上下文无法读取。')
        }
      } finally {
        if (!cancelled) setDetailLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [selectedIssueId, summary.job_id])

  const handleIssueSelect = (issue: IssueQueueItem) => {
    setSelectedIssueId(issue.issue_id)
    setSelectedContractEvidenceId(null)
  }

  const coverage = summary.coverage
  const reviewedCoverageCount = coverage
    ? coverage.reviewed_with_issue_count + coverage.reviewed_no_specific_issue_count
    : 0

  return (
    <>
      <section className="workspace-summarybar issue-summarybar">
        <div className="summary-document">
          <span className="eyebrow">CURRENT JOB · ISSUE_V1</span>
          <h1>{summary.document?.filename ?? '文档元数据不可用'}</h1>
          <div className="summary-meta">
            <span>{summary.document ? `${summary.document.page_count} 页` : '页数未知'}</span>
            <span>{coverage?.contract_type ?? 'CONTRACT TYPE UNKNOWN'}</span>
            <span>{coverage?.planning_mode ?? 'PLANNING PENDING'}</span>
            <span className={summary.source_available ? 'source-ok' : 'source-broken'}>
              {summary.source_available ? '源文件可用' : '源文件异常'}
            </span>
          </div>
        </div>
        <div className={`overall-state ${stateClass(summary.overall_state)}`}>
          <span>Stage 13G 最终状态</span>
          <strong>{overallLabel(summary.overall_state)}</strong>
          <small>
            {summary.review.human_review_required_count > 0
              ? `人工复核 ${summary.review.human_review_resolved_required_count}/${summary.review.human_review_required_count}`
              : (summary.review.final_review_state ?? '尚无 Issue Review Report')}
          </small>
        </div>
      </section>

      <section className="issue-coverage-strip" aria-label="审计规划覆盖">
        <div>
          <span className="eyebrow">PLANNING COVERAGE</span>
          <strong>{coverage ? `${reviewedCoverageCount} / ${coverage.canonical_object_count}` : '—'}</strong>
          <small>{coverage ? (coverage.coverage_complete ? 'Canonical objects 全部进入规划覆盖' : '规划覆盖不完整') : 'AuditPlan 尚未生成'}</small>
        </div>
        <div><span>形成 Issue</span><strong>{coverage?.reviewed_with_issue_count ?? '—'}</strong><small>REVIEWED_WITH_ISSUE</small></div>
        <div><span>无特定 Issue</span><strong>{coverage?.reviewed_no_specific_issue_count ?? '—'}</strong><small>不等于法律安全</small></div>
        <div><span>AuditPlan Issues</span><strong>{coverage?.issue_count ?? 0}</strong><small>全部 Issue 均可展开</small></div>
        <div className={summary.review.human_review_outstanding_required_count > 0 ? 'needs-attention' : ''}>
          <span>人工复核待办</span><strong>{summary.review.human_review_outstanding_required_count}</strong><small>已完成 {summary.review.human_review_resolved_required_count}</small>
        </div>
      </section>

      {!coverage?.coverage_complete && coverage && (
        <div className="coverage-global-warning">审计规划覆盖不完整。工作台不会把“没有形成 Issue”解释为“合同安全”，Issue 人工决定也不能豁免未覆盖文本。</div>
      )}

      <section className="workstation-grid issue-workstation-grid">
        <aside className="workstation-pane source-pane" aria-label="合同来源与 Stage 13 处理链">
          <div className="pane-heading">
            <div><span className="eyebrow">SOURCE</span><h2>合同来源</h2></div>
            <span>{summary.document?.page_count ?? '—'} 页</span>
          </div>

          {summary.document ? (
            <SourceViewerPane
              jobId={summary.job_id}
              pageCount={summary.document.page_count}
              sourceAvailable={summary.source_available}
              requestedEvidenceId={selectedContractEvidenceId}
            />
          ) : (
            <div className="source-viewer-error"><strong>文档元数据不可用</strong><p>没有可靠页数信息，工作台不会猜测源页。</p></div>
          )}

          {summary.document && (
            <div className="document-facts">
              <div><span>原生文本页</span><strong>{summary.document.native_text_pages}</strong></div>
              <div><span>需要 OCR 页</span><strong>{summary.document.ocr_required_pages}</strong></div>
              <div><span>实际使用 OCR</span><strong>{summary.document.ocr_used ? '是' : '否'}</strong></div>
              <div><span>低置信 OCR 页</span><strong>{summary.document.low_confidence_ocr_pages}</strong></div>
            </div>
          )}

          <div className="stage-timeline">
            <div className="subheading">权威处理链</div>
            {summary.stages.map((item) => (
              <div className="stage-row" key={`${item.stage}-${item.label}`}>
                <span className={`stage-dot ${stateClass(item.state)}`} />
                <div><strong>Stage {item.stage} · {item.label}</strong><span>{item.detail}</span></div>
                <em className={stateClass(item.state)}>{artifactLabel(item.state)}</em>
              </div>
            ))}
          </div>
        </aside>

        <section className="workstation-pane findings-pane" aria-label="AuditPlan Issue 队列">
          <div className="pane-heading">
            <div><span className="eyebrow">AUDIT PLAN</span><h2>逐项审计</h2></div>
            <span>{summary.issues.length} 个 Issue</span>
          </div>

          <div className="review-metrics issue-review-metrics">
            <article><span>DeepSeek 已审</span><strong>{summary.review.primary_completed_issue_count}</strong><small>{summary.review.primary_available ? '逐 Issue checkpoint 可用' : '尚未生成'}</small></article>
            <article><span>Kimi 已复核</span><strong>{summary.review.secondary_completed_issue_count}</strong><small>{summary.review.secondary_available ? 'finding + coverage' : '尚未生成'}</small></article>
            <article className={summary.review.human_review_outstanding_required_count > 0 ? 'needs-attention' : ''}><span>人工待复核</span><strong>{summary.review.human_review_outstanding_required_count}</strong><small>Fresh final decision required</small></article>
            <article className={summary.review.human_review_stale_latest_count > 0 ? 'needs-attention' : ''}><span>过期人工决定</span><strong>{summary.review.human_review_stale_latest_count}</strong><small>report 已变化</small></article>
          </div>

          <IssueAuditQueuePane issues={summary.issues} selectedIssueId={selectedIssueId} onSelect={handleIssueSelect} />
        </section>

        <aside className="workstation-pane evidence-pane" aria-label="Issue 证据与双模型复核上下文">
          <div className="pane-heading">
            <div><span className="eyebrow">ISSUE REVIEW CONTEXT</span><h2>证据与复核</h2></div>
          </div>

          <div className="provider-summary-row">
            <div className="provider-card"><span>PRIMARY</span><strong>{summary.review.primary_provider ?? '未生成'}</strong><small>{summary.review.primary_model ?? '—'}</small></div>
            <div className="provider-card"><span>SECONDARY</span><strong>{summary.review.secondary_provider ?? '未生成'}</strong><small>{summary.review.secondary_model ?? '—'}</small></div>
          </div>

          <IssueReviewContextPane
            detail={detail}
            loading={detailLoading}
            message={detailMessage}
            onContractEvidence={setSelectedContractEvidenceId}
            onHumanReviewSaved={onRefresh}
          />

          {summary.warnings.length > 0 && (
            <div className="warning-panel"><div className="subheading">任务级警告</div><ul>{summary.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>
          )}
        </aside>
      </section>
    </>
  )
}
