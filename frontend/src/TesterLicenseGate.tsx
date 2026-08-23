import { ChangeEvent, ReactNode, useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

type LicenseState =
  | 'NOT_REQUIRED'
  | 'MISSING'
  | 'ACTIVE'
  | 'EXPIRED'
  | 'NOT_YET_VALID'
  | 'WRONG_RELEASE'
  | 'INVALID'

type LicenseStatus = {
  required: boolean
  state: LicenseState
  active: boolean
  tester_id: string | null
  license_id: string | null
  release_label: string | null
  not_before_utc: string | null
  expires_at_utc: string | null
  detail: string
}

type Props = {
  children: ReactNode
}

function formatExpiry(value: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export default function TesterLicenseGate({ children }: Props) {
  const [status, setStatus] = useState<LicenseStatus | null>(null)
  const [token, setToken] = useState('')
  const [loading, setLoading] = useState(true)
  const [activating, setActivating] = useState(false)
  const [message, setMessage] = useState('')

  const loadStatus = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE_URL}/api/tester-license/status`, { cache: 'no-store' })
      const body = await response.json().catch(() => null)
      if (!response.ok || !body) throw new Error(`许可证状态读取失败（HTTP ${response.status}）`)
      setStatus(body as LicenseStatus)
      setMessage('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '无法读取测试许可证状态。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadStatus()
  }, [])

  const loadLicenseFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      setToken((await file.text()).trim())
      setMessage(`已读取 ${file.name}，点击“激活测试许可”完成本机验证。`)
    } catch {
      setMessage('许可证文件无法读取。')
    }
  }

  const activate = async () => {
    const candidate = token.trim()
    if (!candidate || activating) return
    setActivating(true)
    setMessage('正在本机验证签名、版本和有效期…')
    try {
      const response = await fetch(`${API_BASE_URL}/api/tester-license/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: candidate }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `激活失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      setStatus(body as LicenseStatus)
      setToken('')
      setMessage('测试许可证已激活。')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '测试许可证激活失败。')
    } finally {
      setActivating(false)
    }
  }

  if (loading && !status) {
    return (
      <main className="tester-license-shell">
        <section className="tester-license-card">
          <div className="tester-license-kicker">LIMITED TEST BUILD</div>
          <h1>Law-Rag</h1>
          <p>正在检查本机测试许可证…</p>
        </section>
      </main>
    )
  }

  if (status && (!status.required || status.active)) {
    return (
      <>
        {children}
        {status.required && status.tester_id ? (
          <div className="tester-license-watermark" aria-label="测试人员标识">
            <strong>Law-Rag {status.release_label}</strong>
            <span>Tester {status.tester_id} · Limited Test Build</span>
          </div>
        ) : null}
      </>
    )
  }

  return (
    <main className="tester-license-shell">
      <section className="tester-license-card">
        <div className="tester-license-kicker">INVITED TESTERS ONLY</div>
        <h1>激活 Law-Rag 测试许可</h1>
        <p className="tester-license-lead">
          这个测试包需要一份由项目方签发的离线许可证。验证只在本机进行，不会为了激活许可证访问网络。
        </p>

        <div className="tester-license-state" data-state={status?.state ?? 'UNKNOWN'}>
          <strong>{status?.state ?? 'STATUS UNAVAILABLE'}</strong>
          <span>{status?.detail ?? (message || '无法读取许可证状态。')}</span>
          {status?.expires_at_utc ? <span>当前许可证到期：{formatExpiry(status.expires_at_utc)}</span> : null}
        </div>

        <label className="tester-license-file">
          <span>从许可证文件读取</span>
          <input type="file" accept=".txt,.license" onChange={(event) => void loadLicenseFile(event)} />
        </label>

        <label className="tester-license-token">
          <span>或粘贴许可证内容</span>
          <textarea
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="LR1.…"
            rows={5}
            spellCheck={false}
            autoComplete="off"
          />
        </label>

        <button type="button" className="tester-license-activate" disabled={!token.trim() || activating} onClick={() => void activate()}>
          {activating ? '验证中…' : '激活测试许可'}
        </button>

        {message ? <p className="tester-license-message">{message}</p> : null}
        <p className="tester-license-footnote">
          许可证与 Tester ID、测试版本和到期时间绑定。测试版界面与导出报告会显示 Tester ID；请勿转发自己的许可证。
        </p>
      </section>
    </main>
  )
}
