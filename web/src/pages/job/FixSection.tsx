import { Undo } from '../../components/Icons'
import type { RunView } from '../../lib/useJob'
import { statusTag } from './FindingsSection'

export function FixSection({ view, selected, onSelect, remote = false }: { view: RunView; selected: string | null; onSelect: (id: string) => void; remote?: boolean }) {
  const chosen = view.findings.filter((f) => f.status !== 'proposed' && f.status !== 'skipped')
  const liveId = view.steps[view.steps.length - 1]?.finding_id

  if (chosen.length === 0) {
    return (
      <div className="panel">
        <div className="empty">
          <h2>Nothing is being fixed yet</h2>
          <p>
            {remote
              ? 'A recording is fixed from your terminal: run whittle fix. Each finding is then patched, rerun on your machine and scored here, and any fix that fails its check is undone.'
              : 'Choose findings on the Findings page. Each one is then patched, rerun and scored here, and any fix that fails its check is undone.'}
          </p>
        </div>
      </div>
    )
  }

  return (
    <>
      {view.recoveries.map((recovery) => {
        const finding = view.findings.find((f) => f.id === recovery.finding_id)
        const retried = recovery.action === 'retried'
        const label = retried ? 'Retried' : recovery.action === 'skipped' ? 'Skipped' : 'Reverted'
        return (
          <div className="notice recover" role="status" key={recovery.seq}>
            <Undo />
            <div>
              <strong>{label}: {finding?.title ?? (retried ? 'a sandbox run' : recovery.finding_id)}</strong>
              {recovery.reason}
              {recovery.action === 'reverted' ? ' The earlier fixes are kept.' : ''}
            </div>
          </div>
        )
      })}
      <div className="panel">
        <div className="table-wrap">
          <table className="ledger">
            <thead>
              <tr>
                <th>#</th><th>Fix</th><th>Patch</th><th className="r">Cost per run</th>
                <th className="r">Quality</th><th>Result</th>
              </tr>
            </thead>
            <tbody>
              {chosen.map((finding) => {
                const patch = view.patches[finding.id]
                const verify = view.verify[finding.id]
                const n = view.findings.indexOf(finding) + 1
                const live = liveId === finding.id && !view.done
                return (
                  <tr key={finding.id} className="clickable" aria-selected={selected === finding.id}
                    onClick={() => onSelect(finding.id)}>
                    <td><span className={`badge-n ${finding.status === 'reverted' ? 'bad' : live ? 'live' : ''}`}>{n}</span></td>
                    <td className="wrap">
                      <span style={{ fontWeight: 600 }}>{finding.title}</span>
                      {patch && <span className="loc">{patch.files.join(', ')}</span>}
                      {(verify || (live && patch)) && (
                        <span className="loc" style={{ fontFamily: 'var(--body)', fontSize: 13, color: verify && !verify.passed ? 'var(--red)' : undefined }}>
                          {verify ? verify.reason : remote ? 'Rerunning on your machine…' : 'Rerunning the tasks…'}
                        </span>
                      )}
                    </td>
                    <td>{patch ? <>+{patch.additions} −{patch.deletions}</> : live ? 'writing…' : '–'}</td>
                    <td className="r">
                      {verify ? <>{verify.cost_per_run_before_usd.toFixed(4)} → {verify.cost_per_run_after_usd.toFixed(4)}</> : '–'}
                    </td>
                    <td className="r">
                      {verify ? <>{verify.quality_before.toFixed(2)} → {verify.quality_after.toFixed(2)}</> : '–'}
                    </td>
                    <td>{statusTag(finding, live)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
