import { AnimatedNumber } from '../../components/AnimatedNumber'
import type { Job } from '../../lib/api'
import { pct, usd } from '../../lib/format'
import type { RunView } from '../../lib/useJob'

export function Kpis({ job, view, recorded = false }: { job: Job | null; view: RunView; recorded?: boolean }) {
  const possible = view.findings.reduce((s, f) => s + f.estimated_saving_usd_per_run, 0)
  const baseline = job?.summary.baseline ?? null
  const after = job?.summary.after ?? null
  const base = baseline?.cost_per_run_usd ?? null

  // The newest kept fix gives the running figures between the baseline and the final rerun.
  const kept = view.findings
    .filter((f) => f.status === 'applied' && view.verify[f.id])
    .map((f) => view.verify[f.id])
  const latest = kept[kept.length - 1]
  const now = after?.cost_per_run_usd ?? latest?.cost_per_run_after_usd ?? base
  const lower = base && now !== null && now < base ? ((base - now) / base) * 100 : null
  // While fixes are checked this is the newest kept fix's score; once the job is done it is the
  // final rerun's, the same figure the result page gives.
  const quality = job?.summary.quality_after ?? latest?.quality_after ?? null
  const baseQuality = job?.summary.quality_baseline ?? Object.values(view.verify)[0]?.quality_before ?? null

  const inBaseline = !baseline
  const applied = view.findings.filter((f) => f.status === 'applied').length
  const reverted = view.findings.filter((f) => f.status === 'reverted').length

  return (
    <dl className="kpis">
      <div className="kpi lead">
        <dt>{inBaseline ? 'Baseline spend so far' : 'Cost per run'}</dt>
        <dd>
          <div className="value">
            <AnimatedNumber value={inBaseline ? view.runningCost.baseline : (now ?? 0)} format={(n) => usd(n)} />
          </div>
          <div className="sub">
            {inBaseline
              ? `${view.completed.baseline.length} ${view.completed.baseline.length === 1 ? 'task' : 'tasks'} run so far`
              : base !== null && now !== null && now < base
                ? <>was <span className="was">{usd(base)}</span></>
                : recorded ? `over ${baseline?.runs ?? 1} recorded run${baseline?.runs === 1 ? '' : 's'}` : 'before any fix'}
          </div>
        </dd>
      </div>
      {recorded && (
        <>
          <div className="kpi">
            <dt>Could be lower by</dt>
            <dd>
              <div className={`value ${possible > 0 ? 'good' : ''}`}>{base && possible > 0 ? pct(Math.min(100, (possible / base) * 100)) : '–'}</div>
              <div className="sub">{possible > 0 ? `about ${usd(possible)} a run, estimated` : 'no repeated waste found'}</div>
            </dd>
          </div>
          <div className="kpi">
            <dt>Recorded total</dt>
            <dd>
              <div className="value">{baseline ? usd(baseline.cost_usd) : '–'}</div>
              <div className="sub">{baseline ? `${(baseline.input_tokens + baseline.cache_read_tokens + baseline.cache_write_tokens).toLocaleString('en-US')} tokens in` : ''}</div>
            </dd>
          </div>
        </>
      )}
      {!recorded && <div className="kpi">
        <dt>{after ? 'Lower' : 'Lower so far'}</dt>
        <dd>
          <div className={`value ${lower ? 'good' : ''}`}>{lower ? pct(lower) : '–'}</div>
          <div className="sub">
            {view.findings.length === 0 ? 'no fixes yet' : `${applied} kept${reverted ? ` · ${reverted} reverted` : ''}`}
          </div>
        </dd>
      </div>}
      {!recorded && <div className="kpi">
        <dt>Answer quality</dt>
        <dd>
          <div className="value">{quality !== null ? quality.toFixed(2) : baseQuality !== null ? baseQuality.toFixed(2) : '–'}</div>
          <div className="sub">
            {quality !== null && baseQuality !== null ? `was ${baseQuality.toFixed(2)}` : 'scored after each fix'}
          </div>
        </dd>
      </div>}
      <div className="kpi">
        <dt>Model calls</dt>
        <dd>
          <div className="value">{after ? after.llm_calls : (baseline?.llm_calls ?? view.calls.baseline.length)}</div>
          <div className="sub">{after && baseline ? `was ${baseline.llm_calls}` : recorded ? 'across all runs' : 'across all tasks'}</div>
        </dd>
      </div>
    </dl>
  )
}
