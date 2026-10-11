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

  // The longest bar is the dearest run on either side: an after run can cost more than its baseline.
  const maxCost = Math.max(...data.tasks.flatMap((t) => [t.baseline.cost_usd, t.after.cost_usd]), 1e-9)
  const title = (id: string) => findings.find((f) => f.id === id)?.title ?? id
  const tokens = (t: Comparison['baseline']) => t.input_tokens + t.output_tokens + t.cache_read_tokens + t.cache_write_tokens
  // Three different endings, and only one of them is a saving.
  const kept = data.by_finding.filter((r) => r.status === 'applied').length
  const tried = data.by_finding.filter((r) => r.status === 'applied' || r.status === 'reverted').length
  const unchanged = kept === 0 // every fix was reverted or skipped: both runs are of the same code
  const worse = !unchanged && data.saving_usd_per_run <= 0
  const unsafe = !unchanged && !worse && !data.quality.passed // cheaper, but the answers did not hold
  const gap = pct(Math.abs(data.saving_pct))
  const more = Math.abs(data.saving_usd_per_run)
  const few = data.tasks.length < 3

  return (
    <>
      <div className="verdict">
        {unchanged ? (
          <div className="big none">
            <div className="label">Result</div>
            <div className="figure">No fix was kept</div>
            <div className="line">
              Your code is unchanged. {tried === 0 ? 'No fix was tried.' : `${tried} ${tried === 1 ? 'fix was' : 'fixes were'} tried and reverted.`} There is no saving to report.
            </div>
          </div>
        ) : worse ? (
          <div className="big worse">
            <div className="label">Cost per run</div>
            <div className="figure">{gap} higher</div>
            <div className="line">
              {usd(data.baseline.cost_per_run_usd)} → <mark className="hl">{usd(data.after.cost_per_run_usd)}</mark>
              {'  '}costing {usd(more)} more on every run. Do not apply this patch.
            </div>
          </div>
        ) : unsafe ? (
          <div className="big caution">
            <div className="label">Cheaper, but not shown to be safe</div>
            <div className="figure">{pct(data.saving_pct)} lower</div>
            <div className="line">
              {usd(data.baseline.cost_per_run_usd)} → {usd(data.after.cost_per_run_usd)} a run, but answer quality fell from{' '}
              {data.quality.baseline_score.toFixed(2)} to {data.quality.after_score.toFixed(2)}, under the bar of {data.quality.threshold.toFixed(2)}.
              A run can get cheaper by doing less. Do not apply this patch without checking the answers. No pull request will be opened for it.
            </div>
          </div>
        ) : (
          <div className="big">
            <div className="label">Cost per run</div>
            <div className="figure">{pct(data.saving_pct)} lower</div>
            <div className="line">
              <s>{usd(data.baseline.cost_per_run_usd)}</s> → <mark className="hl">{usd(data.after.cost_per_run_usd)}</mark>
              {'  '}saving {usd(data.saving_usd_per_run)} on every run
            </div>
          </div>
        )}
        <dl className="side" style={{ margin: 0 }}>
          {unchanged && (
            <div className="kpi">
              <dt>The same code, run twice</dt>
              <dd>
                <div className="value">{usd(data.baseline.cost_per_run_usd)} and {usd(data.after.cost_per_run_usd)}</div>
                <div className="sub">
                  {gap} apart with no change to the code. That is the variation between two runs, not a result.
                </div>
              </dd>
            </div>
          )}
          <div className="kpi">
            <dt>Answer quality · {data.quality.evaluator}</dt>
            <dd>
              <div className="value">{data.quality.baseline_score.toFixed(2)} → {data.quality.after_score.toFixed(2)}</div>
              <div className="sub">
                {unchanged && !data.quality.passed
                  ? `The unchanged code scored under the ${data.quality.threshold.toFixed(2)} bar against its own first answers`
                  : `${data.quality.passed ? 'Held' : 'Fell'} against a threshold of ${data.quality.threshold.toFixed(2)}`}
              </div>
            </dd>
          </div>
          {data.projection && !unchanged && worse && (
            <div className="kpi">
              <dt>At {int(data.projection.monthly_runs)} runs a month</dt>
              <dd>
                <div className="value bad">{usd2(Math.abs(data.projection.saving_monthly_usd))} more</div>
                <div className="sub">{usd2(data.projection.baseline_monthly_usd)} → {usd2(data.projection.after_monthly_usd)} a month</div>
              </dd>
            </div>
          )}
          {data.projection && !unchanged && !worse && !unsafe && (
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

      {unsafe && (
        <div className="notice recover" role="note">
          <div>
            <strong>Why this is not counted as a saving</strong>
            <p>
              Each kept fix passed its own check, but the final run of all tasks did not: its answers scored{' '}
              {data.quality.after_score.toFixed(2)}. Whittle counts a saving only when the answers hold.
            </p>
            <p>
              {data.quality.evaluator === 'answer-judge'
                ? `These answers were scored by a model judge against the first run's answers${few ? `, on ${data.tasks.length} ${data.tasks.length === 1 ? 'task' : 'tasks'}` : ''}. That scoring varies from run to run. Run the job again with three to five tasks whose answers the repository states, so they are scored against facts.`
                : 'Open the traces below and compare the answers before and after, task by task.'}
            </p>
          </div>
        </div>
      )}

      {unchanged && tried > 0 && (
        <div className="notice recover" role="note">
          <div>
            <strong>Why nothing was kept</strong>
            {!data.quality.passed ? (
              <p>
                Each fix was reverted because its answers scored under the bar. But the last run used the same code as the first and
                still scored {data.quality.after_score.toFixed(2)}, so the scoring could not tell a real loss from ordinary variation
                in this agent's answers. The fixes were not shown to be bad; they were not measured well enough to keep.
              </p>
            ) : (
              <p>Each fix was reverted after its rerun, for the reason given beside it below. Whittle keeps a fix only when the run got cheaper and the answers held.</p>
            )}
            <p>
              {few
                ? `This job ran ${data.tasks.length} ${data.tasks.length === 1 ? 'task' : 'tasks'}. Run it again with three to five tasks that have a definite answer, so one unusual answer does not decide the result.`
                : 'Run it again with tasks that have a definite answer, so the scoring has something firm to compare.'}
            </p>
          </div>
        </div>
      )}

      <h2 className="section-title">{unchanged ? 'What was tried' : worse || unsafe ? 'What each fix did' : 'Where the saving came from'}</h2>
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
              {!unchanged && (
                <tr className="total">
                  <td colSpan={2}>{worse ? 'TOTAL ADDED PER RUN' : 'TOTAL SAVED PER RUN'}</td>
                  <td className="r"><mark className="hl">{worse ? '+' : '−'}{more.toFixed(4)}</mark></td>
                  <td />
                </tr>
              )}
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
                <th>Task</th><th>{unchanged ? 'First and second run' : 'Before and after'}</th><th className="r">{unchanged ? 'First' : 'Before'}</th><th className="r">{unchanged ? 'Second' : 'After'}</th>
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
              {([[unchanged ? 'First run' : 'Before', data.baseline], [unchanged ? 'Second run' : 'After', data.after]] as const).map(([name, t]) => (
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
