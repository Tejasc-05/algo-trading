import { Bell, Circle } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { GlobalSearch } from '@/components/layout/GlobalSearch'
import { useAppStore } from '@/store/useAppStore'
import { cn } from '@/utils/cn'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useState } from 'react'
import { redirectToLogin } from '@/lib/session'

interface TopNavbarProps {
  title?: string
}

export function TopNavbar({ title }: TopNavbarProps) {
  const { sidebarCollapsed, marketOpen, user, notifications } = useAppStore()
  const unreadCount = notifications.filter((n) => !n.read).length
  const [signingOut, setSigningOut] = useState(false)
  const [signOutError, setSignOutError] = useState('')

  return (
    <header
      className={cn(
        'fixed top-0 right-0 z-30 flex h-16 items-center justify-between border-b border-border glass-strong px-4 lg:px-6 transition-all duration-250',
        sidebarCollapsed ? 'left-[72px]' : 'left-[260px]',
        'max-lg:left-0'
      )}
    >
      <div className="flex items-center gap-4">
        {title && <h1 className="text-lg font-semibold hidden sm:block">{title}</h1>}
        <div className="flex items-center gap-2">
          <Circle className={cn('h-2 w-2 fill-current', marketOpen ? 'text-success' : 'text-destructive')} />
          <span className="text-xs text-muted-foreground hidden md:inline">
            {marketOpen ? 'Paper Mode' : 'Disconnected'}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <GlobalSearch />
        <Button variant="ghost" size="sm" disabled={signingOut} onClick={async () => {
          setSigningOut(true); setSignOutError('')
          try { await api.auth.logout(); useAppStore.getState().logout(); redirectToLogin() }
          catch { setSignOutError('Sign out failed. Try again.'); setSigningOut(false) }
        }}>{signingOut ? 'Signing out…' : 'Sign out'}</Button>
        {signOutError && <span role="alert" className="text-xs text-destructive">{signOutError}</span>}

        <button className="relative rounded-lg p-2 text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors cursor-pointer">
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">
              {unreadCount}
            </span>
          )}
        </button>

        <div className="flex items-center gap-2 pl-2 border-l border-border">
          <Avatar className="h-8 w-8">
            <AvatarFallback className="text-xs">
              {user.name.split(' ').map((n) => n[0]).join('')}
            </AvatarFallback>
          </Avatar>
          <div className="hidden lg:block">
            <p className="text-sm font-medium leading-none">{user.name}</p>
            <Badge variant="default" className="mt-1 text-[10px] px-1.5 py-0">
              {user.plan.toUpperCase()}
            </Badge>
          </div>
        </div>
      </div>
    </header>
  )
}
