import { ReactNode, useEffect, useMemo, useState } from 'react'
import { API_BASE_URL } from './apiBase'
import { LOCAL_ROUTE_CHANGE_EVENT } from './localRouting'

type ProviderName = 'deepseek' | 'kimi'

type ProviderItem = {
  provider: ProviderName
  configured: boolean
  source: string | null
  model: string
  base_url: string
  runtime_source: string
}

type ProviderOverview = {
  setup_completed: boolean
  requires_setup: boolean
  secure_storage_available: boolean
  providers: ProviderItem[]
}

type ProbeResult = {
  provider: ProviderName
  success: boolean
  detail: string
}

type ProviderSetupGateProps = {
  children: ReactNode
}

function sourceLabel(source: string | null) {
  if (source === 'windows_credential_manager') return '已保存'
  if (source === 'environment') return '环境变量'
  return ''
}

function providerLabel(provider: ProviderName) {
  return provider === 'deepseek' ? '主审模型' : '争议复审模型'
}

export default function ProviderSetupGate({ children }: ProviderSetupGateProps) {
  const [overview, setOverview] = useState<ProviderOverview | null>(null)
  const [open, setOpen] = useState(false)
  const [deepseekKey, setDeepseekKey] = useState('')
  const [kimiKey, setKimiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [probe, setProbe] = useState<Partial<Record<ProviderName, ProbeResult>>>({})

  const load = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/providers`)
      if (!response.ok) throw new Error(`无法读取 API 配置（HTTP ${response.status}）。`)
      const next = (await response.json()) as ProviderOverview
      setOverview(next)
      if (next.requires_setup) setOpen(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法读取 API 配置。')
    }
  }

  useEffect(() => {
    void load()
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('settings') === '1') setOpen(true)
    const sync = () => {
      const params = new URLSearchParams(window.location.search)
      if (params.get('settings') === '1') setOpen(true)
    }
    window.addEventListener('popstate', sync)
    window.addEventListener(LOCAL_ROUTE_CHANGE_EVENT, sync)
    return () => {
      window.removeEventListener('popstate', sync)
      window.removeEventListener(LOCAL_ROUTE_CHANGE_EVENT, sync)
    }
  }, [])

  const byProvider = useMemo(() => {
    const map = new Map<ProviderName, ProviderItem>()
    overview?.providers.forEach((item) => map.set(item.provider, item))
    return map
  }, [overview])

  const testConnection = async (provider: ProviderName) => {
    const apiKey = provider === 'deepseek' ? deepseekKey : kimiKey
    setProbe((current) => ({ ...current, [provider]: undefined }))
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/providers/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, api_key: apiKey.trim() || null }),
      })
      if (!response.ok) throw new Error(`测试连接失败（HTTP ${response.status}）。`)
      const result = (await response.json()) as ProbeResult
      setProbe((current) => ({ ...current, [provider]: result }))
    } catch (err) {
      setError(err instanceof Error ? err.message : '测试连接失败。')
    }
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/providers`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          deepseek_api_key: deepseekKey.trim() || null,
          kimi_api_key: kimiKey.trim() || null,
          complete_setup: true,
        }),
      })
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string }
        throw new Error(payload.detail ?? `保存失败（HTTP ${response.status}）。`)
      }
      const next = (await response.json()) as ProviderOverview
      setOverview(next)
      setDeepseekKey('')
      setKimiKey('')
      setProbe({})
      close()
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法保存 API 配置。')
    } finally {
      setBusy(false)
    }
  }

  const close = () => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('settings') === '1') {
      window.history.replaceState({}, '', window.location.pathname)
    }
    setOpen(false)
  }

  const skip = async () => {
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/providers/skip`, { method: 'POST' })
      if (!response.ok) throw new Error(`暂时跳过失败（HTTP ${response.status}）。`)
      setOverview((await response.json()) as ProviderOverview)
      close()
    } catch (err) {
      setError(err instanceof Error ? err.message : '暂时无法跳过配置。')
      close()
    } finally {
      setBusy(false)
    }
  }

  const remove = async (provider: ProviderName) => {
    setBusy(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE_URL}/api/config/providers/${provider}`, { method: 'DELETE' })
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string }
        throw new Error(payload.detail ?? `移除失败（HTTP ${response.status}）。`)
      }
      setOverview((await response.json()) as ProviderOverview)
      setProbe((current) => ({ ...current, [provider]: undefined }))
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法移除保存的 API Key。')
    } finally {
      setBusy(false)
    }
  }

  const providerBlock = (provider: ProviderName, value: string, setValue: (value: string) => void) => {
    const item = byProvider.get(provider)
    const result = probe[provider]
    const removable = item?.configured && item.source === 'windows_credential_manager'
    return (
      <section className="provider-setup-provider">
        <div className="provider-setup-provider-head">
          <div>
            <strong>{providerLabel(provider)}</strong>
            {item && <span>{item.configured ? '已配置' : '未配置'}</span>}
          </div>
          <div className={`provider-config-chip ${item?.configured ? 'is-ready' : ''}`}>
            {item?.configured ? sourceLabel(item.source) || '已配置' : '未配置'}
          </div>
        </div>
        <label>
          API Key
          <input
            type="password"
            autoComplete="off"
            value={value}
            placeholder={item?.configured ? '留空则保持不变' : '粘贴 API Key'}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
        <div className="provider-setup-actions">
          <button type="button" className="secondary" onClick={() => void testConnection(provider)} disabled={busy}>
            测试当前 Endpoint
          </button>
          {removable && (
            <button type="button" className="quiet-danger" onClick={() => void remove(provider)} disabled={busy}>
              移除已保存 Key
            </button>
          )}
        </div>
        {result && (
          <p className={result.success ? 'provider-probe-ok' : 'provider-probe-error'}>{result.detail}</p>
        )}
      </section>
    )
  }

  return (
    <>
      {children}
      <button className="provider-settings-trigger" type="button" onClick={() => setOpen(true)}>
        API 设置
      </button>
      {open && (
        <div className="provider-setup-backdrop" role="presentation">
          <section className="provider-setup-modal" role="dialog" aria-modal="true" aria-labelledby="provider-setup-title">
            <div className="provider-setup-titlebar">
              <div>
                <p>API 设置</p>
                <h2 id="provider-setup-title">连接审计模型</h2>
              </div>
              <button className="provider-setup-close" type="button" onClick={close} aria-label="关闭 API 设置">
                ×
              </button>
            </div>
            <p className="provider-setup-intro">
              完整审查需要配置主审模型和争议复审模型。代码和安装包不内置任何 API Key。
            </p>
            {overview && !overview.secure_storage_available && (
              <div className="provider-setup-warning">
                当前平台暂不支持保存 API Key，可通过环境变量配置后重试。
              </div>
            )}
            {providerBlock('deepseek', deepseekKey, setDeepseekKey)}
            {providerBlock('kimi', kimiKey, setKimiKey)}

            <p className="provider-setup-cost-note">
              测试连接会产生极少量 API 用量；保存设置本身不会调用模型。
            </p>
            {error && <div className="provider-setup-error">{error}</div>}
            <div className="provider-setup-footer">
              <button type="button" className="provider-skip" onClick={() => void skip()} disabled={busy}>
                暂时跳过，仅使用本地功能
              </button>
              <button type="button" className="provider-save" onClick={() => void save()} disabled={busy || !overview?.secure_storage_available}>
                {busy ? '处理中…' : '保存 API Key 并继续'}
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  )
}
