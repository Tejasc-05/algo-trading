import { motion } from 'framer-motion'
import {
  Activity,
  BarChart3,
  Bot,
  ChevronLeft,
  LayoutDashboard,
  Newspaper,
  Settings,
  TrendingUp,
  Wallet,
  Workflow,
  Zap,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '@/utils/cn'
import { useAppStore } from '@/store/useAppStore'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/strategy-builder', icon: Workflow, label: 'Strategy Builder' },
  { to: '/paper-trading', icon: Activity, label: 'Paper Trading' },
  { to: '/live-trading', icon: Zap, label: 'Live Trading' },
  { to: '/sentiment', icon: Newspaper, label: 'Sentiment Analysis' },
  { to: '/portfolio', icon: BarChart3, label: 'Portfolio' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useAppStore()
  const usage = useApi(() => api.paperTrading.getUsage())

  return (
    <motion.aside
      initial={false}
      animate={{ width: sidebarCollapsed ? 72 : 260 }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
      className="fixed left-0 top-0 z-40 hidden lg:flex h-screen flex-col border-r border-border glass-strong"
    >
      <div className="flex h-16 items-center gap-3 px-4 border-b border-border">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-cyan-500 to-purple-600">
          <Bot className="h-5 w-5 text-white" />
        </div>
        {!sidebarCollapsed && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="overflow-hidden">
            <span className="font-bold text-lg tracking-tight">AlgoFlow</span>
            <p className="text-[10px] text-muted-foreground -mt-0.5">AI Trading Platform</p>
          </motion.div>
        )}
      </div>

      <nav className="flex-1 space-y-1 p-3 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-primary/10 text-primary border border-primary/20'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
              )
            }
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {!sidebarCollapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-border p-3">
        {!sidebarCollapsed && (
          <div className="glass rounded-lg p-3 mb-3">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="h-4 w-4 text-success" />
              <span className="text-xs font-medium">Paper Trading</span>
            </div>
            <p className="text-[11px] text-muted-foreground" aria-live="polite">
              {usage.error ? 'Active bots unavailable' : usage.data
                ? `${usage.data.active_bots} active ${usage.data.active_bots === 1 ? 'bot' : 'bots'}`
                : 'Loading active bots…'}
            </p>
          </div>
        )}
        <button
          onClick={toggleSidebar}
          className="flex w-full items-center justify-center rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors cursor-pointer"
        >
          <ChevronLeft className={cn('h-5 w-5 transition-transform', sidebarCollapsed && 'rotate-180')} />
        </button>
      </div>
    </motion.aside>
  )
}

export function MobileNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around border-t border-border glass-strong py-2 lg:hidden">
      {navItems.slice(0, 5).map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          className={({ isActive }) =>
            cn(
              'flex flex-col items-center gap-0.5 px-2 py-1 text-[10px]',
              isActive ? 'text-primary' : 'text-muted-foreground'
            )
          }
        >
          <item.icon className="h-5 w-5" />
          <span>{item.label.split(' ')[0]}</span>
        </NavLink>
      ))}
      <NavLink
        to="/portfolio"
        className={({ isActive }) =>
          cn(
            'flex flex-col items-center gap-0.5 px-2 py-1 text-[10px]',
            isActive ? 'text-primary' : 'text-muted-foreground'
          )
        }
      >
        <Wallet className="h-5 w-5" />
        <span>Portfolio</span>
      </NavLink>
    </nav>
  )
}
