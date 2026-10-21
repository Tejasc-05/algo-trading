import { create } from 'zustand'
import { useStrategyStore } from './useStrategyStore'

interface User {
  name: string
  email: string
  avatar?: string
  plan: 'free' | 'pro' | 'enterprise'
}

interface Notification {
  id: string
  title: string
  message: string
  time: string
  read: boolean
  type: 'trade' | 'alert' | 'system'
}

interface AppState {
  sidebarCollapsed: boolean
  marketOpen: boolean
  user: User
  notifications: Notification[]
  searchTerm: string
  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setUser: (user: Partial<User>) => void
  logout: () => void
  markNotificationRead: (id: string) => void
  setSearchTerm: (value: string) => void
}

export const useAppStore = create<AppState>((set) => ({
  sidebarCollapsed: false,
  marketOpen: true,
  user: { name: '', email: '', plan: 'free' },
  notifications: [],
  searchTerm: '',
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
  setUser: (u) => set((s) => ({ user: { ...s.user, ...u } })),
  logout: () => {
    useStrategyStore.getState().reset()
    localStorage.removeItem('access_token')
    localStorage.removeItem('user')
    set({ user: { name: '', email: '', plan: 'free' }, notifications: [], searchTerm: '' })
  },
  markNotificationRead: (id) =>
    set((s) => ({
      notifications: s.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      ),
    })),
  setSearchTerm: (value) => set({ searchTerm: value }),
}))
