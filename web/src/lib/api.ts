// Types mirror api/costcutter/contract.py. See docs/api-contract.md.

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8787'

export type JobState =
  | 'queued' | 'cloning' | 'installing' | 'baseline' | 'diagnosing'
  | 'awaiting_selection' | 'fixing' | 'verifying' | 'reporting' | 'done' | 'failed'

export type FindingStatus = 'proposed' | 'selected' | 'applied' | 'reverted' | 'skipped'
export type Phase = 'baseline' | 'after'

export interface RunTotals {
  runs: number
  llm_calls: number
  tool_calls: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  cost_usd: number
  cost_per_run_usd: number
  duration_ms: number
}

export interface CallRef { task_id: string; call_index: number; effect: 'removed' | 'reduced' }
export interface Evidence { trace_id: string; span_id: string | null; trace_url: string; note: string }
export interface CodeLocation { file: string; line_start: number; line_end: number; symbol: string | null }

export interface Finding {
  id: string
  kind: string
  title: string
  summary: string
  severity: 'high' | 'medium' | 'low'
  estimated_saving_usd_per_run: number
  estimated_saving_pct: number
  evidence: Evidence[]
  calls: CallRef[]
  location: CodeLocation | null
  status: FindingStatus
  status_reason: string | null
  /** False for a scan: read from the code, with no run behind it. */
  measured?: boolean
  suggestion?: string | null
  snippet?: string | null
}

export type JobMode = 'measure' | 'scan'
export interface CallSite { file: string; line: number; provider: string; via: string; model: string | null; snippet: string }
export interface ProposedRun { command: string; workdir?: string | null; reason: string; needs: string[] }

export interface Sample {
  id: string
  name: string
  description: string
  language: 'python' | 'typescript' | 'javascript' | 'other'
  repo_url: string
  task_count: number
}

export type Source =
  | { type: 'sample'; sample_id: string }
  | { type: 'github'; repo_url: string; ref?: string | null }
  | { type: 'upload'; upload_id: string; name?: string | null }

export interface Upload { upload_id: string; name: string; files: number; bytes: number }

export interface JobCreate {
  source: Source
  mode?: JobMode
  run?: { command: string; tasks: { input: string }[]; workdir?: string | null; env?: Record<string, string> }
  model_key?: { provider: 'anthropic' | 'openai'; key: string }
  monthly_runs?: number
}

export interface JobSummary {
  baseline: RunTotals | null
  after: RunTotals | null
  saving_pct: number | null
  findings_total: number
  findings_applied: number
  call_sites?: number | null
  files_scanned?: number | null
}

export interface Job {
  id: string
  state: JobState
  mode?: JobMode
  source: Source
  language: 'python' | 'typescript' | 'javascript' | 'other' | null
  base_commit: string | null
  monthly_runs: number | null
  created_at: string
  updated_at: string
  summary: JobSummary
  outcome: 'saved' | 'nothing_to_fix' | 'no_saving' | 'scanned' | null
  error: { code: string; message: string } | null
  last_event_seq: number
  mock: boolean
  scan_summary?: string | null
  scan_good?: string[]
  proposed_run?: ProposedRun | null
}

export interface TaskRun {
  cost_usd: number
  total_tokens: number
  llm_calls: number
  duration_ms: number
  passed: boolean
  trace_id: string
  trace_url: string
}

export interface Comparison {
  baseline: RunTotals
  after: RunTotals
  saving_pct: number
  saving_usd_per_run: number
  quality: { evaluator: string; baseline_score: number; after_score: number; threshold: number; passed: boolean }
  tasks: { task_id: string; input_preview: string; baseline: TaskRun; after: TaskRun }[]
  by_finding: { finding_id: string; status: FindingStatus; saving_usd_per_run: number; reason: string | null }[]
  projection: {
    monthly_runs: number
    baseline_monthly_usd: number
    after_monthly_usd: number
    saving_monthly_usd: number
  } | null
}

export interface Diff {
  base_commit: string
  branch: string
  files: { path: string; additions: number; deletions: number; patch: string }[]
  unified: string
}

export interface PullRequest { url: string; number: number; title: string }

interface EventBase { seq: number; ts: string; job_id: string }
export type JobEvent = EventBase &
  (
    | { type: 'job.state'; state: JobState; previous: JobState | null }
    | { type: 'sandbox.log'; phase: 'install' | Phase; stream: 'stdout' | 'stderr'; line: string; task_id: string | null }
    | {
        type: 'llm.call'; phase: Phase; task_id: string; call_index: number; model: string
        input_tokens: number; output_tokens: number; cache_read_tokens: number; cache_write_tokens: number
        cost_usd: number; running_cost_usd: number; duration_ms: number
      }
    | { type: 'run.completed'; phase: Phase; task_id: string; cost_usd: number; passed: boolean; trace_id: string; trace_url: string }
    | { type: 'finding'; finding: Finding }
    | { type: 'agent.step'; step_index: number; kind: 'thought' | 'tool_call' | 'tool_result'; text: string; tool: string | null; finding_id: string | null }
    | { type: 'patch.applied'; finding_id: string; files: string[]; additions: number; deletions: number }
    | {
        type: 'verify.result'; finding_id: string; passed: boolean
        cost_per_run_before_usd: number; cost_per_run_after_usd: number
        quality_before: number; quality_after: number; reason: string
      }
    | { type: 'recovery'; finding_id: string; action: 'reverted' | 'retried' | 'skipped'; reason: string }
    | { type: 'scan.call_site'; call_site: CallSite }
    | { type: 'job.done'; outcome: string; summary: JobSummary }
    | { type: 'job.error'; code: string; message: string }
  )

export type EventOf<T extends JobEvent['type']> = Extract<JobEvent, { type: T }>

export const EVENT_TYPES: JobEvent['type'][] = [
  'job.state', 'sandbox.log', 'llm.call', 'run.completed', 'finding', 'agent.step',
  'patch.applied', 'verify.result', 'recovery', 'scan.call_site', 'job.done', 'job.error',
]

export class ApiError extends Error {
  code: string
  status: number
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(API_URL + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'unreachable', `Cannot reach the Whittle API at ${API_URL}. Start it with ./start.sh.`)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(
      response.status,
      body?.error?.code ?? 'http_error',
      body?.error?.message ?? `The API answered ${response.status}.`,
    )
  }
  return response.json() as Promise<T>
}

export const api = {
  samples: () => request<{ samples: Sample[]; mock?: boolean }>('/api/samples'),
  createJob: (body: JobCreate, mock?: { speed?: number; scenario?: string }) => {
    const query = new URLSearchParams()
    if (mock?.speed !== undefined) query.set('speed', String(mock.speed))
    if (mock?.scenario) query.set('scenario', mock.scenario)
    const suffix = query.size ? `?${query}` : ''
    return request<Job>(`/api/jobs${suffix}`, { method: 'POST', body: JSON.stringify(body) })
  },
  /** Upload a zip of the code. The body is the file itself. */
  upload: async (file: File): Promise<Upload> => {
    let response: Response
    try {
      response = await fetch(`${API_URL}/api/uploads?name=${encodeURIComponent(file.name)}`, {
        method: 'PUT', body: file, headers: { 'Content-Type': 'application/zip' },
      })
    } catch {
      throw new ApiError(0, 'unreachable', `Cannot reach the Whittle API at ${API_URL}.`)
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      throw new ApiError(response.status, body?.error?.code ?? 'http_error', body?.error?.message ?? `The API answered ${response.status}.`)
    }
    return response.json() as Promise<Upload>
  },
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  fix: (id: string, findingIds: string[]) =>
    request<Job>(`/api/jobs/${id}/fix`, { method: 'POST', body: JSON.stringify({ finding_ids: findingIds }) }),
  comparison: (id: string) => request<Comparison>(`/api/jobs/${id}/comparison`),
  diff: (id: string) => request<Diff>(`/api/jobs/${id}/diff`),
  openPullRequest: (id: string) => request<PullRequest>(`/api/jobs/${id}/pr`, { method: 'POST' }),
  patchUrl: (id: string) => `${API_URL}/api/jobs/${id}/patch`,
  eventsUrl: (id: string) => `${API_URL}/api/jobs/${id}/events`,
}
