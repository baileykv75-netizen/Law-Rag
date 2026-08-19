import { DragEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  API_BASE_URL,
  PipelineReport,
  ProviderExecutionMode,
  approveProvider,
  cancelPipeline,
  pauseFutureProviders,
  resumeCancelledPipeline,
} from './pipelineControlClient'

const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.jpg', '.jpeg', '.png']
const CURRENT_MAX_BYTES = 500 * 1024 * 1024

type QueueState =
  | 'queued'
  | 'uploading'
  | 'inspecting'
  | 'processing'
  | 'waiting'
  | 'cancelled'
  | 'complete'
  | 'error'

type UploadResponse = {
  job_id: string
  filename: string
  document_kind: 'pdf' | 'image' | 'docx'
  page_count: number
  route: string
  ocr_required_pages: number
  evidence_count: number
  warnings: string[]
}

type QueueItem = {
  id: string
  file: File
  state: QueueState
  progress: number
  error: string | null
  notice: string | null
  result: UploadResponse | null
  pipeline: PipelineReport | null
  providerMode: ProviderExecutionMode
}

type BatchManifest = {
  batch_id: string
}

type BatchSummary = {
  batch_id: string
  total_jobs: number
  complete_jobs: number
  waiting_jobs: number
  cancelled_jobs?: number
  failed_jobs: number
  processing_jobs: number
}

function extensionOf(name: string) {
  const index = name.lastIndexOf('.')
  return index >= 0 ? name.slice(index).toLowerCase() : ''
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(bytes >= 100 * 1024 * 1024 ? 0 : 1)} MB`
}

function validateFile(file: File): string | null {
  if (!ALLOWED_EXTENSIONS.includes(extensionOf(file.name))) {
    return '暂支持 PDF、DOCX、JPG、JPEG、PNG。'
  }
  if (file.size === 0) return '文件为空。'
  if (file.size > CURRENT_MAX_BYTES) return '单文件上限为 500 MB。'
  return null
}

function sourceWarningNotice(warnings: string[]) {
  if (!warnings.length) return null
  const visible = warnings.slice(0, 2).join('；')
  const remainder = warnings.length > 2 ? '；其余提示请在工作台源文件视图查看。' : ''
  return `源文件解析提示（${warnings.length}）：${visible}${remainder}`
}

function sourceSummary(result: UploadResponse) {
  if (result.document_kind === 'docx') {
    return `DOCX · ${result.evidence_count} 个源证据`
  }
  return `${result.page_count} 页${result.ocr_required_pages > 0 ? ` · ${result.ocr_required_pages} 页需要 OCR` : ''}`
}

function localToday() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function pipelineStageLabel(stage: PipelineReport['current_stage']) {
  if (stage === 'INGEST') return '文件已接收'
  if (stage === 'OCR') return '正在识别扫描文本'
  if (stage === 'STRUCTURE') return '正在整理合同结构'
  if (stage === 'RULES') return '正在执行确定性合同检查'
  if (stage === 'AUDIT_PLAN') return '正在生成完整审计规划'
  if (stage === 'ISSUE_LEGAL_CONTEXT') return '正在按 Issue 检索法律依据'
  if (stage === 'ISSUE_PRIMARY_AUDIT') return 'DeepSeek 正在逐 Issue 主审'
  if (stage === 'ISSUE_SECONDARY_REVIEW') return 'Kimi 正在逐 Issue 独立复核'
  if (stage === 'ISSUE_REVIEW_REPORT') return '正在确定性比较并整理审计结果'
  // Persisted Legacy RC2 jobs remain readable during the compatibility window.
  if (stage === 'PRIMARY_AUDIT') return 'Legacy RC2 · 正在主审'
  if (stage === 'SECONDARY_REVIEW') return 'Legacy RC2 · 正在独立二审'
  if (stage === 'REVIEW_REPORT') return 'Legacy RC2 · 正在整理报告'
  return '审计完成'
}

function providerModeCopy(mode: ProviderExecutionMode) {
  if (mode === 'AUTO_CONTINUE') return '完成本地结构化与确定性检查后，自动进入 Planner / DeepSeek / Kimi 的受限云端审计。'
  if (mode === 'LOCAL_ONLY') return '只运行本地结构化与确定性检查；到 Audit Planner 的首次云端调用前暂停，除非之后明确批准。'
  return '推荐：先完成本地结构化与确定性检查，在 Audit Planner 第一次发送合同证据到云端前停下等待确认。'
}

function stateLabel(item: QueueItem) {
  if (item.state === 'queued') return '等待上传'
  if (item.state === 'uploading') return `正在上传 ${Math.round(item.progress)}%`
  if (item.state === 'inspecting') return '正在读取文档'
  if (item.state === 'processing') {
    if (item.pipeline?.status === 'CANCEL_REQUESTED') return '正在安全取消'
    if (item.pipeline?.status === 'QUEUED' || item.pipeline?.status === 'WAITING_WORKER') {
      return '等待后台处理名额'
    }
    return item.pipeline ? pipelineStageLabel(item.pipeline.current_stage) : '正在启动后台审计'
  }
  if (item.state === 'waiting') {
    if (item.pipeline?.status === 'PAUSED_BEFORE_PROVIDER') return '等待下一次云端调用确认'
    if (item.pipeline?.status === 'WAITING_OPTIONAL_COMPONENT') return '等待可选组件'
    return '等待 API 配置'
  }
  if (item.state === 'cancelled') return '已取消'
  if (item.state === 'complete') return '审计流水线完成'
  return '处理失败'
}

function createQueueItem(file: File, providerMode: ProviderExecutionMode): QueueItem {
  const error = validateFile(file)
  return {
    id: `${file.name}-${file.size}-${file.lastModified}-${crypto.randomUUID()}`,
    file,
    state: error ? 'error' : 'queued',
    progress: 0,
    error,
    notice: null,
    result: null,
    pipeline: null,
    providerMode,
  }
}

function IntakeApp() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [items, setItems] = useState<QueueItem[]>([])
  const [dragging, setDragging] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [batchId, setBatchId] = useState<string | null>(null)
  const [batchError, setBatchError] = useState<string | null>(null)
  const [recentBatch, setRecentBatch] = useState<BatchSummary | null>(null)
  const [providerMode, setProviderMode] = useState<ProviderExecutionMode>('REQUIRE_APPROVAL')
  const [actionId, setActionId] = useState<string | null>(null)
  const pollingIds = useRef(new Set<string>())
  const mounted = useRef(true)
  const batchIdRef = useRef<string | null>(null)
  const batchPromiseRef = useRef<Promise<string> | null>(null)
  const autoOpenedResults = useRef(false)

  useEffect(() => {
    mounted.current = true
    void fetch(`${API_BASE_URL}/api/batches/recent`)
      .then(async (response) => (response.ok ? ((await response.json()) as BatchSummary | null) : null))
      .then((summary) => {
        if (mounted.current && summary?.total_jobs) setRecentBatch(summary)
      })
      .catch(() => undefined)
    return () => {
      mounted.current = false
    }
  }, [])

  const ensureBatch = async () => {
    if (batchIdRef.current) return batchIdRef.current
    if (!batchPromiseRef.current) {
      batchPromiseRef.current = fetch(`${API_BASE_URL}/api/batches`, { method: 'POST' })
        .then(async (response) => {
          if (!response.ok) throw new Error(`无法创建本地批次（HTTP ${response.status}）。`)
          const manifest = (await response.json()) as BatchManifest
          batchIdRef.current = manifest.batch_id
          if (mounted.current) {
            setBatchId(manifest.batch_id)
            setBatchError(null)
          }
          return manifest.batch_id
        })
        .finally(() => {
          batchPromiseRef.current = null
        })
    }
    return batchPromiseRef.current
  }

  const queuedCount = items.filter((item) => item.state === 'queued').length
  const completeCount = items.filter((item) => item.state === 'complete').length
  const waitingCount = items.filter((item) => item.state === 'waiting').length
  const cancelledCount = items.filter((item) => item.state === 'cancelled').length
  const errorCount = items.filter((item) => item.state === 'error').length

  const itemProgress = (item: QueueItem) => {
    if (item.state === 'complete') return 100
    if (item.pipeline) return item.pipeline.progress_percent
    if (item.state === 'inspecting') return 9
    if (item.state === 'uploading') return Math.min(8, item.progress * 0.08)
    return 0
  }

  const batchProgress = useMemo(() => {
    if (!items.length) return 0
    return Math.round(items.reduce((sum, item) => sum + itemProgress(item), 0) / items.length)
  }, [items])

  useEffect(() => {
    if (!batchId || !items.length || autoOpenedResults.current) return
    if (items.every((item) => item.state === 'complete')) {
      autoOpenedResults.current = true
      window.location.assign(`/results?batch=${encodeURIComponent(batchId)}`)
    }
  }, [batchId, items])

  const updatePipelineItem = (id: string, pipeline: PipelineReport) => {
    setItems((current) =>
      current.map((item) => {
        if (item.id !== id) return item
        if (pipeline.status === 'COMPLETE') {
          return { ...item, state: 'complete', progress: 100, pipeline, error: null }
        }
        if (pipeline.status === 'CANCELLED') {
          return {
            ...item,
            state: 'cancelled',
            progress: pipeline.progress_percent,
            pipeline,
            error: null,
          }
        }
        if (
          pipeline.status === 'WAITING_CONFIGURATION' ||
          pipeline.status === 'WAITING_OPTIONAL_COMPONENT' ||
          pipeline.status === 'PAUSED_BEFORE_PROVIDER'
        ) {
          return {
            ...item,
            state: 'waiting',
            progress: pipeline.progress_percent,
            pipeline,
            error: pipeline.status === 'PAUSED_BEFORE_PROVIDER' ? null : pipeline.failure_detail,
          }
        }
        if (pipeline.status === 'FAILED') {
          return {
            ...item,
            state: 'error',
            progress: pipeline.progress_percent,
            pipeline,
            error: pipeline.failure_detail ?? '后台审计失败。',
          }
        }
        return {
          ...item,
          state: 'processing',
          progress: pipeline.progress_percent,
          pipeline,
          error: null,
        }
      }),
    )
  }

  const pollPipeline = async (id: string, jobId: string) => {
    if (pollingIds.current.has(id)) return
    pollingIds.current.add(id)
    try {
      while (mounted.current) {
        const response = await fetch(`${API_BASE_URL}/api/documents/${jobId}/pipeline`)
        if (!response.ok) throw new Error(`无法读取后台审计状态（HTTP ${response.status}）。`)
        const pipeline = (await response.json()) as PipelineReport
        if (!mounted.current) return
        updatePipelineItem(id, pipeline)
        if (
          pipeline.status === 'COMPLETE' ||
          pipeline.status === 'FAILED' ||
          pipeline.status === 'CANCELLED' ||
          pipeline.status === 'PAUSED_BEFORE_PROVIDER' ||
          pipeline.status === 'WAITING_CONFIGURATION' ||
          pipeline.status === 'WAITING_OPTIONAL_COMPONENT'
        ) {
          return
        }
        await new Promise((resolve) => window.setTimeout(resolve, 800))
      }
    } catch (error) {
      if (!mounted.current) return
      setItems((current) =>
        current.map((item) =>
          item.id === id
            ? { ...item, state: 'error', error: error instanceof Error ? error.message : '无法读取后台审计状态。' }
            : item,
        ),
      )
    } finally {
      pollingIds.current.delete(id)
    }
  }

  const beginPipeline = async (id: string, jobId: string, mode: ProviderExecutionMode) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${jobId}/pipeline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ as_of: localToday(), use_semantic: false, provider_mode: mode }),
      })
      if (!response.ok) {
        let message = `无法启动后台审计（HTTP ${response.status}）。`
        try {
          const payload = (await response.json()) as { detail?: string }
          if (payload.detail) message = payload.detail
        } catch {
          // Keep the safe generic message.
        }
        throw new Error(message)
      }
      const pipeline = (await response.json()) as PipelineReport
      updatePipelineItem(id, pipeline)
      void pollPipeline(id, jobId)
    } catch (error) {
      setItems((current) =>
        current.map((item) =>
          item.id === id
            ? { ...item, state: 'error', error: error instanceof Error ? error.message : '无法启动后台审计。' }
            : item,
        ),
      )
    }
  }

  const registerAndBeginPipeline = async (id: string, jobId: string, mode: ProviderExecutionMode) => {
    const currentBatchId = batchIdRef.current ?? (await ensureBatch())
    const response = await fetch(
      `${API_BASE_URL}/api/batches/${encodeURIComponent(currentBatchId)}/jobs/${encodeURIComponent(jobId)}`,
      { method: 'POST' },
    )
    if (!response.ok) throw new Error(`无法登记批次结果（HTTP ${response.status}）。`)
    await beginPipeline(id, jobId, mode)
  }

  const retryPipeline = async (item: QueueItem) => {
    if (!item.result) return
    setActionId(item.id)
    setItems((current) =>
      current.map((candidate) =>
        candidate.id === item.id
          ? { ...candidate, state: 'processing', error: null, notice: sourceWarningNotice(item.result?.warnings ?? []) }
          : candidate,
      ),
    )
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/${item.result.job_id}/pipeline/retry`, { method: 'POST' })
      if (!response.ok) throw new Error(`重试失败（HTTP ${response.status}）。`)
      const pipeline = (await response.json()) as PipelineReport
      updatePipelineItem(item.id, pipeline)
      void pollPipeline(item.id, item.result.job_id)
    } catch (error) {
      setItems((current) =>
        current.map((candidate) =>
          candidate.id === item.id
            ? { ...candidate, state: 'error', error: error instanceof Error ? error.message : '无法重试后台审计。' }
            : candidate,
        ),
      )
    } finally {
      setActionId(null)
    }
  }

  const approveCloud = async (item: QueueItem) => {
    if (!item.result) return
    setActionId(item.id)
    try {
      const pipeline = await approveProvider(item.result.job_id)
      setItems((current) => current.map((candidate) => (
        candidate.id === item.id
          ? { ...candidate, state: 'processing', pipeline, error: null, notice: '已明确批准该合同继续执行受限 Planner / DeepSeek / Kimi 云端审计。', providerMode: 'REQUIRE_APPROVAL' }
          : candidate
      )))
      void pollPipeline(item.id, item.result.job_id)
    } catch (caught) {
      setItems((current) => current.map((candidate) => (
        candidate.id === item.id
          ? { ...candidate, error: caught instanceof Error ? caught.message : '无法批准云端审计。' }
          : candidate
      )))
    } finally {
      setActionId(null)
    }
  }

  const pauseCloud = async (item: QueueItem) => {
    if (!item.result) return
    setActionId(item.id)
    try {
      const control = await pauseFutureProviders(item.result.job_id)
      const notice = control.active_provider
        ? `当前 ${control.active_provider} 请求已经开始，无法撤回；后续 Planner / DeepSeek / Kimi 调用已设置为发送前暂停。`
        : '已设置为发送前确认；尚未开始的 Planner / DeepSeek / Kimi 调用不会自动发送。'
      setItems((current) => current.map((candidate) => (
        candidate.id === item.id
          ? { ...candidate, providerMode: 'REQUIRE_APPROVAL', notice }
          : candidate
      )))
    } catch (caught) {
      setItems((current) => current.map((candidate) => (
        candidate.id === item.id
          ? { ...candidate, error: caught instanceof Error ? caught.message : '无法暂停后续云端调用。' }
          : candidate
      )))
    } finally {
      setActionId(null)
    }
  }

  const cancelAudit = async (item: QueueItem) => {
    if (!item.result) return
    setActionId(item.id)
    try {
      const action = await cancelPipeline(item.result.job_id)
      setItems((current) => current.map((candidate) => (
        candidate.id === item.id
          ? {
              ...candidate,
              state: 'processing',
              error: null,
              notice: action.provider_in_flight
                ? `${action.detail} 当前 ${action.control.active_provider ?? '外部模型'} 请求已经开始，无法撤回已发送内容。`
                : action.detail,
            }
          : candidate
      )))
      void pollPipeline(item.id, item.result.job_id)
    } catch (caught) {
      setItems((current) => current.map((candidate) => (
        candidate.id === item.id
          ? { ...candidate, error: caught instanceof Error ? caught.message : '无法取消审计。' }
          : candidate
      )))
    } finally {
      setActionId(null)
    }
  }

  const resumeCancelled = async (item: QueueItem) => {
    if (!item.result) return
    setActionId(item.id)
    try {
      const pipeline = await resumeCancelledPipeline(item.result.job_id)
      setItems((current) => current.map((candidate) => (
        candidate.id === item.id
          ? { ...candidate, state: 'processing', pipeline, error: null, notice: '已按原云端策略显式重新开始审计。' }
          : candidate
      )))
      void pollPipeline(item.id, item.result.job_id)
    } catch (caught) {
      setItems((current) => current.map((candidate) => (
        candidate.id === item.id
          ? { ...candidate, error: caught instanceof Error ? caught.message : '无法重新开始审计。' }
          : candidate
      )))
    } finally {
      setActionId(null)
    }
  }

  const addFiles = async (files: File[]) => {
    if (!files.length) return
    try {
      await ensureBatch()
    } catch (error) {
      setBatchError(error instanceof Error ? error.message : '无法创建本地审计批次。')
      return
    }
    setRecentBatch(null)
    setItems((current) => {
      const existing = new Set(current.map((item) => `${item.file.name}::${item.file.size}::${item.file.lastModified}`))
      const additions = files
        .filter((file) => !existing.has(`${file.name}::${file.size}::${file.lastModified}`))
        .map((file) => createQueueItem(file, providerMode))
      return [...current, ...additions]
    })
  }

  useEffect(() => {
    if (activeId || !batchId) return
    const next = items.find((item) => item.state === 'queued')
    if (next) setActiveId(next.id)
  }, [activeId, batchId, items])

  useEffect(() => {
    if (!activeId || !batchId) return
    const item = items.find((candidate) => candidate.id === activeId)
    if (!item || item.state !== 'queued') {
      setActiveId(null)
      return
    }

    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', item.file)

    setItems((current) =>
      current.map((candidate) =>
        candidate.id === activeId ? { ...candidate, state: 'uploading', progress: 0, error: null } : candidate,
      ),
    )

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      const progress = Math.min(100, (event.loaded / event.total) * 100)
      setItems((current) =>
        current.map((candidate) =>
          candidate.id === activeId
            ? { ...candidate, state: progress >= 100 ? 'inspecting' : 'uploading', progress }
            : candidate,
        ),
      )
    }

    xhr.onload = () => {
      void (async () => {
        try {
          if (xhr.status !== 201) {
            let message = `上传失败（HTTP ${xhr.status}）。`
            try {
              const payload = JSON.parse(xhr.responseText) as { detail?: string }
              if (payload.detail) message = payload.detail
            } catch {
              // Keep the safe generic message; never surface an arbitrary HTML response.
            }
            throw new Error(message)
          }

          let result: UploadResponse | null = null
          try {
            result = JSON.parse(xhr.responseText) as UploadResponse
          } catch {
            result = null
          }
          if (!result) throw new Error('本地服务返回了无法读取的文档结果。')

          setItems((current) =>
            current.map((candidate) =>
              candidate.id === activeId
                ? {
                    ...candidate,
                    state: 'processing',
                    progress: 10,
                    result,
                    pipeline: null,
                    error: null,
                    notice: sourceWarningNotice(result.warnings ?? []),
                  }
                : candidate,
            ),
          )
          await registerAndBeginPipeline(activeId, result.job_id, item.providerMode)
        } catch (error) {
          setItems((current) =>
            current.map((candidate) =>
              candidate.id === activeId
                ? { ...candidate, state: 'error', error: error instanceof Error ? error.message : '本地处理失败。' }
                : candidate,
            ),
          )
        } finally {
          setActiveId(null)
        }
      })()
    }

    xhr.onerror = () => {
      setItems((current) =>
        current.map((candidate) =>
          candidate.id === activeId ? { ...candidate, state: 'error', error: '无法连接本地 Law-Rag 服务。' } : candidate,
        ),
      )
      setActiveId(null)
    }

    xhr.open('POST', `${API_BASE_URL}/api/documents`)
    xhr.send(form)

    return () => {
      if (xhr.readyState !== XMLHttpRequest.DONE) xhr.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, batchId])

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    void addFiles(Array.from(event.dataTransfer.files))
  }

  const retryUpload = (id: string) => {
    setItems((current) =>
      current.map((item) =>
        item.id === id && validateFile(item.file) === null
          ? { ...item, state: 'queued', progress: 0, error: null, notice: null, result: null, pipeline: null }
          : item,
      ),
    )
  }

  const remove = (id: string) => {
    if (id === activeId) return
    setItems((current) => current.filter((item) => item.id !== id))
  }

  return (
    <main className="intake-shell">
      <header className="intake-header">
        <div>
          <p className="intake-eyebrow">LAW-RAG</p>
          <h1>合同审计</h1>
        </div>
        <a className="intake-developer-link" href="/developer" aria-label="打开高级调试模式">高级模式</a>
      </header>

      <section className="intake-card" aria-label="合同文件导入">
        {items.length === 0 && recentBatch && (
          <a className="batch-recent-link" href={`/results?batch=${encodeURIComponent(recentBatch.batch_id)}`}>
            查看最近批次 · {recentBatch.complete_jobs}/{recentBatch.total_jobs} 已完成
          </a>
        )}
        {batchError && <p className="intake-error-text">{batchError}</p>}

        <div className="provider-boundary-choice" aria-label="云端审计策略">
          <div>
            <strong>云端审计</strong>
            <span>{providerModeCopy(providerMode)}</span>
          </div>
          <select
            value={providerMode}
            onChange={(event) => setProviderMode(event.target.value as ProviderExecutionMode)}
            disabled={items.length > 0}
            aria-label="选择云端审计策略"
          >
            <option value="REQUIRE_APPROVAL">发送前确认（推荐）</option>
            <option value="AUTO_CONTINUE">本地检查后自动继续</option>
            <option value="LOCAL_ONLY">仅本地检查</option>
          </select>
        </div>

        <div
          className={`intake-dropzone${dragging ? ' is-dragging' : ''}`}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true) }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') inputRef.current?.click()
          }}
        >
          <input
            ref={inputRef}
            className="intake-file-input"
            type="file"
            multiple
            accept=".pdf,.docx,.jpg,.jpeg,.png,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/jpeg,image/png"
            onChange={(event) => {
              void addFiles(Array.from(event.target.files ?? []))
              event.currentTarget.value = ''
            }}
          />
          <div className="intake-drop-icon" aria-hidden="true">＋</div>
          <h2>拖入合同文件</h2>
          <p>也可以点击选择多个文件</p>
          <span>PDF · DOCX · JPG · PNG · 单文件最大 500 MB</span>
        </div>

        <p className="intake-transmission-note">
          合同先在本机完成读取、OCR（需要时）、结构化和确定性规则检查。DOCX 使用结构化源证据，不会伪造页码；源文件解析提示会先在此处显示，并可在工作台源文件视图继续查看。之后 Audit Planner、DeepSeek 逐 Issue 主审与 Kimi 独立复核都必须经过持久化云端策略；每次真正发送前都会重新检查批准与取消状态。已经开始的外部请求无法撤回已发送内容。
        </p>

        {items.length > 0 && (
          <div className="intake-queue-wrap">
            <div className="intake-batch-summary">
              <div>
                <strong>{completeCount}/{items.length}</strong>
                <span> 流水线完成</span>
                {queuedCount > 0 && <span> · {queuedCount} 个等待上传</span>}
                {waitingCount > 0 && <span> · {waitingCount} 个等待确认/配置</span>}
                {cancelledCount > 0 && <span> · {cancelledCount} 个已取消</span>}
                {errorCount > 0 && <span className="intake-error-text"> · {errorCount} 个失败</span>}
              </div>
              <span>{batchProgress}%</span>
            </div>
            <div className="intake-batch-progress" aria-label={`批次进度 ${batchProgress}%`}>
              <div style={{ width: `${batchProgress}%` }} />
            </div>

            {(completeCount > 0 || waitingCount > 0 || cancelledCount > 0 || errorCount > 0) && batchId && (
              <div className="batch-result-entry">
                <a href={`/results?batch=${encodeURIComponent(batchId)}`}>查看批次结果</a>
                <span>全部流水线正常完成时会自动进入结果页；需要人工复核的 Issue 会在结果页和工作台继续保留。</span>
              </div>
            )}

            <div className="intake-queue" aria-live="polite">
              {items.map((item) => {
                const rowProgress = itemProgress(item)
                const pausedForProvider = item.pipeline?.status === 'PAUSED_BEFORE_PROVIDER'
                const retryable = Boolean(
                  item.result &&
                  (item.pipeline?.status === 'WAITING_CONFIGURATION' ||
                    item.pipeline?.status === 'WAITING_OPTIONAL_COMPONENT' ||
                    item.state === 'error'),
                )
                const busy = ['uploading', 'inspecting', 'processing'].includes(item.state)
                const canCancel = Boolean(item.result && !['complete', 'cancelled'].includes(item.state))
                return (
                  <article className={`intake-row state-${item.state}`} key={item.id}>
                    <div className="intake-file-copy">
                      <strong title={item.file.name}>{item.file.name}</strong>
                      <span>{formatBytes(item.file.size)}</span>
                    </div>
                    <div className="intake-row-status">
                      <span>{stateLabel(item)}</span>
                      {(busy || item.state === 'waiting' || item.state === 'cancelled' || item.state === 'complete') && (
                        <div className="intake-row-progress" aria-label={`文件进度 ${Math.round(rowProgress)}%`}>
                          <div style={{ width: `${rowProgress}%` }} />
                        </div>
                      )}
                      {item.error && <small className="intake-error-text">{item.error}</small>}
                      {item.notice && <small>{item.notice}</small>}
                      {item.result && !item.error && item.state !== 'complete' && (
                        <small>
                          {sourceSummary(item.result)}
                          {item.pipeline ? ` · ${item.pipeline.progress_percent}%` : ''}
                        </small>
                      )}
                    </div>
                    <div className="intake-row-actions">
                      {item.state === 'complete' && item.result && (
                        <a className="intake-result-link" href={`/workspace?job=${encodeURIComponent(item.result.job_id)}`}>详细审计</a>
                      )}
                      {pausedForProvider && (
                        <button type="button" onClick={() => void approveCloud(item)} disabled={actionId === item.id}>批准云端审计</button>
                      )}
                      {item.state === 'processing' && item.providerMode === 'AUTO_CONTINUE' && item.pipeline?.status !== 'CANCEL_REQUESTED' && (
                        <button type="button" className="quiet" onClick={() => void pauseCloud(item)} disabled={actionId === item.id}>发送前暂停</button>
                      )}
                      {(item.state === 'waiting' || item.state === 'error') && retryable && !pausedForProvider && (
                        <button type="button" onClick={() => void retryPipeline(item)} disabled={actionId === item.id}>重试审计</button>
                      )}
                      {item.state === 'cancelled' && item.result && (
                        <button type="button" onClick={() => void resumeCancelled(item)} disabled={actionId === item.id}>重新开始</button>
                      )}
                      {canCancel && item.pipeline?.status !== 'CANCEL_REQUESTED' && (
                        <button type="button" className="danger-quiet" onClick={() => void cancelAudit(item)} disabled={actionId === item.id}>取消</button>
                      )}
                      {item.state === 'error' && !item.result && validateFile(item.file) === null && (
                        <button type="button" onClick={() => retryUpload(item.id)}>重试上传</button>
                      )}
                      {!busy && item.state !== 'waiting' && item.state !== 'cancelled' && item.id !== activeId && (
                        <button type="button" className="quiet" onClick={() => remove(item.id)}>移除</button>
                      )}
                    </div>
                  </article>
                )
              })}
            </div>

            <div className="intake-footnote">
              进度来自真实上传字节和后台持久化状态。默认“发送前确认”会先完成本地读取、结构化和规则检查，再在 Audit Planner 的首次云端调用前暂停；后续每一次 Planner / DeepSeek / Kimi 请求仍会重新检查取消与云端策略。
            </div>
          </div>
        )}
      </section>
    </main>
  )
}

export default IntakeApp