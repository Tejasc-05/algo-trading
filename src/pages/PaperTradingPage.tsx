import { motion } from 'framer-motion'
import { Activity, ArrowDownLeft, ArrowUpRight, Wallet } from 'lucide-react'
import { StatCard } from '@/components/common/StatCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { EquityChart } from '@/components/charts/RechartsComponents'
import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Input } from '@/components/ui/input'
import { PaperDiagnostics } from '@/components/PaperDiagnostics'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { formatPercent } from '@/utils/formatters'
import { cn } from '@/utils/cn'

export function PaperTradingPage() {
  const [searchParams] = useSearchParams()
  const accounts = useApi(() => api.paperTrading.accounts())
  const [selectedId, setSelectedId] = useState('')
  const accountId = selectedId || accounts.data?.[0]?.id || ''
  const account = useApi(() => accountId ? api.paperTrading.getAccount(accountId) : Promise.resolve(null), [accountId])
  const portfolio = useApi(() => accountId ? api.paperTrading.positions(accountId) : Promise.resolve([]), [accountId])
  const performance = useApi(() => accountId ? api.paperTrading.performance(accountId) : Promise.resolve(null), [accountId])
  const trades = useApi(() => accountId ? api.paperTrading.getTrades(accountId) : Promise.resolve([]), [accountId])
  const strategies = useApi(() => api.strategies.list())
  const [strategyId, setStrategyId] = useState('')
  const [marketType, setMarketType] = useState<'spot' | 'futures'>('spot')
  const [symbol, setSymbol] = useState('BTC/USDT')
  useEffect(() => {
    const requestedSymbol = searchParams.get('symbol')?.toUpperCase()
    if (requestedSymbol && /^[A-Z0-9]{1,12}\/[A-Z0-9]{1,12}$/.test(requestedSymbol)) setSymbol(requestedSymbol)
  }, [searchParams])
  const [timeframe, setTimeframe] = useState('1h')
  const [balance, setBalance] = useState('10000')
  const [leverage, setLeverage] = useState('1')
  const [fee, setFee] = useState('0.1')
  const [slippage, setSlippage] = useState('0.05')
  const [funding, setFunding] = useState('0.01')
  const [maintenance, setMaintenance] = useState('0.5')
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const current = account.data?.id === accountId ? account.data : null
  const quoteCurrency = current?.currency ?? symbol.split('/')[1]?.toUpperCase() ?? 'USDT'
  const money = (value: number | null | undefined) => value == null ? '—' : `${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: quoteCurrency === 'USDT' ? 2 : 8 })} ${quoteCurrency}`
  const paperWallet = { balance: current?.balance ?? 0,
    equity: current?.equity ?? 0, available: current?.balance ?? 0,
    marginUsed: current?.margin_used ?? 0, totalPnl: current?.total_pnl ?? 0,
    totalPnlPercent: current?.total_pnl_percent ?? 0 }
  const paperPerformanceData = performance.loading ? [] : performance.data?.equity_curve ?? []
  const paperTradeFeed = (trades.loading ? [] : trades.data ?? []).map((t: any) => ({
    id: t.id, action: t.side.toUpperCase(), pair: t.symbol, amount: t.quantity,
    price: t.price, pnl: t.pnl, fee: t.fee, time: t.executed_at ? new Date(t.executed_at).toLocaleString() : '—' }))
  const openPositions = (portfolio.loading ? [] : portfolio.data ?? []).map((p: any) => ({
    id: p.id, pair: p.symbol, side: p.side, size: p.quantity, entryPrice: p.average_entry_price,
    currentPrice: p.current_price, pnl: p.pnl, pnlPercent: p.pnl_percent,
    margin: p.margin, liquidation: p.liquidation_price, stop: p.stop_loss, take: p.take_profit, funding: p.funding_paid }))
  function refresh() {
    void accounts.refetch(); void account.refetch(); void portfolio.refetch(); void trades.refetch(); void performance.refetch()
  }
  useEffect(() => {
    const timer = window.setInterval(() => { if (!document.hidden) refresh() }, 15000)
    return () => window.clearInterval(timer)
  }, [accountId])
  async function act(action: 'start' | 'pause' | 'close' | 'resume' | 'tick') {
    setBusy(true); setActionError(null)
    try {
      if (action === 'start') {
        const result = await api.paperTrading.start({ strategy_id: strategyId, symbol: symbol.trim().toUpperCase(),
          timeframe, starting_balance: Number(balance), market_type: marketType,
          leverage: marketType === 'futures' ? Number(leverage) : 1,
          fee_rate: Number(fee) / 100, slippage_rate: Number(slippage) / 100,
          funding_rate: Number(funding) / 100, maintenance_margin_rate: Number(maintenance) / 100 })
        setSelectedId(result.id)
      } else if (current) {
        if (action === 'pause' || action === 'close') await api.paperTrading.stop(current.id, action === 'close')
        else if (action === 'resume') await api.paperTrading.resume(current.id)
        else await api.paperTrading.tick(current.id)
      }
      window.dispatchEvent(new Event('algoflow:update'))
      refresh()
    } catch (e) { setActionError(e instanceof Error ? e.message : 'Unable to update account'); refresh() }
    finally { setBusy(false) }
  }
  const selectStyle = 'min-h-11 w-full rounded-lg border border-border bg-background px-3 text-sm'
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Paper Trading</h2>
        <p className="text-sm text-muted-foreground">
          Practice with virtual funds — no real money at risk
        </p>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">New paper account</CardTitle></CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={e => { e.preventDefault(); void act('start') }}>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <label className="space-y-2 text-sm">Saved strategy<select aria-label="Saved strategy" required value={strategyId} onChange={e => setStrategyId(e.target.value)} className={selectStyle}>
                <option value="">Choose a saved strategy</option>
                {(strategies.data ?? []).map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select></label>
              <label className="space-y-2 text-sm">Market<select aria-label="Market" value={marketType} onChange={e => setMarketType(e.target.value as 'spot' | 'futures')} className={selectStyle}>
                <option value="spot">Spot simulation</option><option value="futures">USDT futures simulation</option>
              </select></label>
              <label className="space-y-2 text-sm">Symbol<Input required value={symbol} onChange={e => setSymbol(e.target.value)} pattern={marketType === 'futures' ? '[A-Za-z0-9]{1,12}/USDT' : '[A-Za-z0-9]{1,12}/[A-Za-z0-9]{1,12}'} className="min-h-11" /></label>
              <label className="space-y-2 text-sm">Timeframe<select aria-label="Timeframe" value={timeframe} onChange={e => setTimeframe(e.target.value)} className={selectStyle}>{['1m', '5m', '15m', '1h', '4h', '1d'].map(t => <option key={t}>{t}</option>)}</select></label>
              <label className="space-y-2 text-sm">Starting virtual balance<Input type="number" required min="1" max="1000000000" step="any" value={balance} onChange={e => setBalance(e.target.value)} className="min-h-11" /></label>
              {marketType === 'futures' && <label className="space-y-2 text-sm">Leverage (1–10x)<Input type="number" required min="1" max="10" step="1" value={leverage} onChange={e => setLeverage(e.target.value)} className="min-h-11" /></label>}
            </div>
            <details className="text-sm"><summary className="cursor-pointer py-2">Simulation assumptions</summary>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-3">
                <label className="space-y-2">Fee per fill (%)<Input type="number" required min="0" max="1" step="any" value={fee} onChange={e => setFee(e.target.value)} /></label>
                <label className="space-y-2">Slippage (%)<Input type="number" required min="0" max="1" step="any" value={slippage} onChange={e => setSlippage(e.target.value)} /></label>
                {marketType === 'futures' && <>
                  <label className="space-y-2">Funding per 8 hours (%)<Input type="number" required min="-1" max="1" step="any" value={funding} onChange={e => setFunding(e.target.value)} /></label>
                  <label className="space-y-2">Maintenance margin (%)<Input type="number" required min="0.1" max="5" step="any" value={maintenance} onChange={e => setMaintenance(e.target.value)} /></label>
                </>}
              </div>
              <p className="text-xs text-muted-foreground pt-3">Futures use isolated margin and a fixed funding scenario at 00:00, 08:00 and 16:00 UTC. Liquidation is an approximation using contract candles, a fixed maintenance ratio and closing fees. These are configurable simulation assumptions, not your exchange’s fee or liquidation schedule.</p>
            </details>
            <p className="text-xs text-muted-foreground">Spot requires Buy/Sell actions. Futures uses Open Long/Short entries and Close Position exits. Each account pins the latest saved algorithm version; later builder edits apply to a new account.</p>
            <Button type="submit" disabled={busy || !strategyId} className="min-h-11">{busy ? 'Updating…' : 'Start new paper account'}</Button>
          </form>
        </CardContent>
      </Card>
      <Card><CardContent className="pt-6 space-y-4">
        <label className="block space-y-2 text-sm">Your paper accounts<select aria-label="Your paper accounts" className={selectStyle} value={accountId} onChange={e => setSelectedId(e.target.value)} disabled={accounts.loading && !accounts.data}>
          {!accounts.data?.length && <option value="">No paper accounts yet</option>}
          {(accounts.data ?? []).map((a: any) => <option key={a.id} value={a.id}>{a.name} · {a.is_active ? 'Running' : 'Paused'} · {a.id.slice(0, 6)}</option>)}
        </select></label>
        {current && <>
          <p className="text-sm text-muted-foreground">{current.symbol} · {current.timeframe} · {current.market_type} · {current.leverage}x · {current.currency} · {current.is_active ? 'Running' : 'Paused'}</p>
          <div className="flex flex-wrap gap-3">
            <Button disabled={busy || account.loading} onClick={() => act(current.is_active ? 'pause' : 'resume')} className="min-h-11">{current.is_active ? 'Pause trading' : 'Resume trading'}</Button>
            <Button variant="outline" disabled={busy || account.loading || (!current.is_active && openPositions.length === 0)} onClick={() => act('close')} className="min-h-11">Stop & close positions</Button>
            <Button variant="outline" disabled={busy || account.loading || !current.is_active} onClick={() => act('tick')} className="min-h-11">Check strategy now</Button>
            <Button variant="ghost" disabled={busy} onClick={refresh} className="min-h-11">Refresh status</Button>
          </div>
          <p className="text-xs text-muted-foreground">Pause cancels pending orders and retains positions; simulated protection and funding wait until resume. Stop & close exits positions using public market prices and pauses the account. Both actions affect virtual funds only.</p>
          <PaperDiagnostics account={current} />
        </>}
        {!current && <p className="text-sm text-muted-foreground">{accountId ? 'Loading selected account…' : 'Save a strategy and start a paper account to see results.'}</p>}
      </CardContent></Card>
      {actionError && <p role="alert" className="text-sm text-destructive">{actionError}</p>}
      {(accounts.error || account.error || portfolio.error || trades.error || performance.error || strategies.error) && <p role="alert" className="text-sm text-destructive">{accounts.error || account.error || portfolio.error || trades.error || performance.error || strategies.error}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Virtual Balance"
          value={money(paperWallet.balance)}
          icon={<Wallet className="h-5 w-5" />}
        />
        <StatCard
          title="Total Equity"
          value={money(paperWallet.equity)}
          change={formatPercent(paperWallet.totalPnlPercent)}
          changeType={paperWallet.totalPnl >= 0 ? "positive" : "negative"}
          icon={<Activity className="h-5 w-5" />}
          delay={0.1}
        />
        <StatCard
          title="Available"
          value={money(paperWallet.available)}
          change={`Margin: ${money(paperWallet.marginUsed)}`}
          changeType="neutral"
          delay={0.2}
        />
        <StatCard
          title="Total P&L"
          value={money(paperWallet.totalPnl)}
          change={formatPercent(paperWallet.totalPnlPercent)}
          changeType={paperWallet.totalPnl >= 0 ? "positive" : "negative"}
          icon={<ArrowUpRight className="h-5 w-5" />}
          delay={0.3}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Account equity history</CardTitle>
          </CardHeader>
          <CardContent>
            {paperPerformanceData.length > 1 ? <div className="h-64 w-full"><EquityChart data={paperPerformanceData.map((point: { date: string; value: number }) => ({ ...point, date: new Date(point.date).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }))} /></div> : <p className="text-sm text-muted-foreground py-6">No performance history yet.</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Trade Feed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 max-h-[320px] overflow-y-auto">
            {paperTradeFeed.length === 0 && <p className="text-sm text-muted-foreground">No paper trades yet.</p>}
            {paperTradeFeed.map((trade, i) => (
              <motion.div
                key={trade.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-center justify-between p-3 rounded-lg bg-secondary/30"
              >
                <div className="flex items-center gap-2">
                  {trade.action === 'BUY' ? (
                    <ArrowUpRight className="h-4 w-4 text-success" />
                  ) : (
                    <ArrowDownLeft className="h-4 w-4 text-destructive" />
                  )}
                  <div>
                    <p className="text-sm font-medium">{trade.pair}</p>
                    <p className="text-xs text-muted-foreground">{trade.amount} @ {money(trade.price)} · Fee {money(trade.fee)}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={cn('text-sm font-mono', trade.pnl >= 0 ? 'text-success' : 'text-destructive')}>
                    {trade.pnl == null ? '—' : money(trade.pnl)}
                  </p>
                  <p className="text-[10px] text-muted-foreground">{trade.time}</p>
                </div>
              </motion.div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Open Positions</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Pair</TableHead>
                <TableHead>Side</TableHead>
                <TableHead className="text-right">Size</TableHead>
                <TableHead className="text-right">Entry</TableHead>
                <TableHead className="text-right">Current</TableHead>
                <TableHead className="text-right">P&L</TableHead>
                <TableHead className="text-right">Protection / Margin</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {openPositions.length === 0 && <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">No open positions.</TableCell></TableRow>}
              {openPositions.map((pos: any) => (
                <TableRow key={pos.id}>
                  <TableCell className="font-medium">{pos.pair}</TableCell>
                  <TableCell>
                    <Badge variant={pos.side === 'long' ? 'success' : 'destructive'}>
                      {pos.side.toUpperCase()}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono">{pos.size}</TableCell>
                  <TableCell className="text-right font-mono">{money(pos.entryPrice)}</TableCell>
                  <TableCell className="text-right font-mono">{pos.currentPrice == null ? '—' : money(pos.currentPrice)}</TableCell>
                  <TableCell className={cn('text-right font-mono', pos.pnl >= 0 ? 'text-success' : 'text-destructive')}>
                    {pos.pnl == null ? '—' : money(pos.pnl)} {pos.pnlPercent == null ? '' : `(${formatPercent(pos.pnlPercent)})`}
                  </TableCell>
                  <TableCell className="text-right text-xs space-y-1">
                    <p>SL: {pos.stop == null ? '—' : money(pos.stop)} · TP: {pos.take == null ? '—' : money(pos.take)}</p>
                    {current?.market_type === 'futures' && <><p>Margin: {money(pos.margin)} · Liquidation ≈ {money(pos.liquidation)}</p><p>Net funding paid: {money(pos.funding)}</p></>}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
