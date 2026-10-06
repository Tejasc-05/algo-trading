import { motion } from 'framer-motion'
import { Bot, DollarSign, TrendingDown, TrendingUp, Wallet } from 'lucide-react'
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
import { DashboardSkeleton } from '@/components/common/LoadingSkeleton'
import { formatCurrency, formatPercent } from '@/utils/formatters'
import { cn } from '@/utils/cn'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'

function EmptyState({ message }: { message: string }) {
  return (
    <p className="text-sm text-muted-foreground text-center py-6">{message}</p>
  )
}

export function DashboardPage() {
  const { data: portfolio, loading: portfolioLoading, error: portfolioError } = useApi(() => api.portfolio.get())
  const { data: strategies, loading: strategiesLoading, error: strategiesError } = useApi(() => api.strategies.list())
  const { data: trades, loading: tradesLoading, error: tradesError } = useApi(() => api.paperTrading.getTrades())

  const { data: performance } = useApi(() => api.portfolio.performance())
  const loading = portfolioLoading || strategiesLoading || tradesLoading

  if (loading) return <DashboardSkeleton />

  const stats = portfolio ?? null
  const equityData = performance?.equity_curve ?? []

  return (
    <div className="space-y-6">
      {(portfolioError || strategiesError || tradesError) && <p role="alert" className="text-sm text-destructive">{portfolioError || strategiesError || tradesError}</p>}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        <StatCard
          title="Portfolio Value"
          value={stats ? formatCurrency(stats.total_value ?? 0) : '$0.00'}
          change={stats ? formatPercent(stats.daily_pnl_percent ?? 0) : '—'}
          changeType={stats && (stats.daily_pnl_percent ?? 0) >= 0 ? 'positive' : 'negative'}
          icon={<Wallet className="h-5 w-5" />}
          delay={0}
        />
        <StatCard
          title="Daily P&L"
          value={stats ? formatCurrency(stats.daily_pnl ?? 0) : '$0.00'}
          change={stats ? formatPercent(stats.daily_pnl_percent ?? 0) : '—'}
          changeType={stats && (stats.daily_pnl ?? 0) >= 0 ? 'positive' : 'negative'}
          icon={<DollarSign className="h-5 w-5" />}
          delay={0.1}
        />
        <StatCard
          title="Weekly P&L"
          value={stats?.weekly_pnl != null ? formatCurrency(stats.weekly_pnl) : '—'}
          change={stats?.weekly_pnl_percent != null ? formatPercent(stats.weekly_pnl_percent) : '—'}
          changeType={stats && (stats.weekly_pnl ?? 0) >= 0 ? 'positive' : 'negative'}
          icon={<TrendingUp className="h-5 w-5" />}
          delay={0.2}
        />
        <StatCard
          title="Strategies"
          value={String(strategies?.length ?? 0)}
          change={strategies?.length ? `${strategies.length} total` : 'No strategies yet'}
          changeType="neutral"
          icon={<Bot className="h-5 w-5" />}
          delay={0.3}
        />
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Portfolio Equity Curve</CardTitle>
          </CardHeader>
          <CardContent>
            {equityData.length > 1 ? (
              <EquityChart data={equityData} />
            ) : (
              <EmptyState message="No equity data yet — start paper trading to see your equity curve." />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">My Strategies</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {!strategies || strategies.length === 0 ? (
              <EmptyState message="No strategies yet. Go to Strategy Builder to create one." />
            ) : (
              strategies.slice(0, 5).map((s: any) => (
                <div key={s.id} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                  <div>
                    <p className="text-sm font-medium">{s.name}</p>
                    <p className="text-xs text-muted-foreground">{s.description || 'No description'}</p>
                  </div>
                  <Badge variant="secondary" className="text-[10px]">
                    {s.status ?? 'draft'}
                  </Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Paper Trades</CardTitle>
        </CardHeader>
        <CardContent>
          {!trades || trades.length === 0 ? (
            <EmptyState message="No trades yet. Start paper trading to see your history here." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pair</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">P&L</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trades.slice(0, 10).map((trade: any) => (
                  <TableRow key={trade.id}>
                    <TableCell className="font-medium">{trade.symbol}</TableCell>
                    <TableCell>
                      <Badge variant={trade.side === 'buy' ? 'success' : 'destructive'} className="text-[10px]">
                        {trade.side?.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono">{trade.quantity}</TableCell>
                    <TableCell className="text-right font-mono">{formatCurrency(trade.price ?? 0)}</TableCell>
                    <TableCell className={cn('text-right font-mono', (trade.pnl ?? 0) >= 0 ? 'text-success' : 'text-destructive')}>
                      {(trade.pnl ?? 0) >= 0 ? '+' : ''}{formatCurrency(trade.pnl ?? 0)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {stats?.max_drawdown !== undefined && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Risk Summary</CardTitle>
            <div className="flex items-center gap-1 text-sm text-destructive">
              <TrendingDown className="h-4 w-4" />
              Max DD: {formatPercent(stats.max_drawdown)}
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground text-xs">Win Rate</p>
                <p className="font-mono font-semibold">{stats.win_rate ?? 0}%</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Sharpe Ratio</p>
                <p className="font-mono font-semibold">{stats.sharpe_ratio ?? '—'}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Total Trades</p>
                <p className="font-mono font-semibold">{stats.total_trades ?? 0}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Avg Trade</p>
                <p className="font-mono font-semibold">{formatCurrency(stats.avg_trade ?? 0)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
