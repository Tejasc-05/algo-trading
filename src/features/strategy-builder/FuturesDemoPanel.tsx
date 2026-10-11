import { DemoDiagnostics } from './DemoDiagnostics'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useApi } from '@/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

export function FuturesDemoPanel() {
  const connections = useApi(() => api.exchanges.list())
  const strategies = useApi(() => api.strategies.list())
  const sessions = useApi(() => api.futuresDemo.list())
  const [connectionId, setConnectionId] = useState('')
  const [strategyId, setStrategyId] = useState('')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [timeframe, setTimeframe] = useState('1h')
  const [maxNotional, setMaxNotional] = useState('250')
  const [lossLimit, setLossLimit] = useState('25')
  const [confirmed, setConfirmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [ledger, setLedger] = useState<any[] | null>(null)
  useEffect(() => {
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void sessions.refetch() }, 15000)
    return () => window.clearInterval(timer)
  }, [sessions.refetch])
  async function perform(action: () => Promise<unknown>, success: string) {
    setBusy(true); setMessage('')
    try { await action(); if (success) setMessage(success) }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Demo request failed') }
    finally { setBusy(false); void sessions.refetch() }
  }
  const choices = (connections.data ?? []).filter((item: any) => item.is_testnet && item.is_active && ['binance', 'binanceusdm'].includes(item.exchange_name))
  return <Card>
    <CardHeader><CardTitle>Binance Futures Demo</CardTitle></CardHeader>
    <CardContent className="space-y-4">
      <p className="text-sm text-muted-foreground">Virtual funds only. BTC/ETH USDT perpetuals, one-way positions, isolated margin and 1x leverage. Use a dedicated Binance demo account with no other bots or manual trades.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm">Binance demo connection
          <select aria-label="Binance demo connection" value={connectionId} onChange={e => setConnectionId(e.target.value)} className="mt-1 w-full rounded border border-border bg-background p-2" disabled={busy}>
            <option value="">Choose a saved demo connection</option>
            {choices.map((item: any) => <option key={item.id} value={item.id}>{item.label || item.exchange_name}</option>)}
          </select>
        </label>
        <label className="text-sm">Saved algorithm
          <select aria-label="Demo saved algorithm" value={strategyId} onChange={e => setStrategyId(e.target.value)} className="mt-1 w-full rounded border border-border bg-background p-2" disabled={busy}>
            <option value="">Choose your saved strategy</option>
            {(strategies.data ?? []).map((item: any) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        <label className="text-sm">Contract
          <select aria-label="Demo contract" value={symbol} onChange={e => setSymbol(e.target.value)} className="mt-1 w-full rounded border border-border bg-background p-2" disabled={busy}>
            <option>BTCUSDT</option><option>ETHUSDT</option>
          </select>
        </label>
        <label className="text-sm">Candle interval
          <select aria-label="Demo candle interval" value={timeframe} onChange={e => setTimeframe(e.target.value)} className="mt-1 w-full rounded border border-border bg-background p-2" disabled={busy}>
            {['1m','5m','15m','1h'].map(item => <option key={item}>{item}</option>)}
          </select>
        </label>
        <label className="text-sm">Maximum position notional (USDT)
          <Input aria-label="Demo maximum notional" type="number" min="1" max="1000" value={maxNotional} onChange={e => setMaxNotional(e.target.value)} disabled={busy} />
        </label>
        <label className="text-sm">Maximum loss since activation (USDT)
          <Input aria-label="Demo loss limit" type="number" min="1" max="100" value={lossLimit} onChange={e => setLossLimit(e.target.value)} disabled={busy} />
        </label>
      </div>
      <p className="text-xs text-muted-foreground">Use Futures MACD Long/Short templates or long-only BUY/SELL graphs. Entry must trigger both stop-loss and take-profit nodes. Saved edits require a new demo activation; running sessions keep their pinned version.</p>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} disabled={busy} />I confirm this uses demo funds and a dedicated demo account.</label>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={busy || !connectionId} onClick={() => perform(async () => {
          const result = await api.futuresDemo.verify(connectionId)
          setMessage(`Demo authenticated. Available virtual USDT: ${result.available_balance}. Account trading enabled; key trade permission is checked when submitting a demo order.`)
        }, '')}>Verify Demo Account</Button>
        <Button disabled={busy || !connectionId || !strategyId || !confirmed || !(Number(maxNotional)>0 && Number(maxNotional)<=1000 && Number(lossLimit)>0 && Number(lossLimit)<=100)}
          onClick={() => perform(() => api.futuresDemo.activate({connection_id:connectionId,strategy_id:strategyId,symbol,timeframe,max_notional:Number(maxNotional),loss_limit:Number(lossLimit),confirm_demo:true}), 'Demo session activated. Worker evaluates closed candles every 15 seconds.')}>Start Futures Demo</Button>
      </div>
      {message && <p role="status" className="text-sm">{message}</p>}
      {(sessions.error || connections.error || strategies.error) && <p role="alert" className="text-sm text-destructive">Unable to load demo data. Check the backend connection.</p>}
      <Button variant="outline" disabled={sessions.loading || busy} onClick={() => void sessions.refetch()}>Refresh session status</Button>
      {sessions.data?.length === 0 && <p className="text-sm text-muted-foreground">No futures demo sessions yet.</p>}
      {(sessions.data ?? []).map((session) => <div key={session.id} className="space-y-2 rounded border border-border p-3">
        <p className="text-sm font-medium">{session.symbol} · {session.timeframe} · {session.status}</p>
        <p className="text-xs text-muted-foreground">{session.message} · Cap {session.max_notional} USDT · Loss limit {session.loss_limit} USDT</p>
        <DemoDiagnostics session={session} />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={busy || session.status==='stopped'} onClick={() => perform(() => api.futuresDemo.tick(session.id), 'Demo orders reconciled and current candle checked.')}>Reconcile / Run Tick</Button>
          <Button size="sm" variant="outline" disabled={busy || !['paused','needs_attention'].includes(session.status)} onClick={() => perform(() => api.futuresDemo.resume(session.id), 'Demo session resumed.')}>Resume Demo</Button>
          <Button size="sm" variant="destructive" disabled={busy || session.status==='stopped'} onClick={() => perform(() => api.futuresDemo.stop(session.id), 'Demo stopped. Position closed and protective orders canceled.')}>Stop &amp; Close Demo</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => perform(async () => { setLedger(await api.futuresDemo.orders(session.id)) }, 'Order ledger loaded.')}>View Demo Orders</Button>
        </div>
      </div>)}
      {ledger && <div className="space-y-1 text-xs font-mono">{ledger.length ? ledger.map(order => <p key={order.client_id}>{order.role} · {order.state} · {order.client_id}</p>) : <p>No demo orders submitted.</p>}</div>}
    </CardContent>
  </Card>
}
