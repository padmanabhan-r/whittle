import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api, ApiError, EVENT_TYPES } from './api'
import type { CallSite, EventOf, Finding, Job, JobEvent, JobState, Phase } from './api'

export type Call = EventOf<'llm.call'>
export type Step = EventOf<'agent.step'>
export type LogLine = EventOf<'sandbox.log'>

export interface RunView {
  state: JobState
  seq: number
  calls: Record<Phase, Call[]>
  runningCost: Record<Phase, number>
  completed: Record<Phase, EventOf<'run.completed'>[]>
  logs: LogLine[]
  findings: Finding[]
  callSites: CallSite[]
  steps: Step[]
  patches: Record<string, EventOf<'patch.applied'>>
  verify: Record<string, EventOf<'verify.result'>>
  recoveries: EventOf<'recovery'>[]
  error: { code: string; message: string } | null
  done: boolean
}

const empty: RunView = {
  state: 'queued',
  seq: 0,
  calls: { baseline: [], after: [] },
  runningCost: { baseline: 0, after: 0 },
  completed: { baseline: [], after: [] },
  logs: [],
  findings: [],
  callSites: [],
  steps: [],
  patches: {},
  verify: {},
  recoveries: [],
  error: null,
  done: false,
}

function reduce(view: RunView, event: JobEvent | { type: 'reset' }): RunView {
  if (event.type === 'reset') return empty
  // A reconnect can replay events already applied; each seq counts once.
  if (event.seq <= view.seq) return view
  const next = { ...view, seq: event.seq }
  switch (event.type) {
    case 'job.state':
      return { ...next, state: event.state }
    case 'sandbox.log':
      return { ...next, logs: [...view.logs, event] }
    case 'llm.call':
      return {
        ...next,
        calls: { ...view.calls, [event.phase]: [...view.calls[event.phase], event] },
        runningCost: { ...view.runningCost, [event.phase]: event.running_cost_usd },
      }
    case 'run.completed':
      return { ...next, completed: { ...view.completed, [event.phase]: [...view.completed[event.phase], event] } }
    case 'finding': {
      const exists = view.findings.some((f) => f.id === event.finding.id)
      const findings = exists
        ? view.findings.map((f) => (f.id === event.finding.id ? event.finding : f))
        : [...view.findings, event.finding]
      return { ...next, findings }
    }
    case 'agent.step':
      return { ...next, steps: [...view.steps, event] }
    case 'patch.applied':
      return { ...next, patches: { ...view.patches, [event.finding_id]: event } }
    case 'verify.result':
      return { ...next, verify: { ...view.verify, [event.finding_id]: event } }
    case 'recovery':
      return { ...next, recoveries: [...view.recoveries, event] }
    case 'scan.call_site':
      return { ...next, callSites: [...view.callSites, event.call_site] }
    case 'job.done':
      return { ...next, done: true }
    case 'job.error':
      return { ...next, done: true, error: { code: event.code, message: event.message } }
  }
}

export function useJob(jobId: string | undefined) {
  const [view, dispatch] = useReducer(reduce, empty)
  const [job, setJob] = useState<Job | null>(null)
  const [loadError, setLoadError] = useState<ApiError | null>(null)
  const [connected, setConnected] = useState(false)
  const finished = useRef(false)

  const refresh = useCallback(async () => {
    if (!jobId) return
    try {
      setJob(await api.job(jobId))
      setLoadError(null)
    } catch (error) {
      setLoadError(error as ApiError)
    }
  }, [jobId])

  useEffect(() => {
    if (!jobId) return
    dispatch({ type: 'reset' })
    finished.current = false
    refresh()
    const source = new EventSource(api.eventsUrl(jobId))
    source.onopen = () => setConnected(true)
    source.onerror = () => {
      setConnected(false)
      // The server closes the stream after the last event; do not let EventSource reconnect and replay.
      if (finished.current) source.close()
    }
    for (const type of EVENT_TYPES) {
      source.addEventListener(type, (message) => {
        const event = JSON.parse((message as MessageEvent).data) as JobEvent
        if (event.type === 'job.done' || event.type === 'job.error') {
          finished.current = true
          source.close()
          setConnected(false)
        }
        dispatch(event)
      })
    }
    return () => source.close()
  }, [jobId, refresh])

  // The job record carries the summary; refetch it when the state changes.
  useEffect(() => {
    refresh()
  }, [view.state, view.done, refresh])

  return { view, job, loadError, connected }
}
