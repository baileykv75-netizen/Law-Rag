import { FormEvent, useEffect, useState } from 'react'
import IssueWorkspaceView from './IssueWorkspaceView'
import LegacyWorkspaceView, { type LegacyWorkspaceSummary } from './LegacyWorkspaceView'
import type { IssueWorkspaceSummary } from './issue-workspace-types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type WorkspaceResponse = LegacyWorkspaceSummary | IssueWorkspaceSummary
type LoadState = 'idle' | 'loading' | 'ready' | 'error'

function initialJobId() {
  return new URLSearchParams(window.location.search).get('job') ?? ''
}

function isIssueWorkspace(summary: WorkspaceResponse): summary is IssueWorkspaceSummary {
  return summary.architecture === 'ISSUE_V1'
}

export default function WorkspaceApp() {
  const [jobId, setJobId] = useState(initialJobId)
  const [state, setState] = useState<LoadState>('idle')
  const [message, setMessage] = useState('输入一个本机 Job ID，工作台只读取既有审计产物，不会触发 OCR、检索或模型调用。')
  const [summary, setSummary] = useState<WorkspaceResponse | null>(null)

  const loadWorkspace = async (requestedJobId: string) => {
    const normalized = requestedJobId.trim()
    if (!normalized || state === 'loading') return

    setState('loading')
    setMessage('正在解析任务架构并读取本机审计产物…')
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(normalized)}/workspace`)
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(detail)
      }
      if (!body || (body.architecture !== 'ISSUE_V1' && body.architecture !== 'LEGACY_RC2')) {
        throw new Error('工作台无法确认该任务的权威审计架构。')
      }

      const next = body as WorkspaceResponse
      setSummary(next)
      setJobId(next.job_id)
      setState('ready')
      setMessage(
        next.architecture === 'ISSUE_V1'
          ? '已读取 Stage 13 Issue 审计工作台；本次操作没有触发 Planner、DeepSeek 或 Kimi。'
          : '已读取 Legacy RC2 审计工作台；历史任务保持原 Stage 8–9 语义，没有被转换成新 Issue。',
      )
      const url = new URL(window.location.href)
      url.pathname = '/workspace'
      url.searchParams.set('job', next.job_id)
      window.history.replaceState({}, '', url)
    } catch (error) {
      setSummary(null)
      setState('error')
      setMessage(error instanceof Error ? error.message : '无法读取工作台。')
    }
  }

  useEffect(() => {
    const initial = initialJobId()
    if (initial) void loadWorkspace(initial)
    // Load once from the URL. Subsequent loads are explicit form submissions.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void loadWorkspace(jobId)
  }

  return (
    <main className="workstation-shell">
      <header className="workstation-topbar">
        <div className="workstation-brand">
          <span className="workstation-mark">LR</span>
          <div><strong>Law-Rag</strong><span>专业合同审计工作台</span></div>
        </div>
        <div className="workstation-top-actions">
          <span className="local-only-chip">LOCAL · REVIEW WORKSPACE</span>
          <a href="/">返回合同导入</a>
        </div>
      </header>

      <section className="workspace-loader" aria-label="打开审计任务">
        <form onSubmit={submit}>
          <label htmlFor="workspace-job-id">Job ID</label>
          <input
            id="workspace-job-id"
            value={jobId}
            onChange={(event) => setJobId(event.target.value)}
            placeholder="粘贴本机审计任务的 job_id"
            autoComplete="off"
          />
          <button type="submit" disabled={!jobId.trim() || state === 'loading'}>
            {state === 'loading' ? '读取中…' : '打开工作台'}
          </button>
        </form>
        <div className={`workspace-message ${state === 'error' ? 'is-error' : ''}`}>{message}</div>
      </section>

      {!summary ? (
        <section className="workspace-empty-state">
          <div className="empty-illustration">§</div>
          <h1>从一个已存在的审计任务开始</h1>
          <p>工作台会先确认任务属于 ISSUE_V1 还是 LEGACY_RC2；打开页面不会重新识别合同、重新检索法律或调用 DeepSeek / Kimi。</p>
        </section>
      ) : isIssueWorkspace(summary) ? (
        <IssueWorkspaceView
          key={summary.job_id}
          summary={summary}
          onRefresh={() => { void loadWorkspace(summary.job_id) }}
        />
      ) : (
        <LegacyWorkspaceView key={summary.job_id} summary={summary} />
      )}
    </main>
  )
}
