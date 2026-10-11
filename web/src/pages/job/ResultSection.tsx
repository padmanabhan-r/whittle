import { useEffect, useState } from 'react'
import { External } from '../../components/Icons'
import { api } from '../../lib/api'
import type { Comparison, Finding, Job } from '../../lib/api'
import { int, pct, usd, usd2 } from '../../lib/format'

export function ResultSection({ jobId, done, findings, job }: { jobId: string; done: boolean; findings: Finding[]; job: Job | null }) {
  // A job that found nothing, or where no fix was tried, has no after run: that is a result, not an error.
  const noAfter = done && !!job && !job.summary.after
  const [data, setData] = useState<Comparison | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!done || noAfter) return
    api.comparison(jobId).then(setData).catch((e) => setError(e.message))
  }, [jobId, done, noAfter])

  if (!done) {
    return (
      <div className="panel">
        <div className="empty">
          <h2>The result comes after the final rerun</h2>
          <p>When every chosen fix has been checked, all tasks run once more and the before and after are compared here.</p>
        </div>
      </div>
    )
  }
  if (noAfter) return <NothingChanged job={job!} findings={findings} />
  if (error) return <div className="notice" role="alert"><div><strong>The comparison could not be loaded</strong>{error}</div></div>
  if (!data) return <div className="panel"><div className="empty"><p>Loading the comparison…</p></div></div>

  const maxCost = Math.max(...data.tasks.map((t) => t.baseline.cost_usd))
  const title = (id: string) => findings.find((f) => f.id === id)?.title ?? id
  const tokens = (t: Comparison['baseline']) => t.input_tokens + t.output_tokens + t.cache_read_tokens + t.cache_write_tokens

  return (
    <>
      <div className="verdict">
        <div className="big">
          <div className="label">Cost per run</div>
          <div className="figure">{pct(data.saving_pct)} lower</div>
          <div className="line">
            <s>{usd(data.baseline.cost_per_run_usd)}</s> → <mark className="hl">{usd(data.after.cost_per_run_usd)}</mark>
            {'  '}saving {usd(data.saving_usd_per_run)} on every run
          </div>
        </div>
        <dl className="side" style={{ margin: 0 }}>
          <div className="kpi">
            <dt>Answer quality · {data.quality.evaluator}</dt>
            <dd>
              <div className="value">{data.quality.baseline_score.toFixed(2)} → {data.quality.after_score.toFixed(2)}</div>
              <div className="sub">
                {data.quality.passed ? 'Held' : 'Fell'} against a threshold of {data.quality.threshold.toFixed(2)}
              </div>
            </dd>
          </div>
          {data.projection && (
            <div className="kpi">
              <dt>At {int(data.projection.monthly_runs)} runs a month</dt>
              <dd>
                <div className="value good">{usd2(data.projection.saving_monthly_usd)} saved</div>
                <div className="sub">
                  <span className="was">{usd2(data.projection.baseline_monthly_usd)}</span> → {usd2(data.projection.after_monthly_usd)} a month
                </div>
              </dd>
            </div>
          )}
        </dl>
      </div>

      <h2 className="section-title">Where the saving came from</h2>
      <div className="panel">
        <div className="table-wrap">
          <table className="ledger">
            <thead><tr><th>Fix</th><th>Status</th><th className="r">Saved per run</th><th>Note</th></tr></thead>
            <tbody>
              {data.by_finding.map((row) => (
                <tr key={row.finding_id} className={row.status === 'reverted' ? 'struck' : ''}>
                  <td className="wrap" style={{ fontWeight: 600 }}>{title(row.finding_id)}</td>
                  <td style={{ textDecoration: 'none' }}>
                    <span className={`tag ${row.status === 'applied' ? 'ok' : row.status === 'reverted' ? 'bad' : 'idle'}`}>
                      {row.status === 'applied' ? 'kept' : row.status === 'skipped' ? 'not selected' : row.status}
                    </span>
                  </td>
                  <td className="r">{row.saving_usd_per_run ? `−${row.saving_usd_per_run.toFixed(4)}` : '0.0000'}</td>
                  <td className="why">{row.reason ?? ''}</td>
                </tr>
              ))}
              <tr className="total">
                <td colSpan={2}>TOTAL SAVED PER RUN</td>
                <td className="r"><mark className="hl">−{data.saving_usd_per_run.toFixed(4)}</mark></td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <h2 className="section-title">Task by task</h2>
      <div className="panel">
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr>
                <th>Task</th><th>Before and after</th><th className="r">Before</th><th className="r">After</th>
                <th className="r">Calls</th><th>Passed</th><th>Traces</th>
              </tr>
            </thead>
            <tbody>
              {data.tasks.map((task) => (
                <tr key={task.task_id}>
                  <td className="wrap" style={{ maxWidth: 340 }}>{task.input_preview}</td>
                  <td>
                    <div className="bar-pair" aria-hidden="true">
                      <i style={{ width: `${(task.baseline.cost_usd / maxCost) * 100}%` }} />
                      <i className="after" style={{ width: `${(task.after.cost_usd / maxCost) * 100}%` }} />
                    </div>
                  </td>
                  <td className="r">{task.baseline.cost_usd.toFixed(4)}</td>
                  <td className="r">{task.after.cost_usd.toFixed(4)}</td>
                  <td className="r">{task.baseline.llm_calls} → {task.after.llm_calls}</td>
                  <td>{task.after.passed ? 'yes' : 'no'}</td>
                  <td>
                    <a href={task.baseline.trace_url} target="_blank" rel="noreferrer">before <External /></a>{' '}
                    <a href={task.after.trace_url} target="_blank" rel="noreferrer">after <External /></a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <h2 className="section-title">Totals over all tasks</h2>
      <div className="panel">
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr>
                <th>Run</th><th className="r">Model calls</th><th className="r">Tool calls</th><th className="r">Uncached input</th>
                <th className="r">Cache read</th><th className="r">Output</th><th className="r">All tokens</th><th className="r">USD</th>
              </tr>
            </thead>
            <tbody>
              {([['Before', data.baseline], ['After', data.after]] as const).map(([name, t]) => (
                <tr key={name}>
                  <td>{name}</td><td className="r">{t.llm_calls}</td><td className="r">{t.tool_calls}</td>
                  <td className="r">{int(t.input_tokens)}</td><td className="r">{int(t.cache_read_tokens)}</td>
                  <td className="r">{int(t.output_tokens)}</td><td className="r">{int(tokens(t))}</td>
                  <td className="r">{t.cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}

const CHECKS = [
  'a prompt prefix that changes on every call, so it is never cached',
  'the same tool called twice with the same input',
  'context that grows on every turn',
  'a large model used for a small step',
  'a failed call retried unchanged',
]

/** The job measured the code and changed nothing. Say what was measured and why nothing was changed. */
function NothingChanged({ job, findings }: { job: Job; findings: Finding[] }) {
  const base = job.summary.baseline
  const calls = base?.llm_calls ?? 0
  const runs = base?.runs ?? 0
  const found = findings.length
  return (
    <div className="panel">
      <div className="empty">
        <h2>{found === 0 ? 'Nothing worth fixing' : 'No fix was applied'}</h2>
        {base && (
          <p>
            Whittle ran {runs} {runs === 1 ? 'task' : 'tasks'} and recorded {calls} model {calls === 1 ? 'call' : 'calls'}:{' '}
            <strong>{usd(base.cost_per_run_usd)} a run</strong>, {int(base.input_tokens + base.cache_read_tokens + base.cache_write_tokens)} tokens in and {int(base.output_tokens)} out.
          </p>
        )}
        {found === 0 ? (
          <>
            <p>None of the five checks found waste it could prove in those calls:</p>
            <ul className="checks">{CHECKS.map((c) => <li key={c}>{c}</li>)}</ul>
            <p>
              {calls <= 2
                ? `With only ${calls} model ${calls === 1 ? 'call' : 'calls'} there is little to compare. Waste shows up across repeated calls, so try tasks that make the agent loop or use its tools, or add more tasks.`
                : 'The code was left exactly as you gave it. Every recorded call is on the Calls page.'}
            </p>
          </>
        ) : (
          <p>
            Whittle found {found} {found === 1 ? 'thing' : 'things'} to fix, and none was applied, so there is no before and after to compare. They are listed on the Findings page.
          </p>
        )}
      </div>
    </div>
  )
}
