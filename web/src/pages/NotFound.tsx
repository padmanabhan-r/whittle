import { Link } from 'react-router-dom'

export function NotFound() {
  return (
    <main style={{ padding: '96px 32px', maxWidth: 560 }}>
      <h1 style={{ font: '700 40px/1.05 var(--display)', letterSpacing: '-0.02em' }}>There is no page here.</h1>
      <p style={{ margin: '14px 0 24px', color: 'var(--mute)' }}>
        The address may be mistyped, or the job may have been lost when the server restarted.
      </p>
      <Link className="btn primary" to="/app">Start a new job</Link>
    </main>
  )
}
