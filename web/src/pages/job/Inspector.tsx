import { useEffect, useRef, useState } from 'react'
import { External } from '../../components/Icons'
import { KIND_LABEL, usd } from '../../lib/format'
import type { RunView, Step } from '../../lib/useJob'
import { statusTag } from './FindingsSection'

type Tab = 'agent' | 'finding' | 'console'

function who(step: Step): { label: string; cls: string } {
  if (step.kind === 'thought') return { label: 'whittle', cls: '' }
  const tool = step.tool ?? ''
  if (tool.startsWith('neatlogs')) return { label: 'neatlogs', cls: 'neatlogs' }
  if (tool.startsWith('entire')) return { label: 'entire', cls: 'entire' }
  if (tool.startsWith('sandbox')) return { label: 'sandbox', cls: 'sandbox' }
  // Any other tool is named by its family: repo.read_file is the repo at work.
  return { label: step.kind === 'tool_result' ? 'result' : (tool.split('.')[0] || 'tool'), cls: '' }
}

export function Inspector({ view, selected }: { view: RunView; selected: string | null }) {
  const [tab, setTab] = useState<Tab>('agent')
  const end = useRef<HTMLDivElement>(null)
  const finding = view.findings.find((f) => f.id === selected) ?? null

  useEffect(() => {
    if (selected) setTab('finding')
  }, [selected])

  useEffect(() => {
    if (tab !== 'finding') end.current?.scrollIntoView({ block: 'end' })
  }, [view.steps.length, view.logs.length, tab])

  // Tool results inherit the label of the call they answer.
  let last = { label: 'whittle', cls: '' }
  const steps = view.steps.map((step) => {
    const mine = step.kind === 'tool_result' ? last : who(step)
    if (step.kind === 'tool_call') last = mine
    return { step, ...mine }
  })

  return (
    <aside className="inspector" aria-label="Details">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'agent'} onClick={() => setTab('agent')}>Agent</button>
        <button role="tab" aria-selected={tab === 'finding'} onClick={() => setTab('finding')}>Finding</button>
        <button role="tab" aria-selected={tab === 'console'} onClick={() => setTab('console')}>Console</button>
      </div>
      <div className="body" role="tabpanel">
        {tab === 'agent' && (
          steps.length === 0 ? (
            <p>The agent starts once the baseline has run. Its reasoning and every tool it calls will appear here.</p>
          ) : (
            <ol className="steps">
              {steps.map(({ step, label, cls }) => (
                <li key={step.seq} className={step.kind === 'thought' ? 'thought' : step.kind === 'tool_result' ? 'result' : ''}>
                  <span className={`who ${cls}`}>{step.kind === 'tool_result' ? '' : label}</span>
                  <span className={`text ${step.kind === 'tool_call' ? 'code' : ''}`}>{step.text}</span>
                </li>
              ))}
              {view.recoveries.length > 0 && view.done && (
                <li><span className="who revert">revert</span><span className="text">{view.recoveries.length} fix undone after failing its check.</span></li>
              )}
            </ol>
          )
        )}
        {tab === 'finding' && (
          finding ? (
            <>
              <h3>Finding {view.findings.indexOf(finding) + 1} · {KIND_LABEL[finding.kind] ?? finding.kind}</h3>
              <div className="title">{finding.title}</div>
              {statusTag(finding, false)}
              <p style={{ marginTop: 12 }}>{finding.summary}</p>
              {finding.status_reason && <p style={{ marginTop: 8, color: 'var(--red)' }}>{finding.status_reason}</p>}
              <h3>Evidence</h3>
              {finding.evidence.map((evidence) => (
                <p key={evidence.trace_id} style={{ fontSize: 13.5 }}>
                  {evidence.note}{' '}
                  <a href={evidence.trace_url} target="_blank" rel="noreferrer" className="mono" style={{ fontSize: 12.5 }}>
                    {evidence.trace_id} <External />
                  </a>
                </p>
              ))}
              <h3>Numbers</h3>
              <dl className="kv">
                <dt>Estimated saving</dt><dd>{usd(finding.estimated_saving_usd_per_run)} per run</dd>
                <dt>Calls affected</dt><dd>{finding.calls.length}</dd>
                {finding.location && <><dt>In the code</dt><dd>{finding.location.file}:{finding.location.line_start}–{finding.location.line_end}</dd></>}
                {finding.location?.symbol && <><dt>Symbol</dt><dd>{finding.location.symbol}</dd></>}
                {view.verify[finding.id] && (
                  <>
                    <dt>Cost per run</dt>
                    <dd>{usd(view.verify[finding.id].cost_per_run_before_usd)} → {usd(view.verify[finding.id].cost_per_run_after_usd)}</dd>
                    <dt>Quality</dt>
                    <dd>{view.verify[finding.id].quality_before.toFixed(2)} → {view.verify[finding.id].quality_after.toFixed(2)}</dd>
                  </>
                )}
              </dl>
            </>
          ) : (
            <p>Select a finding in the table to see its evidence, where it sits in the code and how its fix checked out.</p>
          )
        )}
        {tab === 'console' && (
          view.logs.length === 0 ? <p>Sandbox output will appear here.</p> : (
            <pre className="console">
              {view.logs.map((log) => (
                <span key={log.seq}><span className="phase">[{log.phase}] </span>{log.line}{'\n'}</span>
              ))}
            </pre>
          )
        )}
        <div ref={end} />
      </div>
    </aside>
  )
}
