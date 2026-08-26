export type ArtifactState = 'READY' | 'MISSING' | 'NOT_REQUIRED' | 'INVALID'
export type OverallState = 'COMPLETE' | 'INCOMPLETE' | 'HUMAN_REVIEW_REQUIRED' | 'INVALID'
export type Severity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type ReviewPriority = 'NORMAL' | 'IMPORTANT' | 'HIGH_ATTENTION'
export type HumanDecisionState = 'UNREVIEWED' | 'CONFIRMED' | 'REJECTED' | 'NEEDS_MORE_REVIEW'
  | 'ACCEPTED_RISK' | 'FALSE_POSITIVE' | 'MODIFIED' | 'NEEDS_LAWYER_REVIEW'
export type SecondaryReviewStatus = 'REVIEWED' | 'SKIPPED_CLEAR' | 'PENDING_CONFIRMATION'

export type WorkspaceDocument = {
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
}

export type WorkspaceStage = {
  stage: string
  label: string
  state: ArtifactState
  artifact: string | null
  detail: string
}

export type IssueWorkspaceCoverage = {
  planning_mode: 'DIRECT' | 'HIERARCHICAL'
  contract_type: string
  coverage_complete: boolean
  canonical_object_count: number
  reviewed_with_issue_count: number
  reviewed_no_specific_issue_count: number
  issue_count: number
}

export type IssueWorkspaceReview = {
  primary_available: boolean
  primary_provider: string | null
  primary_model: string | null
  primary_completed_issue_count: number
  secondary_available: boolean
  secondary_provider: string | null
  secondary_model: string | null
  secondary_completed_issue_count: number
  secondary_reviewed_count: number
  secondary_skipped_clear_count: number
  secondary_pending_confirmation_count: number
  comparison_available: boolean
  final_review_state: 'NO_MANDATORY_REVIEW' | 'HUMAN_REVIEW_REQUIRED' | null
  compared_issue_count: number
  human_review_required_count: number
  material_disagreement_count: number
  possible_omission_count: number
  insufficient_evidence_count: number
  review_required_count: number
  consistent_with_review_count: number
  human_review_available: boolean
  human_review_revision_count: number
  human_review_resolved_required_count: number
  human_review_outstanding_required_count: number
  human_review_stale_latest_count: number
}

export type IssueQueueItem = {
  issue_id: string
  topic: string
  priority: ReviewPriority
  source_labels: string[]
  contract_evidence_count: number
  legal_evidence_count: number
  legal_support_state: string | null
  primary_state: string | null
  primary_severity: Severity | null
  secondary_assessment: string | null
  secondary_review_status: SecondaryReviewStatus | null
  coverage_assessment: string | null
  comparison_state: string | null
  requires_human_review: boolean
  human_decision_state: HumanDecisionState | null
  human_decision_revision: number | null
  human_decision_stale: boolean
}

export type IssueWorkspaceRiskSummary = {
  issue_id: string
  title: string
  severity: Severity
  risk_level: string
  reason: string
  suggested_action: string
  requires_decision: boolean
  secondary_review_status: SecondaryReviewStatus
}

export type IssueWorkspacePresentationSummary = {
  overall_risk: string
  signing_recommendation: string
  top_risks: IssueWorkspaceRiskSummary[]
  suggested_actions: string[]
  evidence_confidence: string
  secondary_review_status_counts: Record<string, number>
}

export type IssueWorkspaceSummary = {
  schema_version: string
  engine_version: string
  job_id: string
  architecture: 'ISSUE_V1'
  overall_state: OverallState
  source_available: boolean
  document: WorkspaceDocument | null
  stages: WorkspaceStage[]
  coverage: IssueWorkspaceCoverage | null
  review: IssueWorkspaceReview
  presentation: IssueWorkspacePresentationSummary | null
  issues: IssueQueueItem[]
  source_uncertainty: string[]
  warnings: string[]
}

export type PlanIssue = {
  issue_id: string
  topic: string
  priority: ReviewPriority
  sources: string[]
  why_review: string[]
  contract_object_ids: string[]
  contract_evidence_ids: string[]
  questions: string[]
  retrieval_queries: string[]
  rule_result_ids: string[]
  legacy_hint_topics: string[]
}

export type LegalEvidenceHit = {
  legal_evidence_id: string
  matched_query_indexes: number[]
  best_rank: number
  candidate: {
    legal_evidence_id: string
    authority_id: string
    authority_title: string
    version_id: string
    article_id: string
    article_token: string
    article_text: string
    coverage_type: string
    effective_date: string
    end_date_exclusive: string | null
    exact_hit: boolean
    matched_snippet: string | null
  }
}

export type IssuePrimaryResult = {
  issue_id: string
  topic: string
  state: string
  evidence_sufficiency: string
  legal_support_state: string
  legal_conclusion: boolean
  risk_category: string
  severity: Severity
  title: string
  reasoning_summary: string
  suggestion: string
  canonical_object_ids: string[]
  contract_evidence_ids: string[]
  legal_evidence_ids: string[]
  review_reasons: string[]
}

export type IssueSecondaryResult = {
  issue_id: string
  topic: string
  primary_state: string
  review_status?: SecondaryReviewStatus
  assessment: string
  coverage_assessment: string
  severity: Severity
  reasoning_summary: string
  suggestion: string
  contract_evidence_ids: string[]
  legal_evidence_ids: string[]
  review_reasons: string[]
  omission_title: string | null
  omission_reasoning: string | null
}

export type EvidenceAlignment = {
  state: string
  shared: string[]
  primary_only: string[]
  secondary_only: string[]
}

export type IssueComparison = {
  issue_id: string
  topic: string
  plan_priority: ReviewPriority
  primary_state: string
  primary_evidence_sufficiency: string
  legal_support_state: string
  primary_legal_conclusion: boolean
  secondary_assessment: string
  coverage_assessment: string
  primary_severity: Severity
  secondary_severity: Severity
  severity_distance: number
  contract_evidence: EvidenceAlignment
  legal_evidence: EvidenceAlignment
  overall_state: string
  requires_human_review: boolean
  reasons: string[]
  omission_title: string | null
  omission_reasoning: string | null
}

export type IssueWorkspaceDetail = {
  schema_version: string
  engine_version: string
  job_id: string
  issue_id: string
  as_of: string | null
  plan_issue: PlanIssue
  legal_support_state: string | null
  legal_evidence: LegalEvidenceHit[]
  primary: IssuePrimaryResult | null
  secondary: IssueSecondaryResult | null
  comparison: IssueComparison | null
  warnings: string[]
}

export type HumanDecisionRevision = {
  schema_version: string
  decision_id: string
  revision: number
  job_id: string
  target_type: 'finding' | 'omission' | 'issue'
  target_id: string
  state: HumanDecisionState
  reviewer_note: string
  decided_at: string
  contract_evidence_ids: string[]
  legal_evidence_ids: string[]
  review_report_fingerprint: string
  is_stale: boolean
}

export type IssueHumanReviewView = {
  schema_version: string
  job_id: string
  authoritative_architecture: 'ISSUE_V1'
  current_review_report_artifact: 'issue-review-report.json'
  current_review_report_fingerprint: string
  revisions: HumanDecisionRevision[]
  latest_by_target: Record<string, HumanDecisionRevision>
}
