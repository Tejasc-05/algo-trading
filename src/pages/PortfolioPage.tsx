import { motion } from 'framer-motion'
import { Award, BarChart3, Percent, TrendingDown } from 'lucide-react'
import { StatCard } from '@/components/common/StatCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  EquityChart,
  MonthlyReturnsChart,
} from '@/components/charts/RechartsComponents'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'

function EmptyState({ message }: { message: string }) {
  return <p className="text-sm text-muted-foreground text-center py-10">{message}</p>
}

export function PortfolioPage() {
  const { data: portfolio, loading, error } = useApi(() => api.portfolio.get())
  const { data: performance, loading: perfLoading, error: performanceError } = useApi(() => api.portfolio.performance())

  const stats = portfolio ? { ...portfolio, win_rate: performance?.win_rate_pct,
    sharpe_ratio: performance?.sharpe_ratio, max_drawdown: performance?.max_drawdown_pct } : null
  const equityData = performance?.equity_curve ?? []
  const monthlyData = performance?.monthly_returns ?? []

  return (
    <div className="space-y-6">
      {(error || performanceError) && <p role="alert" className="text-sm text-destructive">{error || performanceError}</p>}
      <div>
        <h2 className="text-2xl font-bold">Portfolio Analytics</h2>
        <p className="text-sm text-muted-foreground">
          Institutional-grade performance metrics and risk analysis
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Win Rate"
          value={stats?.win_rate != null ? `${stats.win_rate}%` : '—'}
          change={stats?.win_rate != null ? 'Based on your trades' : 'No data yet'}
          changeType="positive"
          icon={<Percent className="h-5 w-5" />}
        />
        <StatCard
          title="Sharpe Ratio"
          value={stats?.sharpe_ratio != null ? String(stats.sharpe_ratio) : '—'}
          change="Risk-adjusted return"
          changeType="positive"
          icon={<Award className="h-5 w-5" />}
          delay={0.1}
        />
        <StatCard
          title="Max Drawdown"
          value={stats?.max_drawdown != null ? `${stats.max_drawdown}%` : '—'}
          change={stats?.max_drawdown != null ? 'Historical peak-to-trough' : 'No data yet'}
          changeType="neutral"
          icon={<TrendingDown className="h-5 w-5" />}
          delay={0.2}
        />
        <StatCard
          title="Total Return"
          value={stats?.total_return_pct != null ? `${stats.total_return_pct > 0 ? '+' : ''}${stats.total_return_pct}%` : '—'}
          change="All-time"
          changeType={stats?.total_return_pct != null && stats.total_return_pct >= 0 ? 'positive' : 'negative'}
          icon={<BarChart3 className="h-5 w-5" />}
          delay={0.3}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Equity Curve</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="h-[300px] flex items-center justify-center text-muted-foreground text-sm">Loading…</div>
          ) : equityData.length > 1 ? (
            <EquityChart data={equityData} className="min-h-[300px]" />
          ) : (
            <EmptyState message="No equity data yet. Start paper trading to build your equity curve." />
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Monthly Returns</CardTitle>
          </CardHeader>
          <CardContent>
            {perfLoading ? (
              <div className="h-48 flex items-center justify-center text-muted-foreground text-sm">Loading…</div>
            ) : monthlyData.length > 0 ? (
              <MonthlyReturnsChart data={monthlyData} />
            ) : (
              <EmptyState message="No monthly return data yet." />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Risk Metrics</CardTitle>
          </CardHeader>
          <CardContent>
            {stats ? (
              <div className="space-y-4">
                {[
                  { label: 'Win Rate', value: stats.win_rate != null ? `${stats.win_rate}%` : '—', desc: 'Profitable trades / total trades' },
                  { label: 'Sharpe Ratio', value: stats.sharpe_ratio ?? '—', desc: 'Risk-adjusted return' },
                  { label: 'Max Drawdown', value: stats.max_drawdown != null ? `${stats.max_drawdown}%` : '—', desc: 'Largest peak-to-trough drop' },
                  { label: 'Total Trades', value: stats.total_trades ?? 0, desc: 'Completed trades' },
                  { label: 'Avg Trade P&L', value: stats.avg_trade != null ? `$${stats.avg_trade}` : '—', desc: 'Average profit/loss per trade' },
                  { label: 'Total Return', value: stats.total_return_pct != null ? `${stats.total_return_pct}%` : '—', desc: 'All-time return' },
                ].map((metric, i) => (
                  <motion.div
                    key={metric.label}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="flex items-center justify-between py-3 border-b border-border last:border-0"
                  >
                    <div>
                      <p className="text-sm font-medium">{metric.label}</p>
                      <p className="text-xs text-muted-foreground">{metric.desc}</p>
                    </div>
                    <span className="text-sm font-mono font-semibold text-primary">{String(metric.value)}</span>
                  </motion.div>
                ))}
              </div>
            ) : (
              <EmptyState message="No risk metrics available yet. Make some trades to see analytics." />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
