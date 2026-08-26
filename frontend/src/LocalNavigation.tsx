import { MouseEvent, useEffect, useState } from 'react'
import { LOCAL_ROUTE_CHANGE_EVENT, navigateLocal } from './localRouting'

export default function LocalNavigation() {
  const [path, setPath] = useState(window.location.pathname)
  const links = [
    ['/', '上传合同'],
    ['/results', '批量结果'],
    ['/history', '历史记录'],
    ['/legal', '法律知识库'],
    ['/?settings=1', 'API 设置'],
  ] as const

  useEffect(() => {
    const sync = () => setPath(window.location.pathname)
    window.addEventListener('popstate', sync)
    window.addEventListener(LOCAL_ROUTE_CHANGE_EVENT, sync)
    return () => {
      window.removeEventListener('popstate', sync)
      window.removeEventListener(LOCAL_ROUTE_CHANGE_EVENT, sync)
    }
  }, [])

  const handleNavigation = (event: MouseEvent<HTMLAnchorElement>, href: string) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) {
      return
    }
    event.preventDefault()
    navigateLocal(href)
  }

  return (
    <nav className="local-navigation" aria-label="Law-Rag 本机导航">
      {links.map(([href, label]) => {
        const cleanHref = href.split('?')[0]
        const active = href === '/?settings=1' ? false : cleanHref === '/' ? path === '/' : path === cleanHref || path.startsWith(`${cleanHref}/`)
        return (
          <a
            key={href}
            href={href}
            className={active ? 'is-active' : ''}
            aria-current={active ? 'page' : undefined}
            onClick={(event) => handleNavigation(event, href)}
          >
            {label}
          </a>
        )
      })}
    </nav>
  )
}
