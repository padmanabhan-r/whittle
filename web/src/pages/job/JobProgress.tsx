import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { usd } from '../../lib/format'
import type { RunView } from '../../lib/useJob'

const STAGES = ['Download', 'Install', 'Measure the baseline', 'Find the waste', 'Fix and check', 'Write the result'] as const

const HINT = [
  'The repository is being downloaded.',
  'The code is being installed in the sandbox. A large project can take a few minutes.',
  'Each task runs once through the recording proxy. Every model call is priced as it happens.',
  'The recorded calls are read for five kinds of waste, and each one is placed in the code.',
  'Each fix is written, the tasks are run again, and the fix is kept only if the run got cheaper and the answers held.',
  'The before and after are being compared.',
]

function stageOf(view: RunView): number {
  switch (view.state) {
    case 'queued':
    case 'cloning':
      return 0
    case 'installing':
      return 1
    case 'baseline':
      return 2
    case 'diagnosing':
    case 'awaiting_selection':
      return 3
    case 'reporting':
      return 5
    default:
      return 4
  }
}

/** A measured job that is still running says so: its stage, what it is doing this second, and for how long. */
export function JobProgress({ jobId, view }: { jobId: string; view: RunView }) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const started = Date.now()
    const id = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => window.clearInterval(id)
  }, [])

  const stage = stageOf(view)
  const waiting = view.state === 'awaiting_selection'
  const lastStep = [...view.steps].reverse().find((s) => s.kind !== 'tool_result')
  const lastLog = view.logs.length ? view.logs[view.logs.length - 1].line.split('\n')[0] : ''
  const runs = view.completed.baseline.length
  const calls = view.calls.baseline.length
  const checked = Object.keys(view.verify).length

  let now = lastStep?.text ?? lastLog ?? ''
  if (stage <= 1) now = lastLog || (stage === 0 ? 'Downloading the repository' : 'Installing')
  if (stage === 2) now = `${runs} ${runs === 1 ? 'task' : 'tasks'} run so far · ${calls} model ${calls === 1 ? 'call' : 'calls'} · ${usd(view.runningCost.baseline)}`
  if (stage === 4 && checked > 0 && !lastStep) now = `${checked} ${checked === 1 ? 'fix' : 'fixes'} checked so far`
  if (waiting) now = `${view.findings.length} ${view.findings.length === 1 ? 'finding' : 'findings'} ready. Nothing runs until you choose.`
  if (!now) now = 'Starting'
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

  return (
    <div className={`scan-progress${waiting ? ' waiting' : ''}`} role="status" aria-live="polite">
      <div className="head">
        <span className={`dot ${waiting ? '' : 'live'}`} aria-hidden="true" />
        <strong>{waiting ? 'Waiting for you' : 'Job in progress'}</strong>
        <span className="step">step {stage + 1} of {STAGES.length}: {waiting ? 'Choose the fixes' : STAGES[stage]}</span>
        {!waiting && <span className="clock mono" title="Time since this page opened">{clock}</span>}
      </div>
      <div className="bar" aria-hidden="true"><i style={{ width: `${((stage + 0.5) / STAGES.length) * 100}%` }} /></div>
      <ol className="stages">
        {STAGES.map((name, i) => (
          <li key={name} className={i < stage ? 'done' : i === stage ? 'now' : ''} aria-current={i === stage ? 'step' : undefined}>{name}</li>
        ))}
      </ol>
      <p className="now mono" title={now}>{now.slice(0, 140)}</p>
      <p className="hint">
        {waiting
          ? <>Pick the fixes to apply on the <Link to={`/app/jobs/${jobId}/findings`}>Findings</Link> page. Each one is then checked by a rerun.</>
          : <>{HINT[stage]} This page updates by itself.</>}
      </p>
    </div>
  )
}
