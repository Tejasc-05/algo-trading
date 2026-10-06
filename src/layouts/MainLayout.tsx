import { Outlet, useLocation } from 'react-router-dom'
import { MobileNav, Sidebar } from '@/components/layout/Sidebar'
import { TopNavbar } from '@/components/layout/TopNavbar'
import { useAppStore } from '@/store/useAppStore'
import { cn } from '@/utils/cn'
import { useRealtime } from '@/hooks/useRealtime'

const pageTitles: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/strategy-builder': 'Strategy Builder',
  '/paper-trading': 'Paper Trading',
  '/live-trading': 'Live Trading',
  '/sentiment': 'Sentiment Analysis',
  '/portfolio': 'Portfolio',
  '/settings': 'Settings',
}

export function MainLayout() {
  useRealtime()
  const sidebarCollapsed = useAppStore((s) => s.sidebarCollapsed)
  const location = useLocation()
  const title = pageTitles[location.pathname]

  return (
    <div className="min-h-screen">
      <Sidebar />
      <TopNavbar title={title} />
      <main
        className={cn(
          'pt-16 pb-20 lg:pb-6 px-4 lg:px-6 transition-all duration-250 min-h-screen',
          sidebarCollapsed ? 'lg:pl-[88px]' : 'lg:pl-[276px]'
        )}
      >
        <Outlet />
      </main>
      <MobileNav />
    </div>
  )
}
