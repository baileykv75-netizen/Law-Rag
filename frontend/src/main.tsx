import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import BatchResultsApp from './BatchResultsApp'
import DeveloperApp from './DeveloperApp'
import IntakeApp from './IntakeApp'
import JobHistoryApp from './JobHistoryApp'
import LocalNavigation from './LocalNavigation'
import ProviderSetupGate from './ProviderSetupGate'
import WorkspaceApp from './WorkspaceApp'
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
import './developer.css'
import './job-history.css'

const pathname = window.location.pathname
const isWorkspaceRoute = pathname === '/workspace' || pathname.startsWith('/workspace/')
const isResultsRoute = pathname === '/results' || pathname.startsWith('/results/')
const isHistoryRoute = pathname === '/history' || pathname.startsWith('/history/')
const isDeveloperRoute = pathname === '/developer' || pathname.startsWith('/developer/')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LocalNavigation />
    {isWorkspaceRoute ? (
      <WorkspaceApp />
    ) : isResultsRoute ? (
      <ProviderSetupGate>
        <BatchResultsApp />
      </ProviderSetupGate>
    ) : isHistoryRoute ? (
      <JobHistoryApp />
    ) : isDeveloperRoute ? (
      <DeveloperApp />
    ) : (
      <ProviderSetupGate>
        <IntakeApp />
      </ProviderSetupGate>
    )}
  </StrictMode>,
)
