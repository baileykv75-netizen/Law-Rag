import { ChangeEvent, ReactNode, useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'
const SESSION_CACHE_KEY = 'law-rag-tester-license-status-v1'
const STATUS_TIMEOUT_MS = 4000

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

function readCachedActiveStatus(): LicenseStatus | null {
  try {
    const raw = window.sessionStorage.getItem(SESSION_CACHE_KEY)
    if (!raw) return null
    const candidate = JSON.parse(raw) as LicenseStatus
    if (!candidate.active) return null
    if (candidate.expires_at_utc) {
      const expiresAt = new Date(candidate.expires_at_utc).getTime()
      if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
        window.sessionStorage.removeItem(SESSION_CACHE_KEY)
        return null
      }
    }
    return candidate
  } catch {
    window.sessionStorage.removeItem(SESSION_CACHE_KEY)
    return null
  }
}

function cacheStatus(status: LicenseStatus) {
  try {
    if (status.active) {
      window.sessionStorage.setItem(SESSION_CACHE_KEY, JSON.stringify(status))
    } else {
      window.sessionStorage.removeItem(SESSION_CACHE_KEY)
    }
  } catch {
    // Session storage is only a UX optimization. Backend enforcement remains authoritative.
  }
}

export default function TesterLicenseGate({ children }: Props) {
  const [status, setStatus] = useState<LicenseStatus | null>(() => readCachedActiveStatus())
  const [token, setToken] = useState('')
  const [loading, setLoading] = useState(() => readCachedActiveStatus() === null)
  const [activating, setActivating] = useState(false)
  const [message, setMessage] = useState('')

  const loadStatus = async ({ blocking = false }: { blocking?: boolean } = {}) => {
    if (blocking) setLoading(true)
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), STATUS_TIMEOUT_MS)
    try {
      const response = await fetch(`${API_BASE_URL}/api/tester-license/status`, {
        cache: 'no-store',
        signal: controller.signal,
      })
      const body = await response.json().catch(() => null)
      if (!response.ok || !body) throw new Error(`许可证状态读取失败（HTTP ${response.status}）`)
      const nextStatus = body as LicenseStatus
      setStatus(nextStatus)
      cacheStatus(nextStatus)
      setMessage('')
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        setMessage('本机 Law-Rag 服务响应超时。请确认程序仍在运行，然后重试。')
      } else {
        setMessage(error instanceof Error ? error.message : '无法读取测试许可证状态。')
      }
    } finally {
      window.clearTimeout(timeout)
      if (blocking) setLoading(false)
    }
  }

  useEffect(() => {
    const cached = readCachedActiveStatus()
    if (cached) {
      // Do not block ordinary in-app page changes. The backend middleware still
      // enforces the current signed license on every protected API request.
      void loadStatus({ blocking: false })
      return
    }
    void loadStatus({ blocking: true })
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
      const nextStatus = body as LicenseStatus
      setStatus(nextStatus)
      cacheStatus(nextStatus)
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
          <p>首次启动正在检查本机测试许可证…</p>
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

        {!status && !loading ? (
          <button type="button" className="tester-license-activate" onClick={() => void loadStatus({ blocking: true })}>
            重新检查本机服务
          </button>
        ) : null}

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
          首次验证成功后，本次浏览器会话中的页面切换不再被许可证检查页阻塞；后台仍会静默复核，受保护 API 继续由后端强制校验。许可证与 Tester ID、测试版本和到期时间绑定。
        </p>
      </section>
    </main>
  )
}
