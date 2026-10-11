import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Warn } from '../../components/Icons'
import { api, ApiError } from '../../lib/api'
import type { Finding, Job } from '../../lib/api'
import { int, KIND_LABEL, PROVIDER_LABEL } from '../../lib/format'
import type { RunView } from '../../lib/useJob'

interface Props {
  job: Job | null
  view: RunView
  selected: string | null
  onSelect: (id: string | null) => void
}

const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 }

/** A scan's page: where the code calls a model, what that code wastes, and how to measure it for real. */
export function ScanSection({ job, view, selected, onSelect }: Props) {
  const working = !view.done
  const findings = [...view.findings].sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
  const files = new Set(view.callSites.map((c) => c.file)).size
  const filesScanned = job?.summary.files_scanned

  return (
    <>
      <dl className="kpis scan">
        <div className="kpi lead">
          <dt>Model call sites</dt>
          <dd className="value">{view.callSites.length || (working ? '…' : 0)}</dd>
          <dd className="sub">{files ? `in ${files} file${files === 1 ? '' : 's'}` : working ? 'looking' : 'none found'}</dd>
        </div>
        <div className="kpi">
          <dt>Source files read</dt>
          <dd className="value">{filesScanned != null ? int(filesScanned) : '…'}</dd>
          <dd className="sub">{job?.language && job.language !== 'other' ? `mostly ${job.language}` : 'any language'}</dd>
        </div>
        <div className="kpi">
          <dt>Findings</dt>
          <dd className="value">{findings.length || (working ? '…' : 0)}</dd>
          <dd className="sub">read from the code</dd>
        </div>
        <div className="kpi">
          <dt>Code run</dt>
          <dd className="value">None</dd>
          <dd className="sub">no key, no command</dd>
        </div>
      </dl>

      {job?.scan_summary && (
        <div className="notice scan-summary" role="status">
          <div>
            <strong>Where the model spend goes</strong>
            {job.scan_summary}
          </div>
        </div>
      )}

      <h2 className="section-title">Where this code calls a model</h2>
      <div className="panel">
        <div className="table-wrap">
          <table className="ledger">
            <thead><tr><th>Where</th><th>How</th><th>Provider</th><th>Model named nearby</th></tr></thead>
            <tbody>
              {view.callSites.length === 0 && (
                <tr><td colSpan={4}>{working ? 'Reading the source files…' : 'No model calls were found in this repository.'}</td></tr>
              )}
              {view.callSites.map((site) => (
                <tr key={`${site.file}:${site.line}`}>
                  <td className="mono">{site.file}:{site.line}</td>
                  <td>{site.via}</td>
                  <td>{PROVIDER_LABEL[site.provider] ?? site.provider}</td>
                  <td className="mono">{site.model ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <h2 className="section-title">
        What it wastes
        <span className="tag idle" title="A scan reads the code and runs nothing, so no saving is measured">read from the code · not measured</span>
      </h2>
      {findings.length === 0 && (
        <div className="panel empty">
          <h2>{working ? 'Reading the code' : 'Nothing to report'}</h2>
          <p>
            {working
              ? 'Whittle is reading each call site and following the prompt, the model choice and the retries back to where they are set.'
              : 'The code that calls a model already caches, caps and routes sensibly, or there is none.'}
          </p>
        </div>
      )}
      <div className="scan-findings">
        {findings.map((finding, index) => (
          <ScanFinding key={finding.id} n={index + 1} finding={finding} open={selected === finding.id}
            onToggle={() => onSelect(selected === finding.id ? null : finding.id)} />
        ))}
      </div>

      {job?.scan_good && job.scan_good.length > 0 && (
        <>
          <h2 className="section-title">What it already does well</h2>
          <ul className="panel scan-good">
            {job.scan_good.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </>
      )}

      {view.done && !view.error && job && <MeasureNext job={job} />}
    </>
  )
}

function ScanFinding({ n, finding, open, onToggle }: { n: number; finding: Finding; open: boolean; onToggle: () => void }) {
  const loc = finding.location
  return (
    <article className={`panel scan-finding ${finding.severity}`} aria-current={open ? 'true' : undefined}>
      <header>
        <span className="num">{n}</span>
        <div className="head">
          <h3>{finding.title}</h3>
          <div className="meta">
            <span className={`tag sev ${finding.severity}`}>{finding.severity}</span>
            <span className="kind mono">{KIND_LABEL[finding.kind] ?? finding.kind}</span>
            {loc && <span className="loc mono">{loc.file}:{loc.line_start}{loc.symbol ? ` · ${loc.symbol}` : ''}</span>}
          </div>
        </div>
      </header>
      <p>{finding.summary}</p>
      {finding.suggestion && <p className="suggest"><strong>Change</strong>{finding.suggestion}</p>}
      {finding.snippet && (
        <>
          <button className="btn code-toggle" type="button" onClick={onToggle} aria-expanded={open}>{open ? 'Hide the code' : 'Show the code'}</button>
          {open && (
            <pre className="snippet">
              {finding.snippet.split('\n').map((line, i) => (
                <span key={i}><i>{(loc?.line_start ?? 1) + i}</i>{line || ' '}{'\n'}</span>
              ))}
            </pre>
          )}
        </>
      )}
    </article>
  )
}

/** After a scan: measure the real cost. That needs a command to run the code once, and the owner's model key. */
function MeasureNext({ job }: { job: Job }) {
  const navigate = useNavigate()
  const proposed = job.proposed_run
  const [command, setCommand] = useState(proposed?.command ?? '')
  const [tasks, setTasks] = useState('')
  const [provider, setProvider] = useState<'anthropic' | 'openai'>('openai')
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const python = job.language === 'python'
  const takesInput = command.includes('{input}')

  async function submit(event: FormEvent) {
    event.preventDefault()
    const list = tasks.split('\n').map((t) => t.trim()).filter(Boolean)
    if (takesInput && list.length === 0) return setError('Add at least one task: an input the code should be run with.')
    setBusy(true)
    setError(null)
    try {
      const created = await api.createJob({
        source: job.source,
        mode: 'measure',
        run: { command: command.trim(), tasks: (list.length ? list : ['run']).slice(0, 10).map((input) => ({ input })) },
        model_key: { provider, key },
        monthly_runs: job.monthly_runs ?? undefined,
      })
      setKey('')
      navigate(`/app/jobs/${created.id}`)
    } catch (e) {
      setError((e as ApiError).message)
      setBusy(false)
    }
  }

  return (
    <>
      <h2 className="section-title">Measure it</h2>
      <p className="lede small">
        The scan shows where the spend goes. To put a dollar figure on it, Whittle runs the code in a locked sandbox with
        your model key, records every call, and can then fix the waste and prove the saving.
      </p>
      {!python && (
        <div className="notice" role="status">
          <Warn />
          <div>
            <strong>Measured runs work for Python today</strong>
            This repository is mostly {job.language === 'other' ? 'another language' : job.language}. The scan above is
            complete; running it in the sandbox is not supported yet.
          </div>
        </div>
      )}
      {error && <div className="notice" role="alert"><Warn /><div><strong>The run did not start</strong>{error}</div></div>}
      <form className="panel form-grid" onSubmit={submit}>
        <label className="wide">
          Command to run the code once
          <small>
            {proposed
              ? `Found by the scan: ${proposed.reason}`
              : 'The scan did not find a command that runs the model-calling code from a shell. Enter one if you know it.'}
          </small>
          <input className="field mono" required value={command} onChange={(e) => setCommand(e.target.value)} placeholder='python -m agent "{input}"' />
        </label>
        {proposed && proposed.needs.length > 0 && (
          <p className="wide needs">
            The code will not start without these environment variables, which the sandbox does not have:{' '}
            {proposed.needs.map((n) => <code key={n}>{n}</code>)}
          </p>
        )}
        <label className="wide">
          Tasks <small>One input per line, up to ten; each replaces {'{input}'} in the command.</small>
          <textarea className="field" rows={3} value={tasks} onChange={(e) => setTasks(e.target.value)} />
        </label>
        <label>
          Model provider
          <select className="pick" value={provider} onChange={(e) => setProvider(e.target.value as 'anthropic' | 'openai')}>
            <option value="openai">OpenAI compatible</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </label>
        <label>
          Your API key <small>Held in memory for the run only. Never stored, logged or shown again.</small>
          <input className="field mono" type="password" required autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
        </label>
        <div className="actions">
          <button className="btn primary" type="submit" disabled={busy || !python}>
            {busy ? 'Starting…' : <>Run and measure <ArrowRight /></>}
          </button>
          <span className="note" style={{ color: 'var(--mute)', fontSize: 13 }}>
            The code runs with no internet access. Only model calls leave the sandbox.
          </span>
        </div>
      </form>
    </>
  )
}
