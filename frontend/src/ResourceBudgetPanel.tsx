import { useEffect, useState } from 'react'

import { API_BASE_URL } from './apiBase'

type ResourceBudgetState =
  | 'UNLIMITED'
  | 'WITHIN_BUDGET'
  | 'EXHAUSTED'
  | 'USAGE_UNKNOWN_BLOCKED'
  | 'COST_UNKNOWN_BLOCKED'

type ProviderPrice = {
  prompt_per_million: number
  completion_per_million: number
}

type ResourceBudgetPolicy = {
  max_provider_calls: number | null
  max_total_tokens: number | null
  max_estimated_cost: number | null
  currency: string | null
  provider_prices: Record<string, ProviderPrice>
}

type ResourceBudgetOverview = {
  job_id: string
  state: ResourceBudgetState
  policy: ResourceBudgetPolicy
  provider_calls_used: number
  completed_calls: number
  failed_calls: number
  in_flight_calls: number
  returned_pending_calls: number
  prompt_tokens_known: number
  completion_tokens_known: number
  total_tokens_known: number
  unknown_usage_calls: number
  estimated_cost: number | null
  estimated_cost_unknown_calls: number
  currency: string | null
  call_budget_remaining: number | null
  token_budget_remaining: number | null
  estimated_cost_remaining: number | null
  warnings: string[]
}

type Props = {
  jobId: string
}

type Draft = {
  maxCalls: string
  maxTokens: string
  maxCost: string
  currency: string
  deepseekPrompt: string
  deepseekCompletion: string
  kimiPrompt: string
  kimiCompletion: string
}

function emptyDraft(): Draft {
  return {
    maxCalls: '',
    maxTokens: '',
    maxCost: '',
    currency: '',
    deepseekPrompt: '',
    deepseekCompletion: '',
    kimiPrompt: '',
    kimiCompletion: '',
  }
}

function policyDraft(policy: ResourceBudgetPolicy): Draft {
  const deepseek = policy.provider_prices.deepseek
  const kimi = policy.provider_prices.kimi
  return {
    maxCalls: policy.max_provider_calls?.toString() ?? '',
    maxTokens: policy.max_total_tokens?.toString() ?? '',
    maxCost: policy.max_estimated_cost?.toString() ?? '',
    currency: policy.currency ?? '',
    deepseekPrompt: deepseek?.prompt_per_million?.toString() ?? '',
    deepseekCompletion: deepseek?.completion_per_million?.toString() ?? '',
    kimiPrompt: kimi?.prompt_per_million?.toString() ?? '',
    kimiCompletion: kimi?.completion_per_million?.toString() ?? '',
  }
}

function stateLabel(state: ResourceBudgetState) {
  if (state === 'UNLIMITED') return '未设置限制'
  if (state === 'WITHIN_BUDGET') return '预算内'
  if (state === 'EXHAUSTED') return '预算已耗尽'
  if (state === 'USAGE_UNKNOWN_BLOCKED') return 'Token 用量未知 · 已阻断后续调用'
  return '成本无法确认 · 已阻断后续调用'
}

function stateClass(state: ResourceBudgetState) {
  if (state === 'UNLIMITED') return 'is-unlimited'
  if (state === 'WITHIN_BUDGET') return 'is-safe'
  return 'is-blocked'
}

function integerOrNull(value: string, label: string): number | null {
  if (!value.trim()) return null
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed < 1) throw new Error(`${label}必须是大于 0 的整数。`)
  return parsed
}

function positiveOrNull(value: string, label: string): number | null {
  if (!value.trim()) return null
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`${label}必须大于 0。`)
  return parsed
}

function pricePair(prompt: string, completion: string, provider: string): ProviderPrice | null {
  const promptBlank = !prompt.trim()
  const completionBlank = !completion.trim()
  if (promptBlank && completionBlank) return null
  if (promptBlank || completionBlank) throw new Error(`${provider} 的输入/输出单价必须同时填写。`)
  const promptValue = Number(prompt)
  const completionValue = Number(completion)
  if (!Number.isFinite(promptValue) || promptValue < 0 || !Number.isFinite(completionValue) || completionValue < 0) {
    throw new Error(`${provider} 单价必须是大于等于 0 的数字。`)
  }
  return { prompt_per_million: promptValue, completion_per_million: completionValue }
}

function formatCount(value: number | null) {
  return value === null ? '不限' : value.toLocaleString()
}

function formatCost(value: number | null, currency: string | null) {
  if (value === null) return '未估算'
  return `${value.toFixed(6)} ${currency ?? ''}`.trim()
}

export default function ResourceBudgetPanel({ jobId }: Props) {
  const [overview, setOverview] = useState<ResourceBudgetOverview | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('正在读取本地模型资源账本…')
  const [editing, setEditing] = useState(false)

  const applyOverview = (value: ResourceBudgetOverview) => {
    setOverview(value)
    setDraft(policyDraft(value.policy))
  }

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/resource-budget`)
        const body = await response.json().catch(() => null)
        if (!response.ok) throw new Error(body?.detail ?? `HTTP ${response.status}`)
        if (!cancelled) {
          applyOverview(body as ResourceBudgetOverview)
          setMessage('仅读取本地账本；未触发模型调用。')
        }
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? error.message : '资源账本读取失败。')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => { cancelled = true }
  }, [jobId])

  const save = async () => {
    setSaving(true)
    try {
      const maxCalls = integerOrNull(draft.maxCalls, '调用次数上限')
      const maxTokens = integerOrNull(draft.maxTokens, 'Token 上限')
      const maxCost = positiveOrNull(draft.maxCost, '估算成本上限')
      const deepseek = pricePair(draft.deepseekPrompt, draft.deepseekCompletion, 'DeepSeek')
      const kimi = pricePair(draft.kimiPrompt, draft.kimiCompletion, 'Kimi')
      const providerPrices: Record<string, ProviderPrice> = {}
      if (deepseek) providerPrices.deepseek = deepseek
      if (kimi) providerPrices.kimi = kimi
      const currency = draft.currency.trim().toUpperCase() || null
      if (maxCost !== null && !currency) throw new Error('启用估算成本上限时必须填写币种。')
      if (maxCost !== null && Object.keys(providerPrices).length === 0) {
        throw new Error('启用估算成本上限时至少填写一个 Provider 的用户估算单价。')
      }

      const response = await fetch(`${API_BASE_URL}/api/documents/${encodeURIComponent(jobId)}/resource-budget`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          policy: {
            max_provider_calls: maxCalls,
            max_total_tokens: maxTokens,
            max_estimated_cost: maxCost,
            currency,
            provider_prices: providerPrices,
          },
        }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) throw new Error(body?.detail ?? `HTTP ${response.status}`)
      applyOverview(body as ResourceBudgetOverview)
      setMessage('预算策略已保存在当前 Job；保存动作没有调用外部模型。')
      setEditing(false)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '预算策略保存失败。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="resource-budget-panel" aria-label="模型资源与成本控制">
      <div className="resource-budget-heading">
        <div>
          <span className="eyebrow">MODEL RESOURCE BUDGET</span>
          <h3>模型资源与成本</h3>
        </div>
        {overview && <strong className={`resource-budget-state ${stateClass(overview.state)}`}>{stateLabel(overview.state)}</strong>}
      </div>

      {loading && !overview ? (
        <p className="resource-budget-message">{message}</p>
      ) : overview ? (
        <>
          <div className="resource-budget-metrics">
            <div><span>Provider 调用</span><strong>{overview.provider_calls_used}</strong><small>剩余 {formatCount(overview.call_budget_remaining)}</small></div>
            <div><span>已知 Token</span><strong>{overview.total_tokens_known.toLocaleString()}</strong><small>剩余 {formatCount(overview.token_budget_remaining)}</small></div>
            <div><span>估算成本</span><strong>{formatCost(overview.estimated_cost, overview.currency)}</strong><small>剩余 {formatCost(overview.estimated_cost_remaining, overview.currency)}</small></div>
            <div className={overview.unknown_usage_calls > 0 ? 'needs-attention' : ''}><span>未知 Usage</span><strong>{overview.unknown_usage_calls}</strong><small>in-flight {overview.in_flight_calls} · pending {overview.returned_pending_calls}</small></div>
          </div>

          <div className="resource-budget-actions">
            <button type="button" onClick={() => setEditing((value) => !value)}>{editing ? '收起设置' : '设置当前 Job 预算'}</button>
            <span>{message}</span>
          </div>

          {editing && (
            <div className="resource-budget-editor">
              <label>Provider 调用次数上限<input inputMode="numeric" value={draft.maxCalls} onChange={(event) => setDraft({ ...draft, maxCalls: event.target.value })} placeholder="留空 = 不限" /></label>
              <label>总 Token continuation limit<input inputMode="numeric" value={draft.maxTokens} onChange={(event) => setDraft({ ...draft, maxTokens: event.target.value })} placeholder="留空 = 不限" /></label>
              <label>估算成本上限<input inputMode="decimal" value={draft.maxCost} onChange={(event) => setDraft({ ...draft, maxCost: event.target.value })} placeholder="留空 = 不限" /></label>
              <label>币种<input value={draft.currency} onChange={(event) => setDraft({ ...draft, currency: event.target.value })} placeholder="例如 CNY / USD" maxLength={12} /></label>

              <div className="resource-budget-price-group">
                <strong>DeepSeek 用户估算单价 / 每百万 Token</strong>
                <label>输入<input inputMode="decimal" value={draft.deepseekPrompt} onChange={(event) => setDraft({ ...draft, deepseekPrompt: event.target.value })} /></label>
                <label>输出<input inputMode="decimal" value={draft.deepseekCompletion} onChange={(event) => setDraft({ ...draft, deepseekCompletion: event.target.value })} /></label>
              </div>
              <div className="resource-budget-price-group">
                <strong>Kimi 用户估算单价 / 每百万 Token</strong>
                <label>输入<input inputMode="decimal" value={draft.kimiPrompt} onChange={(event) => setDraft({ ...draft, kimiPrompt: event.target.value })} /></label>
                <label>输出<input inputMode="decimal" value={draft.kimiCompletion} onChange={(event) => setDraft({ ...draft, kimiCompletion: event.target.value })} /></label>
              </div>

              <div className="resource-budget-truth-note">
                调用次数是请求发出前的硬上限。Token 与成本只能依据 Provider 实际返回的 usage 约束“后续调用”；单个已经发出的请求可能超过剩余额度。价格表完全由你填写，不代表模型厂商实时价格或最终账单。
              </div>
              <div className="resource-budget-editor-actions">
                <button type="button" disabled={saving} onClick={() => void save()}>{saving ? '保存中…' : '保存预算策略'}</button>
                <button type="button" className="secondary" disabled={saving} onClick={() => { setDraft(policyDraft(overview.policy)); setEditing(false) }}>取消</button>
              </div>
            </div>
          )}

          {overview.warnings.length > 0 && (
            <details className="resource-budget-warnings">
              <summary>预算语义与警告</summary>
              <ul>{overview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
            </details>
          )}
        </>
      ) : (
        <p className="resource-budget-message is-error">{message}</p>
      )}
    </section>
  )
}
