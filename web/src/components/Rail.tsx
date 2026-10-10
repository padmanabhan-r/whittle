import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export function Rail({ children, foot }: { children?: ReactNode; foot?: ReactNode }) {
  return (
    <aside className="rail">
      <Link className="wordmark" to="/">Whittle</Link>
      <nav aria-label="Whittle">
        <Link className="item" to="/app">New job</Link>
      </nav>
      {children}
      {foot && <div className="foot">{foot}</div>}
    </aside>
  )
}
