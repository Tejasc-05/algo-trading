import { createBrowserRouter, Navigate } from 'react-router-dom'
import { MainLayout } from '@/layouts/MainLayout'
import { AuthLayout } from '@/layouts/AuthLayout'
import { LandingPage } from '@/pages/LandingPage'
import { LoginPage, SignupPage, ForgotPasswordPage } from '@/pages/auth/AuthPages'
import { DashboardPage } from '@/pages/DashboardPage'
import { StrategyBuilderPage } from '@/pages/StrategyBuilderPage'
import { PaperTradingPage } from '@/pages/PaperTradingPage'
import { LiveTradingPage } from '@/pages/LiveTradingPage'
import { SentimentPage } from '@/pages/SentimentPage'
import { PortfolioPage } from '@/pages/PortfolioPage'
import { SettingsPage } from '@/pages/SettingsPage'

function ProtectedLayout() {
  return localStorage.getItem('access_token') ? <MainLayout /> : <Navigate to="/login" replace />
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
