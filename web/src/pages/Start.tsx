import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Warn } from '../components/Icons'
import { Rail } from '../components/Rail'
import { api, ApiError } from '../lib/api'
import type { JobCreate, Sample } from '../lib/api'
import '../styles/app.css'

export function Start() {
  const navigate = useNavigate()
  const [samples, setSamples] = useState<Sample[] | null>(null)
  const [mock, setMock] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [speed, setSpeed] = useState(4)
  const [monthlyRuns, setMonthlyRuns] = useState('20000')
  const [repo, setRepo] = useState('')
  const [ref, setRef] = useState('')
  const [command, setCommand] = useState('python -m agent "{input}"')
  const [tasks, setTasks] = useState('')
  const [provider, setProvider] = useState<'anthropic' | 'openai'>('anthropic')
  const [key, setKey] = useState('')

  useEffect(() => {
    api
      .samples()
      .then((r) => {
        setSamples(r.samples)
        setMock(Boolean(r.mock))
      })
      .catch((e: ApiError) => setLoadError(e.message))
  }, [])

  async function start(body: JobCreate, label: string) {
    setBusy(label)
    setError(null)
    try {
      const runs = Number(monthlyRuns)
      const job = await api.createJob({ ...body, monthly_runs: runs > 0 ? runs : undefined }, mock ? { speed } : undefined)
      // The key lives only in this request. Drop it from the page as soon as it is sent.
      setKey('')
      navigate(`/app/jobs/${job.id}`)
    } catch (e) {
      setError((e as ApiError).message)
      setBusy(null)
    }
  }

  function submitRepo(event: FormEvent) {
    event.preventDefault()
    const list = tasks.split('\n').map((t) => t.trim()).filter(Boolean)
    if (list.length === 0) return setError('Add at least one task: an input the agent should be run with.')
    if (list.length > 10) return setError('Use at most ten tasks.')
    start(
      {
        source: { type: 'github', repo_url: repo.trim(), ref: ref.trim() || null },
        run: { command: command.trim(), tasks: list.map((input) => ({ input })) },
        model_key: { provider, key },
      },
      'repo',
    )
  }

  return (
    <div className="shell">
      <Rail />
      <main className="work start">
        <h1>Find what your agent wastes</h1>
        <p className="lede">
          Whittle runs the agent in a sandbox, records every model call, and lists the waste it can prove.
          You choose what to fix; it patches, reruns and keeps only the fixes that hold.
        </p>

        {loadError && (
          <div className="notice" role="alert"><Warn /><div><strong>The API is not answering</strong>{loadError}</div></div>
        )}
        {error && <div className="notice" role="alert"><Warn /><div><strong>The job did not start</strong>{error}</div></div>}

        <h2 className="section-title" style={{ marginTop: 0 }}>Try a sample agent</h2>
        <div className="panel">
          <div className="toolbar">
            {mock ? (
              <>
                <span className="tag mock">mock data</span>
                <span className="note">This server is the mock: the run is scripted and its numbers are invented.</span>
                <span className="spacer" />
                <label className="check">
                  Playback
                  <select className="pick" value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
                    <option value={1}>Real pace (about a minute)</option>
                    <option value={4}>Fast</option>
                    <option value={12}>Very fast</option>
                  </select>
                </label>
              </>
            ) : (
              <span className="note">
                Each sample runs in a Docker sandbox on this machine with Whittle's own model key. A full job takes
                about eight minutes and costs under a dollar in model calls.
              </span>
            )}
          </div>
          <div className="table-wrap">
            <table className="ledger">
              <thead><tr><th>Sample</th><th>Language</th><th className="r">Tasks</th><th /></tr></thead>
              <tbody>
                {samples === null && !loadError && <tr><td colSpan={4}>Loading samples…</td></tr>}
                {samples?.map((sample) => (
                  <tr key={sample.id}>
                    <td className="wrap">
                      <span style={{ fontWeight: 600 }}>{sample.name}</span>
                      <span className="loc" style={{ fontFamily: 'var(--body)', fontSize: 13.5 }}>{sample.description}</span>
                    </td>
                    <td>{sample.language}</td>
                    <td className="r">{sample.task_count}</td>
                    <td className="r">
                      <button className="btn primary" disabled={busy !== null}
                        onClick={() => start({ source: { type: 'sample', sample_id: sample.id } }, sample.id)}>
                        {busy === sample.id ? 'Starting…' : <>Run <ArrowRight /></>}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <h2 className="section-title">Or use your own repo</h2>
        <form className="panel form-grid" onSubmit={submitRepo}>
          <label className="wide">
            Public GitHub repository
            <input className="field" type="url" required placeholder="https://github.com/owner/repo" value={repo}
              onChange={(e) => setRepo(e.target.value)} />
          </label>
          <label>
            Branch, tag or commit <small>Leave empty for the default branch</small>
            <input className="field" value={ref} onChange={(e) => setRef(e.target.value)} placeholder="main" />
          </label>
          <label>
            Runs per month <small>Used only for the monthly projection</small>
            <input className="field" inputMode="numeric" value={monthlyRuns} onChange={(e) => setMonthlyRuns(e.target.value.replace(/\D/g, ''))} />
          </label>
          <label className="wide">
            Command to run the agent once <small>{'{input}'} is replaced by each task below</small>
            <input className="field mono" required value={command} onChange={(e) => setCommand(e.target.value)} />
          </label>
          <label className="wide">
            Tasks <small>One input per line, up to ten. These are run before and after the fixes.</small>
            <textarea className="field" rows={4} value={tasks} onChange={(e) => setTasks(e.target.value)}
              placeholder={'What is the refund policy for annual plans?\nSummarise ticket 4821 and draft a reply.'} />
          </label>
          <label>
            Model provider
            <select className="pick" value={provider} onChange={(e) => setProvider(e.target.value as 'anthropic' | 'openai')}>
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI compatible</option>
            </select>
          </label>
          <label>
            API key <small>Held in memory for this job only. Never stored, logged or shown again.</small>
            <input className="field mono" type="password" required autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
          </label>
          <div className="actions">
            <button className="btn primary" type="submit" disabled={busy !== null}>
              {busy === 'repo' ? 'Starting…' : <>Run on this repo <ArrowRight /></>}
            </button>
            <span className="note" style={{ color: 'var(--mute)', fontSize: 13 }}>
              {mock
                ? 'With the mock backend this plays the same scripted run; your repo is not cloned.'
                : 'Public repositories only. Your key is held in memory for this job and never stored.'}
            </span>
          </div>
        </form>
      </main>
    </div>
  )
}
