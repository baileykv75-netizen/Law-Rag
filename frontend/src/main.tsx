import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import AppRouter from './AppRouter'
import './styles.css'
import './workspace.css'
import './source-viewer.css'
import './audit-workstation.css'
import './issue-workspace.css'
import './resource-budget.css'
import './human-review.css'
import './workstation-polish.css'
import './intake.css'
import './provider-setup.css'
import './batch-results.css'
import './job-history.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppRouter />
  </StrictMode>,
)
