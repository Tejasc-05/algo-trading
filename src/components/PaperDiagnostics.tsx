import type { DemoNodeDiagnostic } from '@/lib/api'

function value(x: unknown): string {
  if (x == null) return 'Unknown / warming up'
  if (typeof x === 'boolean') return x ? 'True' : 'False'
  if (typeof x === 'number') return Number.isFinite(x) ? x.toLocaleString(undefined, { maximumFractionDigits: 6 }) : 'Unavailable'
  return JSON.stringify(x)
}
function date(x?: string) { return x ? new Date(x).toLocaleString() : 'Not recorded yet' }

export function PaperDiagnostics({ account }: { account: any }) {
  const diagnostic = account.diagnostics
  const evaluation = diagnostic?.evaluation
  const nodes: DemoNodeDiagnostic[] = evaluation?.nodes ?? []
  const heartbeat = diagnostic?.worker_checked_at
  const stale = account.is_active && (!diagnostic?.checked_at || Date.now() - Date.parse(heartbeat || diagnostic.checked_at) > 90000)
  return <section aria-label="Paper strategy status" className="rounded-lg bg-secondary/30 p-4 space-y-3">
    <h3 className="text-sm font-semibold">Strategy status</h3>
    <p role="status" className="text-sm">{diagnostic?.reason ?? 'Waiting for the worker’s first check.'}</p>
    <p className="text-xs text-muted-foreground">Last worker check: {date(heartbeat)} · {diagnostic?.reason_code ?? 'WAITING_FIRST_CHECK'}</p>
    {stale && <p className="text-sm text-warning">No recent worker check. Make sure the paper worker is running; this account’s data may be out of date.</p>}
    {diagnostic?.last_error && <p className="text-sm text-destructive">Last blocking error: {diagnostic.last_error}</p>}
    {evaluation && <>
      <p className="text-xs text-muted-foreground">Last evaluated candle: {date(evaluation.candle_open)} → {date(evaluation.candle_close)} · Close {value(evaluation.price)} {account.currency}. Next close: {date(evaluation.next_candle_close)}.</p>
      <p className="text-xs text-muted-foreground">Market source: {evaluation.market_source} · Signals: {evaluation.signals.map((s: { action: string }) => s.action).join(', ') || 'None'} · Funding charged during this evaluation: {value(evaluation.funding_payment)} {account.currency}</p>
      <details><summary className="cursor-pointer py-2 text-sm">Algorithm values and conditions</summary>
        <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="text-left py-2 text-muted-foreground">Values from the pinned strategy’s last evaluated candle</caption>
          <thead><tr><th className="text-left p-2">Node</th><th className="text-left p-2">Current value / result</th><th className="text-left p-2">Previous</th></tr></thead>
          <tbody>{nodes.map(node => <tr key={node.id}><th scope="row" className="text-left p-2 font-medium">{node.label}</th>
            <td className="p-2">{node.category === 'action' || node.category === 'risk' ? node.triggered ? 'Triggered' : 'Not triggered' : value(node.current)}
              {node.category === 'condition' && node.inputs?.length > 0 && <p className="text-xs text-muted-foreground">Inputs: {node.inputs.map(i => value(i.current)).join(', ')} {String(node.params?.operator ?? '')} {value(node.params?.value)}</p>}
              {node.macd && <p className="text-xs">{Object.entries(node.macd).map(([name, v]) => `${name}: ${value(v.current)}`).join(' · ')}</p>}
            </td><td className="p-2">{value(node.previous)}</td></tr>)}</tbody>
        </table></div>
      </details>
    </>}
    <p className="text-xs text-muted-foreground">Status refresh only reads data. “Check strategy now” can create a simulated trade when a new candle and your algorithm’s conditions permit it.</p>
  </section>
}
