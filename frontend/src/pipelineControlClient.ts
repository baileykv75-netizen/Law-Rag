export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export type ProviderExecutionMode = 'AUTO_CONTINUE' | 'REQUIRE_APPROVAL' | 'LOCAL_ONLY'

export type PipelineStatus =
  | 'QUEUED'
  | 'WAITING_WORKER'
  | 'RUNNING'
  | 'WAITING_CONFIGURATION'
  | 'WAITING_OPTIONAL_COMPONENT'
  | 'PAUSED_BEFORE_PROVIDER'
  | 'CANCEL_REQUESTED'
  | 'CANCELLED'
  | 'FAILED'
  | 'COMPLETE'

export type PipelineStage =
  | 'INGEST'
  | 'OCR'
  | 'STRUCTURE'
  | 'RULES'
  | 'AUDIT_PLAN'
  | 'ISSUE_LEGAL_CONTEXT'
  | 'ISSUE_PRIMARY_AUDIT'
  | 'ISSUE_SECONDARY_REVIEW'
  | 'ISSUE_REVIEW_REPORT'
  // Legacy RC2 stages remain parseable for persisted historical jobs.
  | 'PRIMARY_AUDIT'
  | 'SECONDARY_REVIEW'
  | 'REVIEW_REPORT'
  | 'COMPLETE'

export type PipelineReport = {
  status: PipelineStatus
  current_stage: PipelineStage
  progress_percent: number
  failure_code: string | null
  failure_detail: string | null
}

export type PipelineControl = {
  provider_mode: ProviderExecutionMode
  provider_approved: boolean
  cancel_requested: boolean
  active_provider: string | null
}

type ControlActionResponse = {
  control: PipelineControl
  provider_in_flight: boolean
  detail: string
}

async function safeDetail(response: Response, fallback: string) {
  try {
    const payload = (await response.json()) as { detail?: string }
    return payload.detail ?? fallback
  } catch {
    return fallback
  }
}

async function postPipelineReport(jobId: string, action: string, fallback: string): Promise<PipelineReport> {
  const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/pipeline/${action}`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(await safeDetail(response, `${fallback}（HTTP ${response.status}）。`))
  return (await response.json()) as PipelineReport
}

export async function approveProvider(jobId: string) {
  return postPipelineReport(jobId, 'approve-provider', '无法批准云端审计')
}

export async function pauseFutureProviders(jobId: string): Promise<PipelineControl> {
  const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/pipeline/pause-provider`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(await safeDetail(response, `无法暂停后续云端调用（HTTP ${response.status}）。`))
  return (await response.json()) as PipelineControl
}

export async function cancelPipeline(jobId: string): Promise<ControlActionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/pipeline/cancel`, {
    method: 'POST',
  })
  if (!response.ok) throw new Error(await safeDetail(response, `无法取消审计（HTTP ${response.status}）。`))
  return (await response.json()) as ControlActionResponse
}

export async function resumeCancelledPipeline(jobId: string) {
  return postPipelineReport(jobId, 'resume', '无法重新开始已取消的审计')
}
