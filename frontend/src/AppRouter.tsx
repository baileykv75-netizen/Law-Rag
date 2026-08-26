import { useEffect, useState } from 'react'
import BatchResultsApp from './BatchResultsApp'
import IntakeApp from './IntakeApp'
import JobHistoryApp from './JobHistoryApp'
import LegalKnowledgePanel from './LegalKnowledgePanel'
import LocalNavigation from './LocalNavigation'
import { LOCAL_ROUTE_CHANGE_EVENT, navigateLocal } from './localRouting'
import ProviderSetupGate from './ProviderSetupGate'
import WorkspaceApp from './WorkspaceApp'

type RouteKey = 'upload' | 'results' | 'history' | 'legal' | 'workspace'

type BrowserLocation = {
  pathname: string
  search: string
}

function readLocation(): BrowserLocation {
  return {
    pathname: window.location.pathname,
    search: window.location.search,
  }
}

function routeFromPath(pathname: string): RouteKey {
  if (pathname === '/workspace' || pathname.startsWith('/workspace/')) return 'workspace'
  if (pathname === '/results' || pathname.startsWith('/results/')) return 'results'
  if (pathname === '/history' || pathname.startsWith('/history/')) return 'history'
  if (pathname === '/legal' || pathname.startsWith('/legal/')) return 'legal'
  return 'upload'
}

function isLocalAppPath(pathname: string) {
  return (
    pathname === '/'
    || pathname === '/results'
    || pathname.startsWith('/results/')
    || pathname === '/history'
    || pathname.startsWith('/history/')
    || pathname === '/legal'
    || pathname.startsWith('/legal/')
    || pathname === '/workspace'
    || pathname.startsWith('/workspace/')
  )
}

function RoutePane({
  active,
  children,
}: {
  active: boolean
  children: React.ReactNode
}) {
  return (
    <div className="app-route-pane" hidden={!active} aria-hidden={!active}>
      {children}
    </div>
  )
}

export default function AppRouter() {
  const [location, setLocation] = useState(readLocation)
  const route = routeFromPath(location.pathname)
  const [visited, setVisited] = useState<Record<RouteKey, boolean>>({
    upload: route === 'upload',
    results: route === 'results',
    history: route === 'history',
    legal: route === 'legal',
    workspace: route === 'workspace',
  })

  useEffect(() => {
    const sync = () => setLocation(readLocation())
    window.addEventListener('popstate', sync)
    window.addEventListener(LOCAL_ROUTE_CHANGE_EVENT, sync)
    return () => {
      window.removeEventListener('popstate', sync)
      window.removeEventListener(LOCAL_ROUTE_CHANGE_EVENT, sync)
    }
  }, [])

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
        return
      }
      if (!(event.target instanceof Element)) return
      const anchor = event.target.closest('a[href]')
      if (!(anchor instanceof HTMLAnchorElement)) return
      if (anchor.target && anchor.target !== '_self') return
      if (anchor.hasAttribute('download')) return

      const url = new URL(anchor.href)
      if (url.origin !== window.location.origin || !isLocalAppPath(url.pathname)) return

      event.preventDefault()
      navigateLocal(`${url.pathname}${url.search}${url.hash}`)
    }

    document.addEventListener('click', handleClick, true)
    return () => document.removeEventListener('click', handleClick, true)
  }, [])

  useEffect(() => {
    setVisited((current) => (current[route] ? current : { ...current, [route]: true }))
  }, [route])

  return (
    <ProviderSetupGate>
      <LocalNavigation />
      {visited.upload && (
        <RoutePane active={route === 'upload'}>
          <IntakeApp />
        </RoutePane>
      )}
      {visited.results && (
        <RoutePane active={route === 'results'}>
          <BatchResultsApp />
        </RoutePane>
      )}
      {visited.history && (
        <RoutePane active={route === 'history'}>
          <JobHistoryApp />
        </RoutePane>
      )}
      {visited.legal && (
        <RoutePane active={route === 'legal'}>
          <LegalKnowledgePanel />
        </RoutePane>
      )}
      {route === 'workspace' && <WorkspaceApp key={`workspace:${location.search}`} />}
    </ProviderSetupGate>
  )
}
