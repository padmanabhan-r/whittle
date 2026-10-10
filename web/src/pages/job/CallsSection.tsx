import { Fragment, useMemo, useState } from 'react'
import type { Phase } from '../../lib/api'
import { int, KIND_LABEL, usd } from '../../lib/format'
import type { RunView } from '../../lib/useJob'

export function CallsSection({ view }: { view: RunView }) {
  const [phase, setPhase] = useState<Phase>('baseline')
  const [task, setTask] = useState('all')
  const [onlyFlagged, setOnlyFlagged] = useState(false)

  // Which finding marks each baseline call. A removed call outranks a reduced one.
  const marks = useMemo(() => {
    const map = new Map<string, { label: string; struck: boolean; live: boolean }>()
    for (const finding of view.findings) {
      const live = finding.status === 'applied'
      const off = finding.status === 'reverted' || finding.status === 'skipped'
      for (const ref of finding.calls) {
        const key = `${ref.task_id}:${ref.call_index}`
        const struck = ref.effect === 'removed' && live
        const label = `${KIND_LABEL[finding.kind] ?? finding.kind}${off ? `, ${finding.status}` : ''}`
        const existing = map.get(key)
        if (!existing || (struck && !existing.struck)) map.set(key, { label, struck, live })
        else if (existing && !existing.label.includes(label)) existing.label += `; ${label}`
      }
    }
    return map
  }, [view.findings])

  const calls = view.calls[phase]
  const tasks = [...new Set(view.calls.baseline.map((c) => c.task_id))]
  const shown = calls.filter((c) => {
    if (task !== 'all' && c.task_id !== task) return false
    if (onlyFlagged && phase === 'baseline' && !marks.has(`${c.task_id}:${c.call_index}`)) return false
    return true
  })
  const total = shown.reduce((sum, c) => sum + c.cost_usd, 0)
  const flagged = phase === 'baseline' ? calls.filter((c) => marks.has(`${c.task_id}:${c.call_index}`)).length : 0
  const newest = calls[calls.length - 1]?.seq

  return (
    <div className="panel">
      <div className="toolbar">
        <div className="seg" role="group" aria-label="Run">
          <button aria-pressed={phase === 'baseline'} onClick={() => setPhase('baseline')}>Baseline</button>
          <button aria-pressed={phase === 'after'} onClick={() => setPhase('after')} disabled={view.calls.after.length === 0}>After</button>
        </div>
        <select className="pick" aria-label="Task" value={task} onChange={(e) => setTask(e.target.value)}>
          <option value="all">All tasks</option>
          {tasks.map((t) => <option key={t} value={t}>{t.replace('task-', 'Task ')}</option>)}
        </select>
        {phase === 'baseline' && view.findings.length > 0 && (
          <label className="check">
            <input type="checkbox" checked={onlyFlagged} onChange={(e) => setOnlyFlagged(e.target.checked)} />
            Only wasted calls
          </label>
        )}
        <span className="spacer" />
        <span className="note">
          {calls.length} calls{flagged ? ` · ${flagged} marked by a finding` : ''}
        </span>
      </div>
      {calls.length === 0 ? (
        <div className="empty">
          <h2>{phase === 'baseline' ? 'Waiting for the first model call' : 'No rerun yet'}</h2>
          <p>
            {phase === 'baseline'
              ? 'Each call the agent makes is recorded here as it happens, with its tokens and its price.'
              : 'Once fixes are kept, every task runs again and its calls are listed here.'}
          </p>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr>
                <th>#</th><th>Model</th><th className="r">Input</th><th className="r" title="Tokens read from the cache">Cached</th>
                <th className="r" title="Tokens written to the cache">Written</th><th className="r">Output</th>
                <th className="r">USD</th><th>Finding</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((call, i) => {
                const mark = phase === 'baseline' ? marks.get(`${call.task_id}:${call.call_index}`) : undefined
                const first = i === 0 || shown[i - 1].task_id !== call.task_id
                const done = view.completed[phase].find((r) => r.task_id === call.task_id)
                const row = [mark?.struck ? 'struck' : mark?.live ? 'reduced' : mark ? 'off' : '', call.seq === newest && !view.done ? 'fresh' : '']
                return (
                  <Fragment key={call.seq}>
                    {first && (
                      <tr className="group">
                        <td colSpan={8}>
                          {call.task_id.replace('task-', 'Task ')}
                          {done && <> · {usd(done.cost_usd)} · <a href={done.trace_url} target="_blank" rel="noreferrer">trace</a></>}
                        </td>
                      </tr>
                    )}
                    <tr className={row.join(' ')}>
                      <td>{String(call.call_index).padStart(2, '0')}</td>
                      <td>{call.model}</td>
                      <td className="r">{int(call.input_tokens)}</td>
                      <td className="r">{call.cache_read_tokens ? int(call.cache_read_tokens) : '–'}</td>
                      <td className="r">{call.cache_write_tokens ? int(call.cache_write_tokens) : '–'}</td>
                      <td className="r">{int(call.output_tokens)}</td>
                      <td className="r">{call.cost_usd.toFixed(4)}</td>
                      <td className="why">{mark?.label ?? ''}</td>
                    </tr>
                  </Fragment>
                )
              })}
              <tr className="total">
                <td colSpan={6}>TOTAL{task !== 'all' || onlyFlagged ? ' (shown)' : ''}</td>
                <td className="r"><mark className="hl">{total.toFixed(4)}</mark></td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
