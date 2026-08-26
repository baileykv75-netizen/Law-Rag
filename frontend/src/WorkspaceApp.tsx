import { FormEvent, useEffect, useState } from 'react'
import IssueWorkspaceView from './IssueWorkspaceView'
import LegacyWorkspaceView, { type LegacyWorkspaceSummary } from './LegacyWorkspaceView'
import type { IssueWorkspaceSummary } from './issue-workspace-types'

import { API_BASE_URL } from './apiBase'

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
  const [message, setMessage] = useState('打开一份已完成或正在处理的合同审查报告。')
  const [summary, setSummary] = useState<WorkspaceResponse | null>(null)

  const loadWorkspace = async (requestedJobId: string) => {
    const normalized = requestedJobId.trim()
    if (!normalized || state === 'loading') return

    setState('loading')
    setMessage('正在读取合同审查报告…')
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
          ? '审查报告已打开。'
          : '已打开历史版本审查结果。',
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
          <div><strong>Law-Rag</strong><span>合同法律审查</span></div>
        </div>
        <div className="workstation-top-actions">
          <a href="/results">批量结果</a>
          <a href="/">上传合同</a>
        </div>
      </header>

      <section className="workspace-loader" aria-label="打开审计任务">
        <form onSubmit={submit}>
          <label htmlFor="workspace-job-id">任务编号</label>
          <input
            id="workspace-job-id"
            value={jobId}
            onChange={(event) => setJobId(event.target.value)}
            placeholder="粘贴任务编号"
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
          <h1>打开合同审查报告</h1>
          <p>从批量结果进入报告，或粘贴任务编号查看对应合同。</p>
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
