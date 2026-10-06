import { Bell, Circle, Search } from 'lucide-react'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { useAppStore } from '@/store/useAppStore'
import { cn } from '@/utils/cn'

interface TopNavbarProps {
  title?: string
}

export function TopNavbar({ title }: TopNavbarProps) {
  const { sidebarCollapsed, marketOpen, user, notifications, searchTerm, setSearchTerm } = useAppStore()
  const unreadCount = notifications.filter((n) => !n.read).length

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
        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="Search strategies, pairs..."
            className="w-64 pl-9 h-9 bg-secondary/30"
          />
          {searchTerm && (
            <span className="absolute -bottom-5 left-0 text-[10px] text-muted-foreground">
              {searchTerm.length > 0 ? `Filtering for: ${searchTerm}` : ''}
            </span>
          )}
        </div>

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
