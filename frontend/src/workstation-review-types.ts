export type Severity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export type PrimaryFinding = {
  finding_id: string
  state: 'SUPPORTED_FINDING' | 'NO_FINDING' | 'INSUFFICIENT_EVIDENCE' | 'REVIEW_REQUIRED'
  evidence_sufficiency: string
  risk_category: string
  severity: Severity
  title: string
  reasoning_summary: string
  suggestion: string
  issue_ids: string[]
  canonical_object_ids: string[]
  contract_evidence_ids: string[]
  legal_evidence_ids: string[]
  review_reasons: string[]
}

export type SecondaryFinding = {
  review_id: string
  primary_finding_id: string
  assessment: 'SUPPORTED' | 'NOT_SUPPORTED' | 'REVIEW_REQUIRED' | 'INSUFFICIENT_EVIDENCE'
  severity: Severity
  reasoning_summary: string
  suggestion: string
  contract_evidence_ids: string[]
  legal_evidence_ids: string[]
  disagreement_categories: string[]
  review_reasons: string[]
}

export type PossibleOmission = {
  omission_id: string
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

export type FindingComparison = {
  comparison_id: string
  primary_finding_id: string
  risk_state: string
  severity: { primary: Severity; secondary: Severity; distance: number; state: string }
  contract_evidence: { state: string; shared: string[]; primary_only: string[]; secondary_only: string[] }
  legal_basis: { state: string; shared: string[]; primary_only: string[]; secondary_only: string[] }
  overall_state: string
  material_reasons: string[]
  follow_up: string
}

export type OmissionComparison = {
  omission_id: string
  risk_category: string
  severity: Severity
  contract_evidence_ids: string[]
  legal_evidence_ids: string[]
  overall_state: string
  follow_up: string
  reason: string
}

export type ReviewReport = {
  job_id: string
  as_of: string
  final_state: string
  primary_provider: string
  primary_model: string
  secondary_provider: string
  secondary_model: string
  primary_findings: PrimaryFinding[]
  secondary_reviews: SecondaryFinding[]
  possible_primary_omissions: PossibleOmission[]
  comparison: {
    overall_state: string
    follow_up: string
    finding_comparisons: FindingComparison[]
    omission_comparisons: OmissionComparison[]
  }
  action_trace: Array<{
    action_id: string
    cycle: number
    tool_name: string
    state: string
    reason: string
    input_evidence_ids: string[]
    output_evidence_ids: string[]
    provider_call_occurred: boolean
    private_contract_evidence_left_machine: boolean
    validation_or_error: string | null
  }>
  evidence_gathered: boolean
  final_reasons: string[]
  warnings: string[]
}

export type SelectedAuditItem = {
  itemType: 'finding' | 'omission'
  itemId: string
  title: string
  riskCategory: string
  primary?: PrimaryFinding
  secondary?: SecondaryFinding
  omission?: PossibleOmission
  comparison?: FindingComparison | OmissionComparison
  contractEvidenceIds: string[]
  legalEvidenceIds: string[]
}
