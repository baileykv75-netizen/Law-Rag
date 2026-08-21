import App from './App'
import LegalKnowledgePanel from './LegalKnowledgePanel'
import LegalRetrievalPanel from './LegalRetrievalPanel'
import PrimaryAuditPanel from './PrimaryAuditPanel'
import SecondaryReviewPanel from './SecondaryReviewPanel'
import Stage13DiagnosticsPanel from './Stage13DiagnosticsPanel'

export default function DeveloperApp() {
  return (
    <main className="developer-shell">
      <div className="workspace-launch-strip">
        <a href="/">← 返回合同导入</a>
        <a href="/workspace">打开专业审计工作台 →</a>
      </div>

      <Stage13DiagnosticsPanel />

      <details className="developer-legacy-section">
        <summary>
          <div>
            <span>LEGACY / RC2</span>
            <strong>旧 Stage 1–9 调试与执行工具</strong>
          </div>
          <small>默认折叠 · 部分按钮会显式执行旧 provider 路径</small>
        </summary>
        <div className="developer-legacy-warning">
          以下组件为历史 RC2 工具，仅用于读取或复现实有 Stage 8/9 行为。带“运行 / 审计 / 复核”字样的按钮可能执行 POST 并调用已配置 provider；它们不属于上方只读 Stage 13 诊断。
        </div>
        <style>{'.hero .notice { display: none; }'}</style>
        <App />
        <LegalKnowledgePanel />
        <LegalRetrievalPanel />
        <PrimaryAuditPanel />
        <SecondaryReviewPanel />
      </details>
    </main>
  )
}
