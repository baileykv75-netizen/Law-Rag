import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import BatchResultsApp from './BatchResultsApp'
import IntakeApp from './IntakeApp'
import LegalKnowledgePanel from './LegalKnowledgePanel'
import LegalRetrievalPanel from './LegalRetrievalPanel'
import PrimaryAuditPanel from './PrimaryAuditPanel'
import ProviderSetupGate from './ProviderSetupGate'
import SecondaryReviewPanel from './SecondaryReviewPanel'
import WorkspaceApp from './WorkspaceApp'
import './styles.css'
import './workspace.css'
import './source-viewer.css'
import './audit-workstation.css'
import './human-review.css'
import './workstation-polish.css'
import './intake.css'
import './provider-setup.css'
import './batch-results.css'

const pathname = window.location.pathname
const isWorkspaceRoute = pathname === '/workspace' || pathname.startsWith('/workspace/')
const isResultsRoute = pathname === '/results' || pathname.startsWith('/results/')
const isDeveloperRoute = pathname === '/developer' || pathname.startsWith('/developer/')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isWorkspaceRoute ? (
      <WorkspaceApp />
    ) : isResultsRoute ? (
      <BatchResultsApp />
    ) : isDeveloperRoute ? (
      <>
        <div className="workspace-launch-strip">
          <a href="/">← 返回合同导入</a>
          <a href="/workspace">打开专业审计工作台 →</a>
        </div>
        <style>{'.hero .notice { display: none; }'}</style>
        <App />
        <LegalKnowledgePanel />
        <LegalRetrievalPanel />
        <PrimaryAuditPanel />
        <SecondaryReviewPanel />
      </>
    ) : (
      <ProviderSetupGate>
        <IntakeApp />
      </ProviderSetupGate>
    )}
  </StrictMode>,
)
