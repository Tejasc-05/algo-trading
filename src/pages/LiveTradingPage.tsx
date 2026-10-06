import { motion } from 'framer-motion'
import { Bot, CheckCircle2, Key, Link2, Pause, Play, XCircle, Zap } from 'lucide-react'
import { StatCard } from '@/components/common/StatCard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'
import { useState } from 'react'
import { formatCurrency } from '@/utils/formatters'
import { cn } from '@/utils/cn'
import { FuturesDemoPanel } from '@/features/strategy-builder/FuturesDemoPanel'

export function LiveTradingPage() {
  const connections = useApi(() => api.exchanges.list())
  const exchangeConnections = (connections.data ?? []).map((e: any) => ({
    id: e.id, name: e.label || e.exchange_name, logo: e.exchange_name[0].toUpperCase(),
    connected: e.is_active, status: e.is_testnet ? 'Sandbox credentials saved' : 'Credentials saved' }))
  const activeBots: { id: string; name: string; strategy: string; status: string; trades: number; pnl: number }[] = []
  const liveTradeFeed: { id: string; pair: string; bot: string; action: string; price: number; time: string }[] = []
  const [connectError, setConnectError] = useState<string | null>(null)
  const [connecting, setConnecting] = useState(false)
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Live Trading</h2>
          <p className="text-sm text-muted-foreground">
            Save exchange connections. Real order execution is not available yet.
          </p>
        </div>
        <Button variant="gradient" disabled title="Live execution is disabled">
          <Zap className="h-4 w-4" />
          Deploy New Bot
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard title="Active Strategies" value="0" change="Live execution disabled" changeType="neutral" icon={<Bot className="h-5 w-5" />} />
        <StatCard title="Connected Exchanges" value={String(exchangeConnections.length)} change="Saved connections" changeType="neutral" icon={<Link2 className="h-5 w-5" />} delay={0.1} />
        <StatCard title="Live P&L Today" value="—" change="Live execution disabled" changeType="positive" icon={<Zap className="h-5 w-5" />} delay={0.2} />
      </div>

      <FuturesDemoPanel />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Active Strategies</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">No live bots. Real execution is disabled.</p>
            {activeBots.filter((b) => b.status !== 'stopped').map((bot) => (
              <div key={bot.id} className="flex items-center justify-between p-4 rounded-lg bg-secondary/30">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-lg',
                    bot.status === 'running' ? 'bg-success/10' : 'bg-warning/10'
                  )}>
                    <Bot className={cn('h-5 w-5', bot.status === 'running' ? 'text-success' : 'text-warning')} />
                  </div>
                  <div>
                    <p className="text-sm font-medium">{bot.name}</p>
                    <p className="text-xs text-muted-foreground">{bot.trades} trades · {bot.strategy}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <p className={cn('text-sm font-mono', bot.pnl >= 0 ? 'text-success' : 'text-destructive')}>
                      {bot.pnl >= 0 ? '+' : ''}{formatCurrency(bot.pnl)}
                    </p>
                    <Badge variant={bot.status === 'running' ? 'success' : 'warning'} className="text-[10px] mt-1">
                      {bot.status}
                    </Badge>
                  </div>
                  <Button variant="ghost" size="icon">
                    {bot.status === 'running' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Live Trade Feed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[340px] overflow-y-auto">
            <p className="text-sm text-muted-foreground">No live trades.</p>
            {liveTradeFeed.map((trade, i) => (
              <motion.div
                key={trade.id}
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-center justify-between p-3 rounded-lg bg-secondary/20 border border-border/50"
              >
                <div>
                  <p className="text-sm font-medium">{trade.pair}</p>
                  <p className="text-xs text-muted-foreground">{trade.bot}</p>
                </div>
                <div className="text-right">
                  <Badge variant={trade.action === 'BUY' ? 'success' : 'destructive'} className="text-[10px]">
                    {trade.action}
                  </Badge>
                  <p className="text-xs font-mono mt-1">{formatCurrency(trade.price)}</p>
                </div>
                <span className="text-[10px] text-muted-foreground">{trade.time}</span>
              </motion.div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Exchange Connections</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {connections.error && <p role="alert" className="text-destructive text-sm">{connections.error}</p>}
            {exchangeConnections.length === 0 && <p className="text-sm text-muted-foreground">No exchange connections saved.</p>}
            {exchangeConnections.map((exchange) => (
              <div key={exchange.id} className="flex items-center justify-between p-4 rounded-lg bg-secondary/30">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 font-bold text-primary">
                    {exchange.logo}
                  </div>
                  <div>
                    <p className="text-sm font-medium">{exchange.name}</p>
                    <div className="flex items-center gap-1 mt-0.5">
                      {exchange.connected ? (
                        <CheckCircle2 className="h-3 w-3 text-success" />
                      ) : (
                        <XCircle className="h-3 w-3 text-muted-foreground" />
                      )}
                      <span className="text-xs text-muted-foreground capitalize">{exchange.status}</span>
                    </div>
                  </div>
                </div>
                <Switch checked={exchange.connected} disabled />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Key className="h-4 w-4" />
              Add Exchange API Key
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={async (e) => {
              e.preventDefault(); const form = e.currentTarget; const fields = new FormData(form)
              setConnecting(true); setConnectError(null)
              try {
                await api.exchanges.connect({ exchange_name: String(fields.get('exchange_name')),
                  api_key: String(fields.get('api_key')), api_secret: String(fields.get('api_secret')), is_testnet: true })
                form.reset(); connections.refetch()
              } catch (error) { setConnectError(error instanceof Error ? error.message : 'Unable to save connection') }
              finally { setConnecting(false) }
            }}>
              <div className="space-y-2">
                <Label>Exchange</Label>
                <Input name="exchange_name" required placeholder="CCXT exchange id, e.g. binance" />
              </div>
              <div className="space-y-2">
                <Label>API Key</Label>
                <Input name="api_key" required type="password" placeholder="Enter API key" />
              </div>
              <div className="space-y-2">
                <Label>API Secret</Label>
                <Input name="api_secret" required type="password" placeholder="Enter API secret" />
              </div>
              <Button variant="gradient" className="w-full" disabled={connecting}>{connecting ? "Saving…" : "Save Sandbox Connection"}</Button>
              {connectError && <p role="alert" className="text-destructive text-sm">{connectError}</p>}
              <p className="text-[11px] text-muted-foreground text-center">
                API credentials are encrypted at rest. Saving credentials does not enable live trading.
              </p>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
