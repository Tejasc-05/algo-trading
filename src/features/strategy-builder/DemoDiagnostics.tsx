import type { DemoSessionView, DemoNodeDiagnostic, DiagnosticValue } from '@/lib/api'

const number = (value: number | boolean | null | undefined): string => {
  if (typeof value === 'boolean') return value ? 'True' : 'False'
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: 8 }) : 'Unavailable'
}
const date = (value: string) => new Date(value).toLocaleString()
const actionNames: Record<string, string> = { buy: 'Open long', openLong: 'Open long', openShort: 'Open short', sell: 'Close position', closePosition: 'Close position' }

function operands(node: DemoNodeDiagnostic) {
  const inputs = node.inputs
  if (node.node_type === 'condition') {
    const operator = String(node.params.operator)
    if (operator.startsWith('crosses_')) {
      return `${number(inputs[0]?.previous)} → ${number(inputs[0]?.current)} ${operator.replaceAll('_', ' ')} ${number(inputs[1]?.previous)} → ${number(inputs[1]?.current)}`
    }
    return `${number(inputs[0]?.current)} ${operator} ${node.params.value}`
  }
  return inputs.map(item => number(item.current)).join(', ')
}

export function DemoDiagnostics({ session }: { session: DemoSessionView }) {
  const snapshot = session.diagnostics
  const evaluation = snapshot?.evaluation
  const macds = evaluation?.nodes.filter(node => node.macd) ?? []
  const gates = evaluation?.nodes.filter(node => ['condition', 'logic'].includes(node.category)) ?? []
  const actions = evaluation?.nodes.filter(node => node.category === 'action') ?? []
  const others = evaluation?.nodes.filter(node => node.category === 'indicator' && !node.macd) ?? []
  const stale = snapshot && Date.now() - Date.parse(snapshot.checked_at) > 90_000 && session.status === 'running'
  return <section aria-label={`Demo strategy status ${session.symbol} ${session.timeframe}`} className="rounded-lg bg-secondary/20 p-3 space-y-3">
    <h4 className="text-sm font-semibold">Strategy status</h4>
    {!snapshot ? <p className="text-sm text-muted-foreground">{['paused', 'needs_attention'].includes(session.status) ? `Session paused. Last recorded reason: ${session.message || 'No status message available'}. No detailed diagnostic snapshot has been recorded yet.` : session.status === 'stopped' ? 'Session stopped. No diagnostic snapshot was recorded for this session.' : 'No diagnostic snapshot yet. The runner will record one on its next check.'}</p> : <>
      <p role="status" aria-atomic="true" className="text-sm">{snapshot.reason}</p>
      <p className="text-xs text-muted-foreground">Last runner check: {date(snapshot.checked_at)} · {snapshot.reason_code} · Last observed position: {snapshot.position ? `${snapshot.position.side} (${snapshot.position.quantity} base units)` : 'Not observed yet'}</p>
      {stale && <p className="text-sm text-warning">Snapshot is older than 90 seconds. Check that the demo worker is running; this information may be out of date.</p>}
      {snapshot.last_error && <p className="text-sm text-destructive">Last blocking reason: {snapshot.last_error.code} · {snapshot.last_error.message}</p>}
      {evaluation ? <>
        <p className="text-xs text-muted-foreground">Pinned strategy version {evaluation.strategy_version_number} · {evaluation.bars_used} closed candles · Evaluated {date(evaluation.evaluated_at)}</p>
        <p className="text-sm">Last candle: {date(evaluation.candle_open_at)} → {date(evaluation.candle_close_at)} · Close: {number(evaluation.close_price)} USDT</p>
        {session.status === 'running' && Date.parse(evaluation.next_candle_close_at) > Date.now() && <p className="text-xs text-muted-foreground">Next candle closes around {date(evaluation.next_candle_close_at)}; the runner checks after it closes.</p>}
        <p className="text-sm">Last evaluation: {evaluation.decision}. Entry: {evaluation.entry_signals.map(action => actionNames[action] ?? action).join(', ') || 'None'} · Exit: {evaluation.exit_signals.map(action => actionNames[action] ?? action).join(', ') || 'None'}</p>
        {macds.map(node => <div key={node.id} className="text-sm space-y-1">
          <p className="font-medium">{node.label} · MACD ({node.params.fast}, {node.params.slow}, {node.params.signal}) · Selected output: {node.params.output}</p>
          <div className="flex flex-wrap gap-x-4 gap-y-1">{Object.entries(node.macd as Record<string, DiagnosticValue>).map(([key, value]) => <p key={key}>{key}: <span className="font-mono">{number(value.current)}</span> <span className="text-xs text-muted-foreground">(previous {number(value.previous)})</span></p>)}</div>
        </div>)}
        {others.map(node => <p key={node.id} className="text-sm">{node.label}: {number(node.current)} <span className="text-xs text-muted-foreground">(previous {number(node.previous)})</span></p>)}
        {gates.length > 0 && <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="text-left text-muted-foreground pb-2">Conditions from the last evaluated candle</caption><thead><tr><th className="text-left p-2">Condition</th><th className="text-left p-2">Values</th><th className="text-left p-2">Result</th></tr></thead><tbody>{gates.map(node => <tr key={node.id}><th scope="row" className="text-left p-2 font-medium">{node.label}</th><td className="p-2">{operands(node)}</td><td className="p-2">{typeof node.current === 'boolean' ? node.current ? 'True' : 'False' : 'Unknown / warming up'}</td></tr>)}</tbody></table></div>}
        {actions.length > 0 && <p className="text-xs text-muted-foreground">Actions: {actions.map(node => `${node.label}: ${node.triggered ? 'triggered' : 'not triggered'}`).join(' · ')}</p>}
      </> : <p className="text-sm text-muted-foreground">{session.last_bar ? 'This session predates diagnostic recording. Values will appear after the next new closed candle is evaluated.' : 'No candle evaluation recorded yet. Runner errors can occur before indicators are calculated.'}</p>}
      {snapshot.entry_limits && <details><summary className="cursor-pointer text-sm py-2">Last observed entry limit check</summary><p className="text-xs text-muted-foreground">Rounded quantity {snapshot.entry_limits.rounded_quantity} · Mark price {snapshot.entry_limits.mark_price} USDT · Notional {snapshot.entry_limits.notional} USDT · Minimum {snapshot.entry_limits.exchange_minimum_notional} USDT · Cap {snapshot.entry_limits.maximum_notional} USDT · Available margin {snapshot.entry_limits.available_margin} USDT</p><ul className="text-xs space-y-1 mt-2">{snapshot.entry_limits.checks.map(check => <li key={check.label} className={check.passed ? 'text-muted-foreground' : 'text-warning'}>{check.passed ? 'Pass' : 'Blocked'}: {check.label}</li>)}</ul></details>}
    </>}
    <p className="text-xs text-muted-foreground">Read-only explanation. Refreshing the session list does not submit orders. A triggered condition may still be blocked by account or risk checks.</p>
  </section>
}
