import { useEffect, useState } from 'react'
import { api, ApiError } from '../../lib/api'
import type { Finding } from '../../lib/api'
import { KIND_LABEL, pct, usd } from '../../lib/format'
import type { RunView } from '../../lib/useJob'

export function statusTag(finding: Finding, live: boolean) {
  switch (finding.status) {
    case 'applied': return <span className="tag ok">kept</span>
    case 'reverted': return <span className="tag bad">reverted</span>
    case 'skipped': return <span className="tag idle">not selected</span>
    case 'selected': return live ? <span className="tag live">fixing…</span> : <span className="tag idle">queued</span>
    default: return <span className="tag idle">proposed</span>
  }
}

interface Props {
  jobId: string
  view: RunView
  selected: string | null
  onSelect: (id: string) => void
  /** The calls came from the command-line tool: there is no code here to fix. */
  recorded?: boolean
  /** The code came with the recording: the fix is started and rerun from the owner's terminal. */
  remote?: boolean
}

export function FindingsSection({ jobId, view, selected, onSelect, recorded = false, remote = false }: Props) {
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const canPick = view.state === 'awaiting_selection' && !remote

  // Start with everything ticked: fixing all and letting the checks decide is the common case.
  useEffect(() => {
    if (canPick) setPicked(new Set(view.findings.map((f) => f.id)))
  }, [canPick, view.findings.length])

  const liveId = view.steps[view.steps.length - 1]?.finding_id
  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  async function fix() {
    setSending(true)
    setError(null)
    try {
      await api.fix(jobId, [...picked])
    } catch (e) {
      setError((e as ApiError).message)
    } finally {
      setSending(false)
    }
  }

  if (view.findings.length === 0) {
    return (
      <div className="panel">
        <div className="empty">
          <h2>{recorded && view.done ? 'No repeated waste in this recording' : view.state === 'diagnosing' ? 'Reading the traces' : 'No findings yet'}</h2>
          <p>
            {recorded
              ? 'Whittle read every recorded call for prompts that never hit the cache, repeated requests, duplicate tool calls, oversized models and growing context, and found none worth fixing. Recording several runs shows waste that repeats between them.'
              : 'After the baseline, Whittle reads every traced call and lists the waste it can prove, with the evidence and the place in the code. You then choose what to fix.'}
          </p>
        </div>
      </div>
    )
  }

  const estimate = view.findings.filter((f) => picked.has(f.id)).reduce((s, f) => s + f.estimated_saving_usd_per_run, 0)

  return (
    <div className="panel">
      <div className="toolbar">
        {canPick ? (
          <>
            <button className="btn primary" disabled={picked.size === 0 || sending} onClick={fix}>
              {sending ? 'Starting…' : `Fix ${picked.size} selected`}
            </button>
            <span className="note">
              Each fix is rerun and scored. One that lowers answer quality is reverted.
            </span>
          </>
        ) : (
          <span className="note">
            {recorded
              ? 'Read from the calls recorded on your machine. Whittle holds no code for this recording, so nothing was changed. To fix these and prove each fix there, run whittle fix.'
              : remote && view.state === 'awaiting_selection'
              ? 'The fix is started from your terminal by whittle fix. Each fix is rerun on your machine and scored.'
              : view.done ? 'Final status of each finding.' : 'Fixes are being applied one at a time.'}
          </span>
        )}
        <span className="spacer" />
        {canPick && <span className="note mono">up to {usd(estimate)} per run, if all hold</span>}
      </div>
      {error && <p className="error-text" style={{ padding: '10px 14px' }}>{error}</p>}
      <div className="table-wrap">
        <table className="ledger">
          <thead>
            <tr>
              {canPick && <th><span className="visually-hidden">Fix</span></th>}
              <th>#</th><th>Finding</th><th>Kind</th><th className="r">Est. per run</th>
              <th className="r">Share</th>{!recorded && <th>Status</th>}
            </tr>
          </thead>
          <tbody>
            {view.findings.map((finding, i) => (
              <tr key={finding.id} className="clickable" aria-selected={selected === finding.id}
                onClick={() => onSelect(finding.id)}>
                {canPick && (
                  <td onClick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={picked.has(finding.id)} onChange={() => toggle(finding.id)}
                      aria-label={`Fix: ${finding.title}`} />
                  </td>
                )}
                <td>
                  <span className={`badge-n ${finding.status === 'reverted' ? 'bad' : liveId === finding.id && !view.done ? 'live' : ''}`}>
                    {i + 1}
                  </span>
                </td>
                <td className="wrap">
                  <button style={{ all: 'unset', cursor: 'pointer', fontWeight: 600 }} onClick={() => onSelect(finding.id)}>
                    {finding.title}
                  </button>
                  {finding.location && (
                    <span className="loc">{finding.location.file}:{finding.location.line_start}</span>
                  )}
                </td>
                <td>{KIND_LABEL[finding.kind] ?? finding.kind}</td>
                <td className="r">−{finding.estimated_saving_usd_per_run.toFixed(4)}</td>
                <td className="r">{pct(finding.estimated_saving_pct)}</td>
                {!recorded && <td>{statusTag(finding, liveId === finding.id && !view.done)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
