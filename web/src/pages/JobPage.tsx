import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Branch, Download, External, Warn } from '../components/Icons'
import { Rail } from '../components/Rail'
import { api } from '../lib/api'
import type { JobState, PullRequest } from '../lib/api'
import { STATE_LABEL } from '../lib/format'
import { useJob } from '../lib/useJob'
import '../styles/app.css'
import { CallsSection } from './job/CallsSection'
import { DiffSection } from './job/DiffSection'
import { FindingsSection } from './job/FindingsSection'
import { FixSection } from './job/FixSection'
import { Inspector } from './job/Inspector'
import { Kpis } from './job/Kpis'
import { ResultSection } from './job/ResultSection'

const SECTIONS = [
  { id: 'calls', label: 'Calls', title: 'Model calls' },
  { id: 'findings', label: 'Findings', title: 'Findings' },
  { id: 'fix', label: 'Fix and verify', title: 'Fix and verify' },
  { id: 'result', label: 'Result', title: 'Result' },
  { id: 'diff', label: 'Diff', title: 'Diff' },
] as const
type SectionId = (typeof SECTIONS)[number]['id']

const ORDER: JobState[] = ['queued', 'cloning', 'installing', 'baseline', 'diagnosing', 'awaiting_selection', 'fixing', 'verifying', 'reporting', 'done']

/** The section that shows what is happening in a given state. */
function sectionFor(state: JobState): SectionId {
  const at = ORDER.indexOf(state)
  if (state === 'done') return 'result'
  if (at >= ORDER.indexOf('fixing')) return 'fix'
  if (at >= ORDER.indexOf('diagnosing')) return 'findings'
  return 'calls'
}

export function JobPage() {
  const { jobId, section } = useParams()
  const navigate = useNavigate()
  const { view, job, loadError, connected } = useJob(jobId)
  const [follow, setFollow] = useState(!section)
  const [selected, setSelected] = useState<string | null>(null)
  const [pr, setPr] = useState<PullRequest | null>(null)
  const [prError, setPrError] = useState<string | null>(null)
  const [opening, setOpening] = useState(false)

  const current = (SECTIONS.find((s) => s.id === section)?.id ?? sectionFor(view.state)) as SectionId
  const live = sectionFor(view.state)

  useEffect(() => {
    if (follow && jobId && view.seq > 0 && section !== live) navigate(`/app/jobs/${jobId}/${live}`, { replace: true })
  }, [follow, live, jobId, section, view.seq, navigate])

  if (loadError && !job) {
    return (
      <div className="shell">
        <Rail />
        <main className="work">
          <div className="notice" role="alert">
            <Warn />
            <div>
              <strong>{loadError.code === 'job_not_found' ? 'This job no longer exists' : 'The job could not be loaded'}</strong>
              {loadError.code === 'job_not_found'
                ? 'The mock server keeps jobs in memory, so they are lost when it restarts.'
                : loadError.message}
            </div>
          </div>
          <Link className="btn primary" to="/app">Start a new job</Link>
        </main>
      </div>
    )
  }

  const name = job?.source.type === 'sample' ? job.source.sample_id : job?.source.type === 'github' ? job.source.repo_url.replace('https://github.com/', '') : ''
  const done = view.state === 'done'
  const failed = view.state === 'failed'
  const applied = view.findings.filter((f) => f.status === 'applied').length
  const stateDot = (id: SectionId) => {
    const order: SectionId[] = ['calls', 'findings', 'fix', 'result', 'diff']
    if (done) return 'done'
    if (id === live && !failed) return 'live'
    return order.indexOf(id) < order.indexOf(live) ? 'done' : ''
  }

  async function openPr() {
    if (!jobId) return
    setOpening(true)
    setPrError(null)
    try {
      setPr(await api.openPullRequest(jobId))
    } catch (e) {
      setPrError((e as Error).message)
    } finally {
      setOpening(false)
    }
  }

  return (
    <div className="shell with-inspector">
      <Rail
        foot={
          <>
            <label className="follow">
              <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
              Follow the job as it runs
            </label>
            <span>{connected ? 'Live' : done || failed ? 'Stream closed' : 'Reconnecting…'}</span>
          </>
        }
      >
        <h2>This job</h2>
        <nav aria-label="Job sections">
          {SECTIONS.map((s) => (
            <Link key={s.id} className="item" to={`/app/jobs/${jobId}/${s.id}`} aria-current={current === s.id ? 'page' : undefined}
              onClick={() => setFollow(false)}>
              <span className={`dot ${stateDot(s.id)}`} />
              {s.label}
              {s.id === 'findings' && view.findings.length > 0 && <span className="count">{view.findings.length}</span>}
            </Link>
          ))}
        </nav>
      </Rail>

      <main className="work">
        <div className="work-head">
          <div className="titles">
            <div className="row">
              <h1>{SECTIONS.find((s) => s.id === current)!.title}</h1>
              <span className={`tag ${failed ? 'bad' : done ? 'ok' : 'live'}`}>{STATE_LABEL[view.state]}</span>
              {job?.mock && <span className="tag mock" title="Every number on this page is invented by the mock server">mock data</span>}
            </div>
            <span className="meta mono">{name} · {jobId}</span>
          </div>
          <span className="spacer" />
          <a className="btn" href={done && applied ? api.patchUrl(jobId!) : undefined} aria-disabled={!done || !applied}
            style={!done || !applied ? { color: '#9a9dab', pointerEvents: 'none' } : undefined}>
            <Download /> Download patch
          </a>
          {pr ? (
            <a className="btn primary" href={pr.url} target="_blank" rel="noreferrer"><Branch /> Pull request #{pr.number} <External /></a>
          ) : (
            <button className="btn primary" disabled={!done || !applied || opening} onClick={openPr}>
              <Branch /> {opening ? 'Opening…' : 'Open pull request'}
            </button>
          )}
        </div>

        {prError && <div className="notice" role="alert"><Warn /><div><strong>The pull request was not opened</strong>{prError}</div></div>}
        {view.error && (
          <div className="notice" role="alert">
            <Warn />
            <div>
              <strong>The job failed ({view.error.code})</strong>
              {view.error.message} <Link to="/app">Start another job</Link>
            </div>
          </div>
        )}

        <Kpis job={job} view={view} />

        {current === 'calls' && <CallsSection view={view} />}
        {current === 'findings' && <FindingsSection jobId={jobId!} view={view} selected={selected} onSelect={setSelected} />}
        {current === 'fix' && <FixSection view={view} selected={selected} onSelect={setSelected} />}
        {current === 'result' && <ResultSection jobId={jobId!} done={done} findings={view.findings} />}
        {current === 'diff' && <DiffSection jobId={jobId!} done={done} />}
      </main>

      <Inspector view={view} selected={selected} />
    </div>
  )
}
