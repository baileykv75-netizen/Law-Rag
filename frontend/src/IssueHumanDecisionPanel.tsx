import { FormEvent, useEffect, useMemo, useState } from 'react'
import type {
  HumanDecisionState,
  IssueHumanReviewView,
  IssueWorkspaceDetail,
} from './issue-workspace-types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type Props = {
  detail: IssueWorkspaceDetail
  onSaved: () => void
}

function decisionLabel(value: HumanDecisionState) {
  if (value === 'CONFIRMED') return '确认当前结论'
  if (value === 'REJECTED') return '不采纳当前结论'
  if (value === 'NEEDS_MORE_REVIEW') return '继续复核'
  return '未形成决定'
}

export default function IssueHumanDecisionPanel({ detail, onSaved }: Props) {
  const [view, setView] = useState<IssueHumanReviewView | null>(null)
  const [state, setState] = useState<HumanDecisionState>('UNREVIEWED')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const reportAvailable = detail.comparison !== null

  useEffect(() => {
    setView(null)
    if (!reportAvailable) {
      setMessage('需要有效 issue-review-report.json 后才能记录 Issue 人工决定。')
      return
    }
    let cancelled = false
    const load = async () => {
      setMessage('正在读取本机 Issue 人工复核记录…')
      try {
        const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(detail.job_id)}/human-review`)
        const body = await response.json().catch(() => null)
        if (!response.ok) {
          const errorDetail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
          throw new Error(errorDetail)
        }
        if (!body || body.authoritative_architecture !== 'ISSUE_V1') {
          throw new Error('人工复核 API 没有返回 ISSUE_V1 权威视图。')
        }
        if (!cancelled) {
          setView(body as IssueHumanReviewView)
          setMessage('人工决定只追加到本机 human-review.json；不会改写模型报告。')
        }
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : '无法读取 Issue 人工复核记录。')
      }
    }
    void load()
    return () => { cancelled = true }
  }, [detail.job_id, reportAvailable])

  const key = `issue:${detail.issue_id}`
  const latest = view?.latest_by_target[key] ?? null
  const history = useMemo(() => {
    if (!view) return []
    return view.revisions
      .filter((item) => item.target_type === 'issue' && item.target_id === detail.issue_id)
      .sort((a, b) => b.revision - a.revision)
  }, [detail.issue_id, view])

  useEffect(() => {
    if (latest) {
      setState(latest.state)
      setNote(latest.reviewer_note)
    } else {
      setState('UNREVIEWED')
      setNote('')
    }
  }, [detail.issue_id, latest])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy || !reportAvailable) return
    setBusy(true)
    setMessage('正在追加 Issue 人工复核 revision…')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/documents/${encodeURIComponent(detail.job_id)}/human-review/decisions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_type: 'issue',
            target_id: detail.issue_id,
            state,
            reviewer_note: note,
          }),
        },
      )
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const errorDetail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(errorDetail)
      }
      if (!body || body.authoritative_architecture !== 'ISSUE_V1') {
        throw new Error('保存后未返回 ISSUE_V1 人工复核视图。')
      }
      setView(body as IssueHumanReviewView)
      setMessage('已追加新的 Issue revision；服务端已快照当前合同 Evidence、Legal Evidence 与 report fingerprint。')
      onSaved()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Issue 人工决定保存失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="human-decision-panel issue-human-decision-panel">
      <div className="context-eyebrow">HUMAN REVIEW · ISSUE IDENTITY</div>
      <div className="human-target-heading">
        <strong>{detail.plan_issue.topic}</strong>
        <span>issue · {detail.issue_id}</span>
      </div>

      {detail.comparison?.requires_human_review ? (
        <p className="issue-human-required">确定性 Comparison 已标记该 Issue 必须人工复核。</p>
      ) : (
        <p className="human-panel-message">该 Issue 没有强制人工复核要求，但仍可留下人工决定。</p>
      )}

      {latest && (
        <div className={`latest-decision ${latest.is_stale ? 'is-stale' : ''}`}>
          <span>当前最新 Issue 记录</span>
          <strong>{decisionLabel(latest.state)} · revision {latest.revision}</strong>
          <small>{new Date(latest.decided_at).toLocaleString()}</small>
          <small>合同 Evidence {latest.contract_evidence_ids.length} · Legal Evidence {latest.legal_evidence_ids.length}</small>
          {latest.is_stale && <em>STALE · issue-review-report 已变化，该决定不能关闭当前复核</em>}
        </div>
      )}

      <form onSubmit={submit}>
        <div className="decision-options" role="group" aria-label="Issue 人工决定状态">
          {(['CONFIRMED', 'REJECTED', 'NEEDS_MORE_REVIEW', 'UNREVIEWED'] as HumanDecisionState[]).map((value) => (
            <button
              type="button"
              key={value}
              className={state === value ? 'is-active' : ''}
              onClick={() => setState(value)}
            >
              {decisionLabel(value)}
            </button>
          ))}
        </div>
        <label htmlFor={`issue-human-review-note-${detail.issue_id}`}>复核备注</label>
        <textarea
          id={`issue-human-review-note-${detail.issue_id}`}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="说明为什么确认/不采纳当前结论，或者还需要核查什么。"
          rows={4}
          maxLength={4000}
        />
        <button className="save-human-decision" type="submit" disabled={busy || !reportAvailable}>
          {busy ? '保存中…' : '追加 Issue 人工决定 revision'}
        </button>
      </form>

      <p className="human-panel-message">{message}</p>

      {history.length > 0 && (
        <div className="human-history">
          <div className="context-eyebrow">ISSUE REVISION HISTORY</div>
          {history.map((item) => (
            <article key={item.decision_id} className={item.is_stale ? 'is-stale' : ''}>
              <div>
                <strong>r{item.revision} · {decisionLabel(item.state)}</strong>
                <span>{new Date(item.decided_at).toLocaleString()}</span>
              </div>
              {item.reviewer_note && <p>{item.reviewer_note}</p>}
              <small>合同 Evidence {item.contract_evidence_ids.length} · Legal Evidence {item.legal_evidence_ids.length}</small>
              {item.is_stale && <em>基于旧 issue-review-report</em>}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
