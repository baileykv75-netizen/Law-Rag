import { FormEvent, useEffect, useMemo, useState } from 'react'
import type { SelectedAuditItem } from './workstation-review-types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type DecisionState = 'UNREVIEWED' | 'CONFIRMED' | 'REJECTED' | 'NEEDS_MORE_REVIEW'

type DecisionRevision = {
  schema_version: string
  decision_id: string
  revision: number
  job_id: string
  target_type: 'finding' | 'omission'
  target_id: string
  state: DecisionState
  reviewer_note: string
  decided_at: string
  contract_evidence_ids: string[]
  legal_evidence_ids: string[]
  review_report_fingerprint: string
  is_stale: boolean
}

type HumanReviewView = {
  schema_version: string
  job_id: string
  current_review_report_fingerprint: string
  revisions: DecisionRevision[]
  latest_by_target: Record<string, DecisionRevision>
}

type Props = {
  jobId: string
  reportAvailable: boolean
  selectedItem: SelectedAuditItem | null
}

function decisionLabel(value: DecisionState) {
  if (value === 'CONFIRMED') return '确认'
  if (value === 'REJECTED') return '驳回'
  if (value === 'NEEDS_MORE_REVIEW') return '继续复核'
  return '未审阅'
}

function targetKey(item: SelectedAuditItem) {
  return `${item.itemType}:${item.itemId}`
}

export default function HumanDecisionPanel({ jobId, reportAvailable, selectedItem }: Props) {
  const [view, setView] = useState<HumanReviewView | null>(null)
  const [state, setState] = useState<DecisionState>('UNREVIEWED')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    setView(null)
    if (!reportAvailable) {
      setMessage('需要有效 review-report.json 后才能记录人工决定。')
      return
    }
    let cancelled = false
    const load = async () => {
      setMessage('正在读取本机人工复核记录…')
      try {
        const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/human-review`)
        const body = await response.json().catch(() => null)
        if (!response.ok) {
          const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
          throw new Error(detail)
        }
        if (!cancelled) {
          setView(body as HumanReviewView)
          setMessage('人工决定只保存在本机 human-review.json。')
        }
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : '无法读取人工复核记录。')
      }
    }
    void load()
    return () => { cancelled = true }
  }, [jobId, reportAvailable])

  const latest = useMemo(() => {
    if (!view || !selectedItem) return null
    return view.latest_by_target[targetKey(selectedItem)] ?? null
  }, [selectedItem, view])

  const history = useMemo(() => {
    if (!view || !selectedItem) return []
    return view.revisions
      .filter((item) => item.target_type === selectedItem.itemType && item.target_id === selectedItem.itemId)
      .sort((a, b) => b.revision - a.revision)
  }, [selectedItem, view])

  useEffect(() => {
    if (latest) {
      setState(latest.state)
      setNote(latest.reviewer_note)
    } else {
      setState('UNREVIEWED')
      setNote('')
    }
  }, [latest, selectedItem?.itemId])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedItem || busy || !reportAvailable) return
    setBusy(true)
    setMessage('正在追加人工复核 revision…')
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/human-review/decisions`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_type: selectedItem.itemType,
            target_id: selectedItem.itemId,
            state,
            reviewer_note: note,
          }),
        },
      )
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`
        throw new Error(detail)
      }
      setView(body as HumanReviewView)
      setMessage('已追加新的本机人工复核 revision；旧记录保持不变。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '人工决定保存失败。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="human-decision-panel">
      <div className="context-eyebrow">HUMAN REVIEW</div>
      {!selectedItem ? (
        <p className="human-panel-message">先在中栏选择一个 finding 或可能漏审项。</p>
      ) : (
        <>
          <div className="human-target-heading">
            <strong>{selectedItem.title}</strong>
            <span>{selectedItem.itemType} · {selectedItem.itemId}</span>
          </div>

          {latest && (
            <div className={`latest-decision ${latest.is_stale ? 'is-stale' : ''}`}>
              <span>当前最新记录</span>
              <strong>{decisionLabel(latest.state)} · revision {latest.revision}</strong>
              <small>{new Date(latest.decided_at).toLocaleString()}</small>
              {latest.is_stale && <em>STALE · review-report 已变化，请重新确认</em>}
            </div>
          )}

          <form onSubmit={submit}>
            <div className="decision-options" role="group" aria-label="人工决定状态">
              {(['CONFIRMED', 'REJECTED', 'NEEDS_MORE_REVIEW', 'UNREVIEWED'] as DecisionState[]).map((value) => (
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
            <label htmlFor="human-review-note">复核备注</label>
            <textarea
              id="human-review-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="记录为什么确认/驳回，或者还需要核查什么。"
              rows={4}
              maxLength={4000}
            />
            <button className="save-human-decision" type="submit" disabled={busy || !reportAvailable}>
              {busy ? '保存中…' : '追加人工决定 revision'}
            </button>
          </form>

          <p className="human-panel-message">{message}</p>

          {history.length > 0 && (
            <div className="human-history">
              <div className="context-eyebrow">REVISION HISTORY</div>
              {history.map((item) => (
                <article key={item.decision_id} className={item.is_stale ? 'is-stale' : ''}>
                  <div>
                    <strong>r{item.revision} · {decisionLabel(item.state)}</strong>
                    <span>{new Date(item.decided_at).toLocaleString()}</span>
                  </div>
                  {item.reviewer_note && <p>{item.reviewer_note}</p>}
                  <small>合同 Evidence {item.contract_evidence_ids.length} · Legal Evidence {item.legal_evidence_ids.length}</small>
                  {item.is_stale && <em>基于旧 review-report</em>}
                </article>
              ))}
            </div>
          )}
        </>
      )}
      {!selectedItem && <p className="human-panel-message">{message}</p>}
    </section>
  )
}
