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
import { useState } from 'react'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { formatCurrency, formatPercent } from '@/utils/formatters'
import { cn } from '@/utils/cn'

export function PaperTradingPage() {
  const account = useApi(() => api.paperTrading.getAccount())
  const portfolio = useApi(() => api.portfolio.get())
  const performance = useApi(() => api.portfolio.performance())
  const trades = useApi(() => api.paperTrading.getTrades())
  const strategies = useApi(() => api.strategies.list())
  const [strategyId, setStrategyId] = useState('')
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const paperWallet = { balance: account.data?.balance ?? 0,
    equity: account.data?.equity ?? 0, available: account.data?.balance ?? 0,
    marginUsed: 0, totalPnl: account.data?.total_pnl ?? 0,
    totalPnlPercent: account.data?.total_pnl_percent ?? 0 }
  const paperPerformanceData = performance.data?.equity_curve ?? []
  const paperTradeFeed = (trades.data ?? []).map((t: any) => ({
    id: t.id, action: t.side.toUpperCase(), pair: t.symbol, amount: t.quantity,
    price: t.price, pnl: t.pnl, time: t.executed_at ? new Date(t.executed_at).toLocaleString() : '—' }))
  const openPositions = (portfolio.data?.positions ?? []).map((p: any) => ({
    id: p.id, pair: p.symbol, side: p.side, size: p.quantity, entryPrice: p.average_entry_price,
    currentPrice: p.current_price, pnl: p.pnl, pnlPercent: p.pnl_percent }))
  async function toggleAccount() {
    setBusy(true); setActionError(null)
    try {
      if (account.data?.is_active) await api.paperTrading.stop(account.data.id)
      else await api.paperTrading.start({ strategy_id: strategyId, symbol: 'BTC/USDT' })
      window.dispatchEvent(new Event('algoflow:update'))
      account.refetch(); portfolio.refetch(); trades.refetch(); performance.refetch()
    } catch (e) { setActionError(e instanceof Error ? e.message : 'Unable to update account') }
    finally { setBusy(false) }
  }
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Paper Trading</h2>
        <p className="text-sm text-muted-foreground">
          Practice with virtual funds — no real money at risk
        </p>
      </div>

      <div className="flex items-center gap-3">
        {!account.data?.is_active && <select aria-label="Saved strategy" value={strategyId} onChange={e => setStrategyId(e.target.value)} className="rounded-lg border border-border bg-background p-2 text-sm">
          <option value="">Choose a saved strategy</option>
          {(strategies.data ?? []).map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>}
        <Button disabled={busy || (!account.data?.is_active && !strategyId)} onClick={toggleAccount}>
          {busy ? 'Updating…' : account.data?.is_active ? 'Stop Paper Trading' : 'Start Paper Trading'}
        </Button>
        <p className="text-sm text-muted-foreground">{account.loading ? 'Loading account…' : account.data ? 'Your paper account' : 'No paper account yet'}</p>
      </div>
      {actionError && <p role="alert" className="text-sm text-destructive">{actionError}</p>}
      {(portfolio.error || trades.error) && <p role="alert" className="text-sm text-destructive">{portfolio.error || trades.error}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Virtual Balance"
          value={formatCurrency(paperWallet.balance)}
          icon={<Wallet className="h-5 w-5" />}
        />
        <StatCard
          title="Total Equity"
          value={formatCurrency(paperWallet.equity)}
          change={formatPercent(paperWallet.totalPnlPercent)}
          changeType="positive"
          icon={<Activity className="h-5 w-5" />}
          delay={0.1}
        />
        <StatCard
          title="Available"
          value={formatCurrency(paperWallet.available)}
          change={`Margin: ${formatCurrency(paperWallet.marginUsed)}`}
          changeType="neutral"
          delay={0.2}
        />
        <StatCard
          title="Total P&L"
          value={formatCurrency(paperWallet.totalPnl)}
          change={formatPercent(paperWallet.totalPnlPercent)}
          changeType="positive"
          icon={<ArrowUpRight className="h-5 w-5" />}
          delay={0.3}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Performance</CardTitle>
          </CardHeader>
          <CardContent>
            {paperPerformanceData.length > 1 ? <EquityChart data={paperPerformanceData} /> : <p className="text-sm text-muted-foreground py-6">No performance history yet.</p>}
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
                    <p className="text-xs text-muted-foreground">{trade.amount} @ {formatCurrency(trade.price)}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={cn('text-sm font-mono', trade.pnl >= 0 ? 'text-success' : 'text-destructive')}>
                    {trade.pnl == null ? '—' : formatCurrency(trade.pnl)}
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {openPositions.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">No open positions.</TableCell></TableRow>}
              {openPositions.map((pos: any) => (
                <TableRow key={pos.id}>
                  <TableCell className="font-medium">{pos.pair}</TableCell>
                  <TableCell>
                    <Badge variant={pos.side === 'long' ? 'success' : 'destructive'}>
                      {pos.side.toUpperCase()}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono">{pos.size}</TableCell>
                  <TableCell className="text-right font-mono">{formatCurrency(pos.entryPrice)}</TableCell>
                  <TableCell className="text-right font-mono">{pos.currentPrice == null ? '—' : formatCurrency(pos.currentPrice)}</TableCell>
                  <TableCell className={cn('text-right font-mono', pos.pnl >= 0 ? 'text-success' : 'text-destructive')}>
                    {pos.pnl == null ? '—' : formatCurrency(pos.pnl)} {pos.pnlPercent == null ? '' : `(${formatPercent(pos.pnlPercent)})`}
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
