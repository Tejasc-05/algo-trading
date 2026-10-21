import { createBrowserRouter, Navigate } from 'react-router-dom'
import { MainLayout } from '@/layouts/MainLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { LandingPage } from '@/pages/LandingPage'
import { LoginPage, SignupPage, ForgotPasswordPage, ResetPasswordPage } from '@/pages/auth/AuthPages'
import { DashboardPage } from '@/pages/DashboardPage'
import { StrategyBuilderPage } from '@/pages/StrategyBuilderPage'
import { PaperTradingPage } from '@/pages/PaperTradingPage'
import { LiveTradingPage } from '@/pages/LiveTradingPage'
import { SentimentPage } from '@/pages/SentimentPage'
import { PortfolioPage } from '@/pages/PortfolioPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'
import { VerifyEmailPage } from '@/pages/auth/VerifyEmailPage'

function ProtectedLayout() {
  const [state, setState] = useState<'loading' | 'ready' | 'signed-out' | 'error'>('loading')
  useEffect(() => {
    let active = true
    api.auth.session().then(({ user }) => {
      if (!active) return
      useAppStore.getState().setUser({ name: user.full_name || '', email: user.email })
      setState('ready')
    }).catch(error => { if (active) setState(error.status === 401 ? 'signed-out' : 'error') })
    return () => { active = false }
  }, [])
  if (state === 'loading') return <p role="status" className="p-6">Checking your session…</p>
  if (state === 'error') return <div className="p-6" role="alert">Unable to check your session. <button onClick={() => window.location.reload()}>Retry</button></div>
  return state === 'ready' ? <MainLayout /> : <Navigate to="/login" replace />
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <LandingPage />,
  },
  {
    element: <AuthLayout />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/signup', element: <SignupPage /> },
      { path: '/forgot-password', element: <ForgotPasswordPage /> },
      { path: '/reset-password', element: <ResetPasswordPage /> },
      { path: '/verify-email', element: <VerifyEmailPage /> },
    ],
  },
  {
    element: <ProtectedLayout />,
    children: [
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/strategy-builder', element: <StrategyBuilderPage /> },
      { path: '/paper-trading', element: <PaperTradingPage /> },
      { path: '/live-trading', element: <LiveTradingPage /> },
      { path: '/sentiment', element: <SentimentPage /> },
      { path: '/portfolio', element: <PortfolioPage /> },
      { path: '/settings', element: <SettingsPage /> },
    ],
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
])
