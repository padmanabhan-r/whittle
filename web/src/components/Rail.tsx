import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Mark } from './Icons'

export function Rail({ children, foot }: { children?: ReactNode; foot?: ReactNode }) {
  return (
    <aside className="rail">
      <Link className="wordmark" to="/">
        <Mark />
        Whittle AI
      </Link>
      <nav aria-label="Whittle AI">
        <Link className="item" to="/app">New job</Link>
      </nav>
      {children}
      {foot && <div className="foot">{foot}</div>}
    </aside>
  )
}
