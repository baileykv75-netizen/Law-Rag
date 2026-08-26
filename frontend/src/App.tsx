import { ChangeEvent, DragEvent, useRef, useState } from 'react'

import { API_BASE_URL } from './apiBase'
const ALLOWED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png']
const MAX_BYTES = 50 * 1024 * 1024
const DEFAULT_AUDIT_PROFILE = 'basic-bilateral-v1'

type PageRoute = 'NATIVE_TEXT_USABLE' | 'OCR_REQUIRED' | 'EMPTY_OR_UNSUPPORTED'
type DocumentRoute = 'NATIVE_TEXT' | 'OCR_REQUIRED' | 'MIXED'
type OcrPageState = 'NATIVE_RETAINED' | 'OCR_COMPLETE' | 'OCR_LOW_CONFIDENCE' | 'OCR_NO_TEXT' | 'OCR_FAILED'
type RuleState = 'PASS' | 'FAIL' | 'REVIEW' | 'NOT_APPLICABLE'

type PageSummary = {
  evidence_id: string
  page_number: number
  route: PageRoute
  character_count: number
  route_reason: string
}

type UploadResult = {
  job_id: string
  filename: string
  media_type: string
  size_bytes: number
  status: string
  storage_scope: string
  document_kind: 'pdf' | 'image'
  page_count: number
  route: DocumentRoute
  native_text_pages: number
  ocr_required_pages: number
  pages: PageSummary[]
}

type OcrPageResult = {
  page_number: number
  state: OcrPageState
  source_method: 'native_pdf_text' | 'image_source' | 'ocr'
  text: string
  low_confidence_blocks: number
  error: string | null
}

type OcrRunResult = {
  job_id: string
  provider: string
  model: string
  provider_version: string
  status: string
  page_count: number
  native_pages: number
  ocr_pages_attempted: number
  ocr_pages_complete: number
  low_confidence_pages: number
  failed_pages: number
  no_text_pages: number
  pages: OcrPageResult[]
}

type ClauseSummary = {
  clause_id: string
  heading_token: string
  heading_text: string
  body_text: string
  level: number
  parent_clause_id: string | null
  page_start: number
  page_end: number
}

type PartySummary = {
  mention_id: string
  role_label: string
  raw_name: string | null
  resolution_state: 'RESOLVED' | 'UNRESOLVED' | 'AMBIGUOUS'
}

type DateSummary = {
  mention_id: string
  raw_text: string
  iso_date: string | null
  field_label: string | null
  resolution_state: 'RESOLVED' | 'UNRESOLVED' | 'AMBIGUOUS'
}

type MoneySummary = {
  mention_id: string
  raw_text: string
  numeric_value: string | null
  currency: string | null
  unit: string | null
}

type PercentageSummary = {
  mention_id: string
  raw_text: string
  numeric_value: string | null
}

type IdentifierSummary = {
  mention_id: string
  label: string
  raw_value: string
}

type StructureSummary = {
  job_id: string
  schema_version: string
  status: string
  title: string | null
  clause_count: number
  party_count: number
  date_count: number
  money_count: number
  percentage_count: number
  identifier_count: number
  unresolved_reference_count: number
  warning_count: number
  clauses: ClauseSummary[]
  parties: PartySummary[]
  dates: DateSummary[]
  money_mentions: MoneySummary[]
  percentages: PercentageSummary[]
  identifiers: IdentifierSummary[]
}

type ObservedValue = {
  label: string
  value: string
  canonical_object_id: string | null
}

type AuditRuleResult = {
  result_id: string
  rule_id: string
  rule_version: string
  family: string
  title: string
  state: RuleState
  deterministic_state: RuleState
  severity: 'INFO' | 'WARNING' | 'ERROR' | null
  reason_code: string
  explanation: string
  canonical_object_ids: string[]
  evidence_ids: string[]
  observed_values: ObservedValue[]
  review_reasons: string[]
}

type AuditRuleReport = {
  schema_version: string
  engine_version: string
  job_id: string
  status: string
  contract_schema_version: string
  contract_source_fingerprint: string
  contract_content_fingerprint: string
  profile: {
    profile_id: string
    version: string
    title: string
  }
  counts: {
    total: number
    passed: number
    failed: number
    review: number
    not_applicable: number
  }
  results: AuditRuleResult[]
  engine_errors: Array<{ rule_id: string; error_type: string; message: string }>
}

type ViewState = 'idle' | 'ready' | 'uploading' | 'success' | 'error'
type OcrViewState = 'idle' | 'running' | 'success' | 'error'
type StructureViewState = 'idle' | 'running' | 'success' | 'error'
type AuditViewState = 'idle' | 'running' | 'success' | 'error'

function getExtension(name: string) {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot).toLowerCase() : ''
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function validateFile(file: File): string | null {
  if (!ALLOWED_EXTENSIONS.includes(getExtension(file.name))) return '暂仅支持 PDF、JPG、JPEG、PNG 文件。'
  if (file.size === 0) return '文件为空，请选择有效文件。'
  if (file.size > MAX_BYTES) return '文件超过当前 50 MiB 限制。'
  return null
}

function routeLabel(route: DocumentRoute | PageRoute) {
  if (route === 'NATIVE_TEXT' || route === 'NATIVE_TEXT_USABLE') return '原生文本可用'
  if (route === 'MIXED') return '混合路由'
  if (route === 'OCR_REQUIRED') return '需要 OCR'
  return '空白/不支持'
}

function ocrStateLabel(state: OcrPageState) {
  if (state === 'NATIVE_RETAINED') return '保留原生文本'
  if (state === 'OCR_COMPLETE') return 'OCR 完成'
  if (state === 'OCR_LOW_CONFIDENCE') return 'OCR 低置信度'
  if (state === 'OCR_NO_TEXT') return 'OCR 无文本'
  return 'OCR 失败'
}

function ruleStateLabel(state: RuleState) {
  if (state === 'PASS') return '通过'
  if (state === 'FAIL') return '规则不通过'
  if (state === 'REVIEW') return '需复核'
  return '不适用'
}

function App() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [state, setState] = useState<ViewState>('idle')
  const [message, setMessage] = useState('')
  const [result, setResult] = useState<UploadResult | null>(null)
  const [dragging, setDragging] = useState(false)
  const [ocrState, setOcrState] = useState<OcrViewState>('idle')
  const [ocrMessage, setOcrMessage] = useState('')
  const [ocrResult, setOcrResult] = useState<OcrRunResult | null>(null)
  const [structureState, setStructureState] = useState<StructureViewState>('idle')
  const [structureMessage, setStructureMessage] = useState('')
  const [structureResult, setStructureResult] = useState<StructureSummary | null>(null)
  const [auditState, setAuditState] = useState<AuditViewState>('idle')
  const [auditMessage, setAuditMessage] = useState('')
  const [auditResult, setAuditResult] = useState<AuditRuleReport | null>(null)

  const resetAudit = () => {
    setAuditState('idle')
    setAuditMessage('')
    setAuditResult(null)
  }

  const resetStructure = () => {
    setStructureState('idle')
    setStructureMessage('')
    setStructureResult(null)
    resetAudit()
  }

  const resetOcr = () => {
    setOcrState('idle')
    setOcrMessage('')
    setOcrResult(null)
    resetStructure()
  }

  const selectFile = (nextFile: File | null) => {
    setResult(null)
    resetOcr()
    if (!nextFile) {
      setFile(null)
      setState('idle')
      setMessage('')
      return
    }
    const error = validateFile(nextFile)
    if (error) {
      setFile(null)
      setState('error')
      setMessage(error)
      return
    }
    setFile(nextFile)
    setState('ready')
    setMessage('文件已准备好，可以进行本地文档检查。')
  }

  const handleInput = (event: ChangeEvent<HTMLInputElement>) => {
    selectFile(event.target.files?.[0] ?? null)
    event.target.value = ''
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    selectFile(event.dataTransfer.files?.[0] ?? null)
  }

  const upload = async () => {
    if (!file || state === 'uploading') return
    setState('uploading')
    setMessage('正在保存并检查文档…')
    setResult(null)
    resetOcr()
    try {
      const form = new FormData()
      form.append('file', file)
      const response = await fetch(`${API_BASE_URL}/api/documents`, { method: 'POST', body: form })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `处理失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      const inspection = body as UploadResult
      setResult(inspection)
      setState('success')
      if (inspection.route === 'NATIVE_TEXT') {
        setMessage('检查完成：原生文本可用，可直接生成确定性合同结构。')
      } else if (inspection.route === 'MIXED') {
        setMessage('检查完成：部分页面需要 OCR；完成 OCR 后才能生成完整合同结构。')
      } else {
        setMessage('检查完成：该文档需要 OCR；完成 OCR 后才能生成合同结构。')
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setState('error')
      setMessage(`处理失败：${detail}。请确认本地后端正在运行。`)
    }
  }

  const runOcr = async () => {
    if (!result || result.ocr_required_pages === 0 || ocrState === 'running') return
    setOcrState('running')
    setOcrMessage('正在本机执行 OCR；首次使用可能需要下载模型…')
    setOcrResult(null)
    resetStructure()
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${result.job_id}/ocr`, { method: 'POST' })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `OCR 失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      const next = body as OcrRunResult
      setOcrResult(next)
      setOcrState('success')
      if (next.failed_pages || next.no_text_pages) {
        setOcrMessage('OCR 已完成，但存在失败或无文本页面；系统不会在缺页状态下生成合同结构。')
      } else if (next.low_confidence_pages) {
        setOcrMessage('OCR 已完成，存在低置信度页；这些不确定性会继续传播到结构化和规则结果。')
      } else {
        setOcrMessage('OCR 已完成并保存页级证据，可以继续生成合同结构。')
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setOcrState('error')
      setOcrMessage(`OCR 无法运行：${detail}`)
    }
  }

  const canStructure = Boolean(
    result &&
      (result.ocr_required_pages === 0 ||
        (ocrResult && ocrResult.failed_pages === 0 && ocrResult.no_text_pages === 0)),
  )

  const runStructure = async () => {
    if (!result || !canStructure || structureState === 'running') return
    setStructureState('running')
    setStructureMessage('正在基于现有证据生成确定性合同结构…')
    setStructureResult(null)
    resetAudit()
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${result.job_id}/structure`, { method: 'POST' })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `结构化失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      const next = body as StructureSummary
      setStructureResult(next)
      setStructureState('success')
      setStructureMessage('合同结构已生成并保存在本机 contract.json。可以继续运行确定性审计规则。')
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setStructureState('error')
      setStructureMessage(`合同结构无法生成：${detail}`)
    }
  }

  const runAuditRules = async () => {
    if (!result || !structureResult || auditState === 'running') return
    setAuditState('running')
    setAuditMessage('正在对 contract.json 执行确定性规则；不会调用大模型…')
    setAuditResult(null)
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/documents/${result.job_id}/audit-rules?profile=${encodeURIComponent(DEFAULT_AUDIT_PROFILE)}`,
        { method: 'POST' },
      )
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body && typeof body.detail === 'string' ? body.detail : `规则检查失败（HTTP ${response.status}）`
        throw new Error(detail)
      }
      const next = body as AuditRuleReport
      setAuditResult(next)
      setAuditState('success')
      setAuditMessage('确定性检查已保存到本机 audit-rules.json。FAIL 仅表示规则不通过，不等同于违法或最终法律结论。')
    } catch (error) {
      const detail = error instanceof Error ? error.message : '未知错误'
      setAuditState('error')
      setAuditMessage(`确定性规则无法运行：${detail}`)
    }
  }

  return (
    <main className="page-shell">
      <section className="hero">
        <div className="eyebrow">LOCAL · RESEARCH USE</div>
        <h1>Law-Rag</h1>
        <p className="subtitle">智能合同审计辅助系统 · 本地开发版</p>
        <p className="notice">
          当前阶段支持文档证据、合同结构与确定性规则检查；尚未接入法律知识库或大模型，规则 FAIL 不代表违法。
        </p>
      </section>

      <section className="workspace" aria-label="合同导入">
        <div
          className={`drop-zone ${dragging ? 'is-dragging' : ''}`}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => { if (event.currentTarget === event.target) setDragging(false) }}
          onDrop={handleDrop}
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click() }}
        >
          <div className="document-icon" aria-hidden="true">§</div>
          <strong>拖入合同文件</strong>
          <span>或点击选择本机文件</span>
          <span className="file-hint">PDF · JPG · JPEG · PNG · 最大 50 MiB</span>
          <input ref={inputRef} className="file-input" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" onChange={handleInput} />
        </div>

        {file && (
          <div className="selected-file">
            <div><span className="meta-label">已选择文件</span><strong>{file.name}</strong></div>
            <div className="file-size">{formatBytes(file.size)}</div>
          </div>
        )}

        <button className="primary-action" onClick={upload} disabled={!file || state === 'uploading'}>
          {state === 'uploading' ? '正在检查…' : '导入并检查文档'}
        </button>
        {message && <div className={`status status-${state}`}>{message}</div>}
      </section>

      {result && (
        <section className="result-card" aria-label="文档检查结果">
          <div className="result-heading">
            <div><span className="meta-label">Document Evidence</span><h2>文档检查完成</h2></div>
            <span className={`route-pill route-${result.route.toLowerCase()}`}>{routeLabel(result.route)}</span>
          </div>
          <div className="route-metrics">
            <div><span>总页数</span><strong>{result.page_count}</strong></div>
            <div><span>原生文本页</span><strong>{result.native_text_pages}</strong></div>
            <div><span>待 OCR 页</span><strong>{result.ocr_required_pages}</strong></div>
          </div>
          <dl>
            <div><dt>文件名</dt><dd>{result.filename}</dd></div>
            <div><dt>文档类型</dt><dd>{result.document_kind.toUpperCase()}</dd></div>
            <div><dt>大小</dt><dd>{formatBytes(result.size_bytes)}</dd></div>
            <div><dt>任务 ID</dt><dd className="mono">{result.job_id}</dd></div>
          </dl>
          <div className="page-routes">
            <div className="section-label">页级路由</div>
            {result.pages.map((page) => (
              <div className="page-route" key={page.evidence_id}>
                <div><strong>第 {page.page_number} 页</strong><span className="mono">{page.evidence_id}</span></div>
                <div className="page-route-detail"><span>{routeLabel(page.route)}</span><small>{page.character_count} 字符</small></div>
              </div>
            ))}
          </div>
          {result.ocr_required_pages > 0 && (
            <div className="ocr-actions">
              <button className="secondary-action" onClick={runOcr} disabled={ocrState === 'running'}>
                {ocrState === 'running' ? '正在运行本地 OCR…' : `运行本地 OCR（${result.ocr_required_pages} 页）`}
              </button>
              <p>首次使用请先运行根目录 <span className="mono">setup-ocr-cpu.bat</span>。OCR 只处理待识别页面。</p>
              {ocrMessage && <div className={`status status-${ocrState === 'error' ? 'error' : 'ready'}`}>{ocrMessage}</div>}
            </div>
          )}
          <div className="structure-actions">
            <button className="secondary-action" onClick={runStructure} disabled={!canStructure || structureState === 'running'}>
              {structureState === 'running' ? '正在生成合同结构…' : '生成确定性合同结构'}
            </button>
            {!canStructure && result.ocr_required_pages > 0 && <p>必须先完成全部待 OCR 页，失败/无文本页面不能被静默跳过。</p>}
            {structureMessage && <div className={`status status-${structureState === 'error' ? 'error' : 'ready'}`}>{structureMessage}</div>}
          </div>
        </section>
      )}

      {ocrResult && (
        <section className="result-card" aria-label="OCR 结果">
          <div className="result-heading">
            <div><span className="meta-label">OCR Evidence</span><h2>本地 OCR 证据</h2></div>
            <span className="success-pill">{ocrResult.status.toUpperCase()}</span>
          </div>
          <div className="route-metrics ocr-metrics">
            <div><span>尝试 OCR</span><strong>{ocrResult.ocr_pages_attempted}</strong></div>
            <div><span>识别出文本</span><strong>{ocrResult.ocr_pages_complete}</strong></div>
            <div><span>低置信度页</span><strong>{ocrResult.low_confidence_pages}</strong></div>
            <div><span>失败页</span><strong>{ocrResult.failed_pages}</strong></div>
            <div><span>无文本页</span><strong>{ocrResult.no_text_pages}</strong></div>
          </div>
          <dl>
            <div><dt>OCR Provider</dt><dd>{ocrResult.provider}</dd></div>
            <div><dt>模型</dt><dd>{ocrResult.model}</dd></div>
            <div><dt>Provider 版本</dt><dd>{ocrResult.provider_version}</dd></div>
          </dl>
          <div className="page-routes">
            <div className="section-label">处理后页级证据</div>
            {ocrResult.pages.map((page) => (
              <div className="page-route" key={`ocr-${page.page_number}`}>
                <div><strong>第 {page.page_number} 页</strong><span>{page.source_method === 'ocr' ? 'OCR evidence' : 'Native evidence'}</span></div>
                <div className="page-route-detail">
                  <span>{ocrStateLabel(page.state)}</span>
                  {page.low_confidence_blocks > 0 && <small>{page.low_confidence_blocks} 个低置信度块</small>}
                  {page.error && <small className="warning-text">{page.error}</small>}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {structureResult && (
        <section className="result-card structure-card" aria-label="合同结构结果">
          <div className="result-heading">
            <div><span className="meta-label">Canonical Contract · v{structureResult.schema_version}</span><h2>{structureResult.title ?? '未识别标题'}</h2></div>
            <span className="success-pill">STRUCTURED</span>
          </div>
          <div className="structure-metrics">
            <div><span>条款</span><strong>{structureResult.clause_count}</strong></div>
            <div><span>主体出现项</span><strong>{structureResult.party_count}</strong></div>
            <div><span>日期</span><strong>{structureResult.date_count}</strong></div>
            <div><span>金额</span><strong>{structureResult.money_count}</strong></div>
            <div><span>百分比</span><strong>{structureResult.percentage_count}</strong></div>
            <div><span>编号</span><strong>{structureResult.identifier_count}</strong></div>
            <div><span>未解析引用</span><strong>{structureResult.unresolved_reference_count}</strong></div>
            <div><span>警告</span><strong>{structureResult.warning_count}</strong></div>
          </div>

          {structureResult.parties.length > 0 && (
            <div className="structure-section">
              <div className="section-label">主体出现项</div>
              {structureResult.parties.map((party) => (
                <div className="fact-row" key={party.mention_id}>
                  <strong>{party.role_label}</strong>
                  <span>{party.raw_name ?? '名称未解析'}</span>
                </div>
              ))}
            </div>
          )}

          {structureResult.identifiers.length > 0 && (
            <div className="structure-section">
              <div className="section-label">显式编号</div>
              {structureResult.identifiers.map((item) => (
                <div className="fact-row" key={item.mention_id}><strong>{item.label}</strong><span>{item.raw_value}</span></div>
              ))}
            </div>
          )}

          <div className="structure-section">
            <div className="section-label">条款大纲</div>
            {structureResult.clauses.length === 0 && <p className="empty-note">未检测到可保守确认的编号条款。</p>}
            {structureResult.clauses.map((clause) => (
              <div className="clause-row" key={clause.clause_id} style={{ paddingLeft: `${Math.max(0, clause.level - 1) * 18}px` }}>
                <div><strong>{clause.heading_token} {clause.heading_text}</strong><span className="mono">{clause.clause_id}</span></div>
                <small>{clause.page_start === clause.page_end ? `第 ${clause.page_start} 页` : `第 ${clause.page_start}–${clause.page_end} 页`}</small>
              </div>
            ))}
          </div>

          <div className="structure-section compact-facts">
            <div className="section-label">其他显式事实</div>
            <p>日期：{structureResult.dates.map((item) => item.iso_date ?? item.raw_text).join(' · ') || '无'}</p>
            <p>金额：{structureResult.money_mentions.map((item) => item.raw_text).join(' · ') || '无'}</p>
            <p>百分比：{structureResult.percentages.map((item) => item.raw_text).join(' · ') || '无'}</p>
          </div>

          <div className="audit-actions">
            <button className="primary-action" onClick={runAuditRules} disabled={auditState === 'running'}>
              {auditState === 'running' ? '正在运行确定性检查…' : '运行确定性审计规则'}
            </button>
            <p>当前使用显式审计配置 <span className="mono">{DEFAULT_AUDIT_PROFILE}</span>。规则只读取 contract.json，不重新解释原始 PDF。</p>
            {auditMessage && <div className={`status status-${auditState === 'error' ? 'error' : 'ready'}`}>{auditMessage}</div>}
          </div>
          <p className="stage-boundary">Stage 5 只做可解释的机器规则检查。FAIL 表示规则条件不满足，不等于违法、无效或最终法律风险结论。</p>
        </section>
      )}

      {auditResult && (
        <section className="result-card audit-card" aria-label="确定性审计规则结果">
          <div className="result-heading">
            <div>
              <span className="meta-label">Deterministic Rules · {auditResult.engine_version}</span>
              <h2>确定性规则检查</h2>
            </div>
            <span className="success-pill">{auditResult.profile.profile_id}</span>
          </div>

          <div className="audit-metrics">
            <div><span>规则结果</span><strong>{auditResult.counts.total}</strong></div>
            <div><span>通过</span><strong>{auditResult.counts.passed}</strong></div>
            <div><span>规则不通过</span><strong>{auditResult.counts.failed}</strong></div>
            <div><span>需复核</span><strong>{auditResult.counts.review}</strong></div>
            <div><span>不适用</span><strong>{auditResult.counts.not_applicable}</strong></div>
          </div>

          {auditResult.engine_errors.length > 0 && (
            <div className="status status-error">
              有 {auditResult.engine_errors.length} 条规则发生执行异常；其他规则仍已继续运行，请查看开发日志/结果。
            </div>
          )}

          <div className="rule-results">
            {auditResult.results.map((rule) => (
              <article className={`rule-result rule-state-${rule.state.toLowerCase()}`} key={rule.result_id}>
                <div className="rule-result-heading">
                  <div>
                    <span className="mono">{rule.rule_id} · v{rule.rule_version}</span>
                    <h3>{rule.title}</h3>
                  </div>
                  <span className={`rule-state-pill state-${rule.state.toLowerCase()}`}>{ruleStateLabel(rule.state)}</span>
                </div>
                <p>{rule.explanation}</p>
                <div className="rule-meta">
                  <span>原因码：<span className="mono">{rule.reason_code}</span></span>
                  {rule.deterministic_state !== rule.state && <span>原始机器判定：{ruleStateLabel(rule.deterministic_state)}</span>}
                  {rule.evidence_ids.length > 0 && <span>Evidence：{rule.evidence_ids.join(' · ')}</span>}
                </div>
                {rule.observed_values.length > 0 && (
                  <div className="observed-values">
                    {rule.observed_values.map((item, index) => (
                      <span key={`${rule.result_id}-${item.label}-${index}`}><strong>{item.label}</strong> {item.value}</span>
                    ))}
                  </div>
                )}
                {rule.review_reasons.length > 0 && (
                  <ul className="review-reasons">
                    {rule.review_reasons.map((reason) => <li key={reason}>{reason}</li>)}
                  </ul>
                )}
              </article>
            ))}
          </div>
          <p className="stage-boundary">这里没有法条检索或大模型法律结论。法律知识库将在 Stage 6 建立，RAG 从 Stage 7 才开始。</p>
        </section>
      )}

      <footer>真实合同、脱敏测试集和 API Key 不应提交到 GitHub。正式法律判断必须由专业人员复核。</footer>
    </main>
  )
}

export default App
