import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import LegalKnowledgePanel from './LegalKnowledgePanel'
import LegalRetrievalPanel from './LegalRetrievalPanel'
import PrimaryAuditPanel from './PrimaryAuditPanel'
import SecondaryReviewPanel from './SecondaryReviewPanel'
import WorkspaceApp from './WorkspaceApp'
import './styles.css'
import './workspace.css'

const isWorkspaceRoute = window.location.pathname === '/workspace' || window.location.pathname.startsWith('/workspace/')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isWorkspaceRoute ? (
      <WorkspaceApp />
    ) : (
      <>
        <div className="workspace-launch-strip">
          <a href="/workspace">打开 Stage 10 专业审计工作台 →</a>
        </div>
        <style>{'.hero .notice { display: none; }'}</style>
        <App />
        <LegalKnowledgePanel />
        <LegalRetrievalPanel />
        <PrimaryAuditPanel />
        <SecondaryReviewPanel />
      </>
    )}
  </StrictMode>,
)
