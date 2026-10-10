import { AnimatedNumber } from '../../components/AnimatedNumber'
import type { Job } from '../../lib/api'
import { pct, usd } from '../../lib/format'
import type { RunView } from '../../lib/useJob'

export function Kpis({ job, view }: { job: Job | null; view: RunView }) {
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
  const quality = latest?.quality_after ?? null
  const baseQuality = Object.values(view.verify)[0]?.quality_before ?? null

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
              ? `${view.completed.baseline.length} of 5 tasks run`
              : base !== null && now !== null && now < base
                ? <>was <span className="was">{usd(base)}</span></>
                : 'before any fix'}
          </div>
        </dd>
      </div>
      <div className="kpi">
        <dt>{after ? 'Lower' : 'Lower so far'}</dt>
        <dd>
          <div className={`value ${lower ? 'good' : ''}`}>{lower ? pct(lower) : '–'}</div>
          <div className="sub">
            {view.findings.length === 0 ? 'no fixes yet' : `${applied} kept${reverted ? ` · ${reverted} reverted` : ''}`}
          </div>
        </dd>
      </div>
      <div className="kpi">
        <dt>Answer quality</dt>
        <dd>
          <div className="value">{quality !== null ? quality.toFixed(2) : baseQuality !== null ? baseQuality.toFixed(2) : '–'}</div>
          <div className="sub">
            {quality !== null && baseQuality !== null ? `was ${baseQuality.toFixed(2)}` : 'scored after each fix'}
          </div>
        </dd>
      </div>
      <div className="kpi">
        <dt>Model calls</dt>
        <dd>
          <div className="value">{after ? after.llm_calls : (baseline?.llm_calls ?? view.calls.baseline.length)}</div>
          <div className="sub">{after && baseline ? `was ${baseline.llm_calls}` : 'across all tasks'}</div>
        </dd>
      </div>
    </dl>
  )
}
