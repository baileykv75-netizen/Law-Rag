import { useCallback, useState } from 'react'
import AuditQueuePane from './AuditQueuePane'
import HumanDecisionPanel from './HumanDecisionPanel'
import ReviewContextPane from './ReviewContextPane'
import SourceViewerPane from './SourceViewerPane'
import type { SelectedAuditItem } from './workstation-review-types'

export type ArtifactState = 'READY' | 'MISSING' | 'NOT_REQUIRED' | 'INVALID'
export type OverallState = 'COMPLETE' | 'INCOMPLETE' | 'HUMAN_REVIEW_REQUIRED' | 'INVALID'

export type LegacyWorkspaceSummary = {
  schema_version: string
  job_id: string
  architecture: 'LEGACY_RC2'
  overall_state: OverallState
  source_available: boolean
  document: {
    filename: string
    media_type: string
    document_kind: string
    page_count: number
    route: string
    native_text_pages: number
    ocr_required_pages: number
    ocr_used: boolean
    low_confidence_ocr_pages: number
    failed_ocr_pages: number
    no_text_ocr_pages: number
  } | null
  stages: Array<{
    stage: string
    label: string
    state: ArtifactState
    artifact: string | null
    detail: string
  }>
  review: {
    primary_available: boolean
    primary_provider: string | null
    primary_model: string | null
    primary_finding_count: number
    secondary_available: boolean
    secondary_provider: string | null
    secondary_model: string | null
    secondary_review_count: number
    possible_omission_count: number
    comparison_available: boolean
    final_review_state: string | null
    agent_action_count: number
  }
  source_uncertainty: string[]
  warnings: string[]
}

function artifactLabel(state: ArtifactState) {
  if (state === 'READY') return '已就绪'
  if (state === 'NOT_REQUIRED') return '无需执行'
  if (state === 'INVALID') return '完整性异常'
  return '尚未完成'
}

function overallLabel(state: OverallState) {
  if (state === 'COMPLETE') return '审计链完整'
  if (state === 'HUMAN_REVIEW_REQUIRED') return '需要人工复核'
  if (state === 'INVALID') return '存在完整性异常'
  return '审计链未完成'
}

function stateClass(state: ArtifactState | OverallState) {
  if (state === 'READY' || state === 'COMPLETE') return 'is-ready'
  if (state === 'NOT_REQUIRED') return 'is-muted'
  if (state === 'HUMAN_REVIEW_REQUIRED') return 'is-review'
  if (state === 'INVALID') return 'is-invalid'
  return 'is-missing'
}

type Props = { summary: LegacyWorkspaceSummary }

export default function LegacyWorkspaceView({ summary }: Props) {
  const [selectedAuditItem, setSelectedAuditItem] = useState<SelectedAuditItem | null>(null)
  const [selectedContractEvidenceId, setSelectedContractEvidenceId] = useState<string | null>(null)
  const [selectedLegalEvidenceId, setSelectedLegalEvidenceId] = useState<string | null>(null)

  const handleAuditSelection = useCallback((item: SelectedAuditItem | null) => {
    setSelectedAuditItem(item)
  }, [])
  const handleContractEvidence = useCallback((evidenceId: string) => {
    setSelectedContractEvidenceId(evidenceId)
  }, [])
  const handleLegalEvidence = useCallback((evidenceId: string) => {
    setSelectedLegalEvidenceId(evidenceId)
  }, [])

  return (
    <>
      <section className="workspace-summarybar legacy-workspace-summarybar">
        <div className="summary-document">
          <span className="eyebrow">CURRENT JOB · LEGACY_RC2</span>
          <h1>{summary.document?.filename ?? '文档元数据不可用'}</h1>
          <div className="summary-meta">
            <span>{summary.document ? `${summary.document.page_count} 页` : '页数未知'}</span>
            <span>{summary.document?.document_kind?.toUpperCase() ?? 'UNKNOWN'}</span>
            <span>{summary.document?.route ?? 'ROUTE UNKNOWN'}</span>
            <span className={summary.source_available ? 'source-ok' : 'source-broken'}>
              {summary.source_available ? '源文件可用' : '源文件异常'}
            </span>
          </div>
        </div>
        <div className={`overall-state ${stateClass(summary.overall_state)}`}>
          <span>Legacy Stage 9 最终状态</span>
          <strong>{overallLabel(summary.overall_state)}</strong>
          <small>{summary.review.final_review_state ?? '尚无 Stage 9 最终状态'}</small>
        </div>
      </section>

      <div className="legacy-workspace-notice">
        该任务使用旧 RC2 / Stage 8–9 审计产物。Law-Rag 保留原始视图，不会把旧 Finding/Omission 伪装成 Stage 13 AuditPlan Issue。
      </div>

      <section className="workstation-grid">
        <aside className="workstation-pane source-pane" aria-label="合同来源与处理链">
          <div className="pane-heading">
            <div><span className="eyebrow">SOURCE</span><h2>合同来源</h2></div>
            <span>{summary.document?.page_count ?? '—'} 页</span>
          </div>

          {summary.document ? (
            <SourceViewerPane
              jobId={summary.job_id}
              documentKind={summary.document.document_kind}
              pageCount={summary.document.page_count}
              sourceAvailable={summary.source_available}
              requestedEvidenceId={selectedContractEvidenceId}
            />
          ) : (
            <div className="source-viewer-error"><strong>文档元数据不可用</strong><p>没有可靠的页数/文档类型信息，工作台不会猜测源页。</p></div>
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
            <div className="subheading">Legacy 处理链</div>
            {summary.stages.map((item) => (
              <div className="stage-row" key={`${item.stage}-${item.label}`}>
                <span className={`stage-dot ${stateClass(item.state)}`} />
                <div><strong>Stage {item.stage} · {item.label}</strong><span>{item.detail}</span></div>
                <em className={stateClass(item.state)}>{artifactLabel(item.state)}</em>
              </div>
            ))}
          </div>
        </aside>

        <section className="workstation-pane findings-pane" aria-label="旧审计结果队列">
          <div className="pane-heading">
            <div><span className="eyebrow">LEGACY AUDIT QUEUE</span><h2>审计结果</h2></div>
            <span>{summary.review.primary_finding_count} 项主审发现</span>
          </div>

          <div className="review-metrics">
            <article><span>DeepSeek 主审</span><strong>{summary.review.primary_finding_count}</strong><small>{summary.review.primary_available ? '报告已存在' : '尚未生成'}</small></article>
            <article><span>Kimi 二审</span><strong>{summary.review.secondary_review_count}</strong><small>{summary.review.secondary_available ? '报告已存在' : '尚未生成'}</small></article>
            <article className={summary.review.possible_omission_count > 0 ? 'needs-attention' : ''}><span>可能漏审项</span><strong>{summary.review.possible_omission_count}</strong><small>独立保留，不自动并入主审</small></article>
            <article className={summary.review.agent_action_count > 0 ? 'needs-attention' : ''}><span>Agent 动作</span><strong>{summary.review.agent_action_count}</strong><small>Stage 9 白名单补证据</small></article>
          </div>

          <AuditQueuePane
            jobId={summary.job_id}
            reportAvailable={summary.review.comparison_available}
            onSelectionChange={handleAuditSelection}
            onContractEvidence={handleContractEvidence}
            onLegalEvidence={handleLegalEvidence}
          />
        </section>

        <aside className="workstation-pane evidence-pane" aria-label="旧证据、法律与双模型复核上下文">
          <div className="pane-heading"><div><span className="eyebrow">LEGACY REVIEW CONTEXT</span><h2>证据与复核</h2></div></div>

          <div className="provider-summary-row">
            <div className="provider-card"><span>PRIMARY</span><strong>{summary.review.primary_provider ?? '未生成'}</strong><small>{summary.review.primary_model ?? '—'}</small></div>
            <div className="provider-card"><span>SECONDARY</span><strong>{summary.review.secondary_provider ?? '未生成'}</strong><small>{summary.review.secondary_model ?? '—'}</small></div>
          </div>

          <ReviewContextPane
            selectedItem={selectedAuditItem}
            legalEvidenceId={selectedLegalEvidenceId}
            onContractEvidence={handleContractEvidence}
            onLegalEvidence={handleLegalEvidence}
            finalReviewState={summary.review.final_review_state}
            agentActionCount={summary.review.agent_action_count}
          />

          <HumanDecisionPanel
            jobId={summary.job_id}
            reportAvailable={summary.review.comparison_available}
            selectedItem={selectedAuditItem}
          />

          {summary.warnings.length > 0 && (
            <div className="warning-panel"><div className="subheading">任务级警告</div><ul>{summary.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>
          )}
        </aside>
      </section>
    </>
  )
}
