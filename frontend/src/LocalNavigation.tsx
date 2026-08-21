export default function LocalNavigation() {
  const path = window.location.pathname
  const links = [
    ['/', '导入'],
    ['/results', '结果'],
    ['/history', '历史'],
    ['/workspace', '工作台'],
  ] as const

  return (
    <nav className="local-navigation" aria-label="Law-Rag 本机导航">
      {links.map(([href, label]) => {
        const active = href === '/' ? path === '/' : path === href || path.startsWith(`${href}/`)
        return (
          <a key={href} href={href} className={active ? 'is-active' : ''} aria-current={active ? 'page' : undefined}>
            {label}
          </a>
        )
      })}
    </nav>
  )
}
