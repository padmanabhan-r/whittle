import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Warn } from '../../components/Icons'
import { api, ApiError } from '../../lib/api'
import type { Finding, Job } from '../../lib/api'
import { int, keyMismatch, KIND_LABEL, PROVIDER_LABEL } from '../../lib/format'
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
      {working && !view.error && <ScanProgress view={view} />}
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
          <dd className="value">{working ? '…' : job?.proposed_run?.verified ? 'Dry run' : 'None'}</dd>
          <dd className="sub">{working ? 'finding how to run it' : job?.proposed_run?.verified ? 'once in the sandbox, no key' : 'no key, no command'}</dd>
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
        <span className="tag idle" title="A scan reads the code. Its one dry run in the sandbox reaches no model, so no cost or saving is measured">read from the code · not measured</span>
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

      {/* The job record is refetched when the stream ends; wait for it, so the form opens with the scan's command in it. */}
      {view.done && !view.error && job && job.state === 'done' && <MeasureNext key={job.proposed_run?.command ?? 'none'} job={job} />}
    </>
  )
}

const STAGES = ['Clone', 'Find the model calls', 'Read the code', 'Work out how to run it', 'Try it in the sandbox'] as const

/** Which stage a running scan is in, read from the events so far. */
function scanStage(view: RunView): number {
  if (view.state === 'queued' || view.state === 'cloning') return 0
  const tried = view.steps.some((s) => s.tool === 'sandbox.try') || view.logs.some((l) => l.phase === 'install')
  if (tried) return 4
  if (view.steps.some((s) => s.tool === 'repo.write_file')) return 3
  // the agent's own reading starts after the call sites and their importers are listed
  const reading = view.steps.some((s) => s.tool === 'repo.read_file' || s.tool === 'repo.grep' || s.tool === 'entire.graph_search')
  return reading || view.findings.length > 0 ? 2 : 1
}

/** A scan that is still running says so: its stage, what it is doing this second, and for how long. */
function ScanProgress({ view }: { view: RunView }) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const started = Date.now()
    const id = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000)
    return () => window.clearInterval(id)
  }, [])
  const stage = scanStage(view)
  const last = [...view.steps].reverse().find((s) => s.kind !== 'tool_result')
  const log = view.logs.length ? view.logs[view.logs.length - 1].line.split('\n')[0] : ''
  const now = stage === 4 && log ? log : last?.text ?? 'Starting'
  const clock = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
  return (
    <div className="scan-progress" role="status" aria-live="polite">
      <div className="head">
        <span className="dot live" aria-hidden="true" />
        <strong>Scan in progress</strong>
        <span className="step">step {stage + 1} of {STAGES.length}: {STAGES[stage]}</span>
        <span className="clock mono" title="Time since this page opened">{clock}</span>
      </div>
      <div className="bar" aria-hidden="true"><i style={{ width: `${((stage + 0.5) / STAGES.length) * 100}%` }} /></div>
      <ol className="stages">
        {STAGES.map((name, i) => (
          <li key={name} className={i < stage ? 'done' : i === stage ? 'now' : ''} aria-current={i === stage ? 'step' : undefined}>{name}</li>
        ))}
      </ol>
      <p className="now mono" title={now}>{now.slice(0, 140)}</p>
      <p className="hint">A scan usually takes one to three minutes. This page updates by itself; the result appears below when it finishes.</p>
    </div>
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
  const [workdir, setWorkdir] = useState(proposed?.workdir ?? '')
  const [envText, setEnvText] = useState((proposed?.needs ?? []).filter((n) => !/API_KEY$|_BASE_URL$/.test(n)).map((n) => `${n}=`).join('\n'))
  const [tasks, setTasks] = useState((proposed?.examples ?? []).join('\n'))
  const [provider, setProvider] = useState<'anthropic' | 'openai'>(proposed?.provider ?? 'openai')
  const keyEnv = proposed?.key_env ?? (provider === 'anthropic' ? 'ANTHROPIC_API_KEY' : 'OPENAI_API_KEY')
  const harness = Object.keys(proposed?.files ?? {})
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const runnable = job.language === 'python' || job.language === 'typescript' || job.language === 'javascript'
  const takesInput = command.includes('{input}')

  async function submit(event: FormEvent) {
    event.preventDefault()
    const list = tasks.split('\n').map((t) => t.trim()).filter(Boolean)
    if (takesInput && list.length === 0) return setError('Add at least one task: an input the code should be run with.')
    const mismatch = keyMismatch(provider, key)
    if (mismatch) return setError(mismatch)
    const env: Record<string, string> = {}
    for (const line of envText.split('\n')) {
      const at = line.indexOf('=')
      if (at > 0 && line.slice(at + 1).trim()) env[line.slice(0, at).trim()] = line.slice(at + 1).trim()
    }
    setBusy(true)
    setError(null)
    try {
      const created = await api.createJob({
        source: job.source,
        mode: 'measure',
        run: { command: command.trim(), tasks: (list.length ? list : ['run']).slice(0, 10).map((input) => ({ input })), workdir: workdir.trim() || null, env, files: proposed?.files ?? {} },
        model_key: { provider, key },
        monthly_runs: job.monthly_runs ?? undefined,
      })
      setKey('')
      setEnvText('')
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
      {!runnable && (
        <div className="notice" role="status">
          <Warn />
          <div>
            <strong>The sandbox runs Python, JavaScript and TypeScript</strong>
            This code is mostly another language. The scan above is complete; running it is not supported yet.
          </div>
        </div>
      )}
      {error && <div className="notice" role="alert"><Warn /><div><strong>The run did not start</strong>{error}</div></div>}
      <form className="panel form-grid" onSubmit={submit}>
        <label className="wide">
          Command to run the code once
          <small>
            {proposed
              ? `${proposed.reason} ${proposed.verified ? 'Verified: ' : 'Not confirmed: '}${proposed.check ?? ''}`
              : 'The scan did not arrive at a command that runs the model-calling code. Enter one if you know it.'}
          </small>
          <input className="field mono" required value={command} onChange={(e) => setCommand(e.target.value)} placeholder='python -m agent "{input}"' />
        </label>
        <label>
          Folder to run from <small>Inside the repository. Leave empty for the root.</small>
          <input className="field mono" value={workdir} onChange={(e) => setWorkdir(e.target.value)} placeholder="services/agent" />
        </label>
        <label>
          Other environment variables <small>One NAME=value per line. Held in memory for the run only.</small>
          <textarea className="field mono" rows={2} value={envText} onChange={(e) => setEnvText(e.target.value)} placeholder="FEATURE_FLAG=on" />
        </label>
        {harness.length > 0 && (
          <p className="wide needs">
            The repository has no shell entry point that reaches the model, so Whittle wrote one: {harness.map((f) => <code key={f}>{f}</code>)}
            It is sent with the run and never appears in the diff or a pull request.
          </p>
        )}
        {proposed && proposed.needs.length > 0 && (
          <p className="wide needs">
            The scan found that the code reads these: {proposed.needs.map((n) => <code key={n}>{n}</code>)}
            The sandbox has no internet access, so a variable that points at a database or another service will not reach it.
          </p>
        )}
        <label className="wide">
          Tasks <small>One input per line, up to ten; each replaces {'{input}'} in the command.</small>
          <textarea className="field" rows={3} value={tasks} onChange={(e) => setTasks(e.target.value)} />
        </label>
        <label>
          Model provider
          {proposed?.provider && <small>{proposed.verified ? 'The code called this provider when the scan tried it.' : 'What the call sites show.'}</small>}
          <select className="pick" value={provider} onChange={(e) => setProvider(e.target.value as 'anthropic' | 'openai')}>
            <option value="openai">OpenAI compatible</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </label>
        <label>
          <span>Your <code>{keyEnv}</code></span> <small>{provider === 'anthropic' ? 'An Anthropic key.' : 'An OpenAI or OpenAI-compatible key, not an Anthropic one.'} The variable this code reads its key from. Held in memory for the run only. Never stored, logged or shown again.</small>
          <input className="field mono" type="password" required autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
        </label>
        <div className="actions">
          <button className="btn primary" type="submit" disabled={busy || !runnable}>
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
