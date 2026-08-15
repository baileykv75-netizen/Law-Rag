import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import LegalKnowledgePanel from './LegalKnowledgePanel'
import LegalRetrievalPanel from './LegalRetrievalPanel'
import PrimaryAuditPanel from './PrimaryAuditPanel'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <style>{'.hero .notice { display: none; }'}</style>
    <App />
    <LegalKnowledgePanel />
    <LegalRetrievalPanel />
    <PrimaryAuditPanel />
  </StrictMode>,
)
