import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { Diff } from '../../lib/api'

export function DiffSection({ jobId, done, nothingFound = false }: { jobId: string; done: boolean; nothingFound?: boolean }) {
  const [diff, setDiff] = useState<Diff | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!done) return
    api.diff(jobId).then(setDiff).catch((e) => setError(e.message))
  }, [jobId, done])

  if (!done) {
    return (
      <div className="panel">
        <div className="empty">
          <h2>The diff is ready when the job is done</h2>
          <p>It holds only the fixes that passed their checks. Reverted fixes are left out.</p>
        </div>
      </div>
    )
  }
  if (error) return <div className="notice" role="alert"><div><strong>The diff could not be loaded</strong>{error}</div></div>
  if (!diff) return <div className="panel"><div className="empty"><p>Loading the diff…</p></div></div>
  if (diff.files.length === 0) {
    return nothingFound
      ? <div className="panel"><div className="empty"><h2>Nothing was changed</h2><p>No waste was found, so the code is exactly as you gave it.</p></div></div>
      : <div className="panel"><div className="empty"><h2>No changes were kept</h2><p>Every fix was reverted or skipped, so there is nothing to apply.</p></div></div>
  }

  return (
    <>
      <p className="mono" style={{ fontSize: 12.5, color: 'var(--mute)', marginBottom: 12 }}>
        {diff.files.length} files · branch {diff.branch} · on {diff.base_commit.slice(0, 7)}
      </p>
      {diff.files.map((file) => (
        <div className="panel diff-file" key={file.path}>
          <header>
            {file.path}
            <span style={{ color: 'var(--green)' }}>+{file.additions}</span>
            <span style={{ color: 'var(--red)' }}>−{file.deletions}</span>
          </header>
          <pre>
            {file.patch.split('\n').filter((line, i, all) => i < all.length - 1 || line).slice(2).map((line, i) => (
              <span key={i} className={line.startsWith('@@') ? 'hunk' : line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : ''}>
                {line || ' '}
              </span>
            ))}
          </pre>
        </div>
      ))}
    </>
  )
}
