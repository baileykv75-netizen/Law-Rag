import { useEffect, useMemo, useState } from 'react'

import { API_BASE_URL } from './apiBase'

type ProviderName = 'deepseek' | 'kimi'
type RuntimeSource = 'SAVED' | 'ENVIRONMENT' | 'DEFAULT'

type RuntimeProvider = {
  provider: ProviderName
  source: RuntimeSource
  model: string
  base_url: string
  request_timeout_seconds: number
  connect_timeout_seconds: number
  max_attempts: number
  retry_backoff_seconds: number
  supported_models: string[]
  custom_endpoint: boolean
}

type RuntimeOverview = {
  schema_version: string
  providers: RuntimeProvider[]
  custom_endpoint_warning: string
}

type DraftProvider = {
  model: string
  base_url: string
  request_timeout_seconds: string
  connect_timeout_seconds: string
  max_attempts: string
  retry_backoff_seconds: string
}

type Props = {
  onChanged?: () => void | Promise<void>
}

function label(provider: ProviderName) {
  return provider === 'deepseek' ? 'DeepSeek · 主审' : 'Kimi · 二审'
}

function sourceLabel(source: RuntimeSource) {
  if (source === 'SAVED') return '本地已保存'
  if (source === 'ENVIRONMENT') return '环境变量兼容配置'
  return '内置默认'
}

function draftFromProvider(provider: RuntimeProvider): DraftProvider {
  return {
    model: provider.model,
    base_url: provider.base_url,
    request_timeout_seconds: String(provider.request_timeout_seconds),
    connect_timeout_seconds: String(provider.connect_timeout_seconds),
    max_attempts: String(provider.max_attempts),
    retry_backoff_seconds: String(provider.retry_backoff_seconds),
  }
}

function numberValue(value: string, labelText: string): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) throw new Error(`${labelText}必须是数字。`)
  return parsed
}

export default function ProviderAdvancedSettings({ onChanged }: Props) {
  const [overview, setOverview] = useState<RuntimeOverview | null>(null)
  const [drafts, setDrafts] = useState<Partial<Record<ProviderName, DraftProvider>>>({})
  const [confirmCustom, setConfirmCustom] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('正在读取本地运行参数…')
  const [expanded, setExpanded] = useState(false)

  const load = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/providers/runtime`)
      const body = await response.json().catch(() => null)
      if (!response.ok) throw new Error(body?.detail ?? `读取高级设置失败（HTTP ${response.status}）。`)
      const next = body as RuntimeOverview
      setOverview(next)
      const nextDrafts: Partial<Record<ProviderName, DraftProvider>> = {}
      next.providers.forEach((provider) => { nextDrafts[provider.provider] = draftFromProvider(provider) })
      setDrafts(nextDrafts)
      setConfirmCustom(false)
      setMessage('仅读取本地非秘密配置；未触发模型调用。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '无法读取高级设置。')
    }
  }

  useEffect(() => { void load() }, [])

  const providerMap = useMemo(() => {
    const map = new Map<ProviderName, RuntimeProvider>()
    overview?.providers.forEach((provider) => map.set(provider.provider, provider))
    return map
  }, [overview])

  const patchDraft = (provider: ProviderName, patch: Partial<DraftProvider>) => {
    setDrafts((current) => ({
      ...current,
      [provider]: { ...(current[provider] as DraftProvider), ...patch },
    }))
  }

  const notifyChanged = async () => {
    if (onChanged) await onChanged()
  }

  const save = async () => {
    const deepseek = drafts.deepseek
    const kimi = drafts.kimi
    if (!deepseek || !kimi) return
    setBusy(true)
    try {
      const payloadFor = (draft: DraftProvider) => ({
        model: draft.model,
        base_url: draft.base_url.trim(),
        request_timeout_seconds: numberValue(draft.request_timeout_seconds, '请求超时'),
        connect_timeout_seconds: numberValue(draft.connect_timeout_seconds, '连接超时'),
        max_attempts: numberValue(draft.max_attempts, 'HTTP 尝试次数'),
        retry_backoff_seconds: numberValue(draft.retry_backoff_seconds, '重试等待'),
      })
      const response = await fetch(`${API_BASE_URL}/api/config/providers/runtime`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deepseek: payloadFor(deepseek),
          kimi: payloadFor(kimi),
          confirm_custom_endpoints: confirmCustom,
        }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) throw new Error(body?.detail ?? `保存高级设置失败（HTTP ${response.status}）。`)
      const next = body as RuntimeOverview
      setOverview(next)
      const nextDrafts: Partial<Record<ProviderName, DraftProvider>> = {}
      next.providers.forEach((provider) => { nextDrafts[provider.provider] = draftFromProvider(provider) })
      setDrafts(nextDrafts)
      setConfirmCustom(false)
      await notifyChanged()
      setMessage('运行参数已保存到本地；上方 Provider 地址已同步刷新。保存动作未测试连接，也未调用模型。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '无法保存高级设置。')
    } finally {
      setBusy(false)
    }
  }

  const reset = async () => {
    setBusy(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/providers/runtime`, { method: 'DELETE' })
      const body = await response.json().catch(() => null)
      if (!response.ok) throw new Error(body?.detail ?? `恢复默认失败（HTTP ${response.status}）。`)
      const next = body.overview as RuntimeOverview
      setOverview(next)
      const nextDrafts: Partial<Record<ProviderName, DraftProvider>> = {}
      next.providers.forEach((provider) => { nextDrafts[provider.provider] = draftFromProvider(provider) })
      setDrafts(nextDrafts)
      setConfirmCustom(false)
      await notifyChanged()
      setMessage('已移除本地运行参数覆盖；上方 Provider 地址已同步刷新。现在按环境变量兼容配置或内置默认值解析，未触发网络请求。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '无法恢复默认运行参数。')
    } finally {
      setBusy(false)
    }
  }

  const providerEditor = (provider: ProviderName) => {
    const resolved = providerMap.get(provider)
    const draft = drafts[provider]
    if (!resolved || !draft) return null
    return (
      <section className="provider-runtime-provider" key={provider}>
        <div className="provider-runtime-provider-head">
          <div><strong>{label(provider)}</strong><span>{sourceLabel(resolved.source)}</span></div>
          <span className={resolved.custom_endpoint ? 'provider-runtime-custom' : 'provider-runtime-official'}>
            {resolved.custom_endpoint ? '自定义 endpoint' : '默认 endpoint'}
          </span>
        </div>
        <div className="provider-runtime-grid">
          <label>
            模型
            <select value={draft.model} onChange={(event) => patchDraft(provider, { model: event.target.value })}>
              {resolved.supported_models.map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
          </label>
          <label className="provider-runtime-url">
            API 根地址
            <input value={draft.base_url} onChange={(event) => patchDraft(provider, { base_url: event.target.value })} />
          </label>
          <label>请求超时 / 秒<input inputMode="decimal" value={draft.request_timeout_seconds} onChange={(event) => patchDraft(provider, { request_timeout_seconds: event.target.value })} /></label>
          <label>连接超时 / 秒<input inputMode="decimal" value={draft.connect_timeout_seconds} onChange={(event) => patchDraft(provider, { connect_timeout_seconds: event.target.value })} /></label>
          <label>
            HTTP 尝试次数
            <select value={draft.max_attempts} onChange={(event) => patchDraft(provider, { max_attempts: event.target.value })}>
              <option value="1">1 · 不重试</option>
              <option value="2">2 · 最多重试 1 次</option>
              <option value="3">3 · 最多重试 2 次</option>
            </select>
          </label>
          <label>重试等待 / 秒<input inputMode="decimal" value={draft.retry_backoff_seconds} onChange={(event) => patchDraft(provider, { retry_backoff_seconds: event.target.value })} /></label>
        </div>
      </section>
    )
  }

  return (
    <section className="provider-advanced-settings">
      <button type="button" className="provider-advanced-toggle" onClick={() => setExpanded((value) => !value)}>
        <span><strong>高级运行参数</strong><small>模型、Endpoint、超时与瞬时重试 · 不含 API Key</small></span>
        <span>{expanded ? '收起' : '展开'}</span>
      </button>

      {expanded && (
        <div className="provider-advanced-body">
          <div className="provider-runtime-note">
            保存这些参数只写本地配置，不会测试连接或产生 API 用量。Prompt、证据范围、输出 JSON Schema 和最大输出 Token 安全上限不可在这里修改。
          </div>
          {overview ? (
            <>
              {providerEditor('deepseek')}
              {providerEditor('kimi')}
              <label className="provider-custom-confirm">
                <input type="checkbox" checked={confirmCustom} onChange={(event) => setConfirmCustom(event.target.checked)} />
                <span>如果我填写了自定义 Endpoint，我确认后续对应 Provider 的受限合同/法律证据会发送到该地址。</span>
              </label>
              <div className="provider-runtime-accounting-note">
                Stage 18.3 的“Provider 调用预算”按每个 Issue 的逻辑模型调用计数；这里的 HTTP 尝试次数只控制该逻辑调用内部遇到 429/5xx/网络异常时的瞬时重试，不会被伪装成多个逻辑调用预算单位。
              </div>
              <div className="provider-runtime-actions">
                <button type="button" className="provider-save" disabled={busy} onClick={() => void save()}>{busy ? '处理中…' : '保存高级设置'}</button>
                <button type="button" className="provider-skip" disabled={busy} onClick={() => void reset()}>恢复环境/默认参数</button>
              </div>
            </>
          ) : <p className="provider-runtime-message">{message}</p>}
          {overview && <p className="provider-runtime-message">{message}</p>}
        </div>
      )}
    </section>
  )
}
