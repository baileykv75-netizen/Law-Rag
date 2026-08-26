import { FormEvent, useEffect, useMemo, useState } from 'react'
import type {
  HumanDecisionState,
  IssueHumanReviewView,
  IssueWorkspaceDetail,
} from './issue-workspace-types'

import { API_BASE_URL } from './apiBase'

type Props = {
  detail: IssueWorkspaceDetail
  onSaved: () => void
}

function decisionLabel(value: HumanDecisionState) {
  if (value === 'CONFIRMED') return '已确认风险'
  if (value === 'ACCEPTED_RISK') return '已接受风险'
  if (value === 'FALSE_POSITIVE' || value === 'REJECTED') return '误报'
  if (value === 'MODIFIED') return '已修改'
  if (value === 'NEEDS_LAWYER_REVIEW' || value === 'NEEDS_MORE_REVIEW') return '需律师复核'
  return '待处理'
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
      setMessage('报告生成后才能记录处理决策。')
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
          throw new Error('处理决策记录无法读取。')
        }
        if (!cancelled) {
          setView(body as IssueHumanReviewView)
          setMessage('处理决策只记录业务处理状态，不会自动触发 AI 重审。')
        }
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : '无法读取处理决策记录。')
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
    setMessage('正在保存处理决策…')
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
        throw new Error('保存后未返回处理决策视图。')
      }
      setView(body as IssueHumanReviewView)
      setMessage('处理决策已保存。')
      onSaved()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '处理决策保存失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="human-decision-panel issue-human-decision-panel">
      <div className="report-kicker">处理决策</div>
      <div className="human-target-heading">
        <strong>{detail.plan_issue.topic}</strong>
      </div>

      {detail.comparison?.requires_human_review ? (
        <p className="issue-human-required">该风险需要形成处理决策。</p>
      ) : (
        <p className="human-panel-message">该风险可直接记录业务处理状态；不会自动触发 AI 重审。</p>
      )}

      {latest && (
        <div className={`latest-decision ${latest.is_stale ? 'is-stale' : ''}`}>
          <span>当前处理状态</span>
          <strong>{decisionLabel(latest.state)}</strong>
          <small>{new Date(latest.decided_at).toLocaleString()}</small>
          {latest.is_stale && <em>报告已更新，请重新确认该处理状态</em>}
        </div>
      )}

      <form onSubmit={submit}>
        <div className="decision-options" role="group" aria-label="处理决策状态">
          {(['UNREVIEWED', 'CONFIRMED', 'ACCEPTED_RISK', 'FALSE_POSITIVE', 'MODIFIED', 'NEEDS_LAWYER_REVIEW'] as HumanDecisionState[]).map((value) => (
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
        <label htmlFor={`issue-human-review-note-${detail.issue_id}`}>处理备注</label>
        <textarea
          id={`issue-human-review-note-${detail.issue_id}`}
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="说明已修改、接受风险、判断为误报，或需要律师复核的原因。"
          rows={4}
          maxLength={4000}
        />
        <button className="save-human-decision" type="submit" disabled={busy || !reportAvailable}>
          {busy ? '保存中…' : '保存处理决策'}
        </button>
      </form>

      <p className="human-panel-message">{message}</p>

      {history.length > 0 && (
        <div className="human-history">
          <div className="report-kicker">处理记录</div>
          {history.map((item) => (
            <article key={item.decision_id} className={item.is_stale ? 'is-stale' : ''}>
              <div>
                <strong>{decisionLabel(item.state)}</strong>
                <span>{new Date(item.decided_at).toLocaleString()}</span>
              </div>
              {item.reviewer_note && <p>{item.reviewer_note}</p>}
              {item.is_stale && <em>基于旧报告</em>}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
