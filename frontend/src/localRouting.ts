export const LOCAL_ROUTE_CHANGE_EVENT = 'law-rag:route-change'

export function notifyLocalRouteChange() {
  window.dispatchEvent(new Event(LOCAL_ROUTE_CHANGE_EVENT))
}

export function navigateLocal(href: string) {
  const url = new URL(href, window.location.href)
  const next = `${url.pathname}${url.search}${url.hash}`
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`
  if (next !== current) {
    window.history.pushState({}, '', url)
  }
  notifyLocalRouteChange()
}
