import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import LegalKnowledgePanel from './LegalKnowledgePanel'
import './styles.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
    <LegalKnowledgePanel />
  </StrictMode>,
)
