import { useEffect } from 'react'
import { api } from '@/lib/api'
import { redirectToLogin } from '@/lib/session'

/** One cookie-authenticated socket per protected layout. */
export function useRealtime() {
  useEffect(() => {
    let stopped = false
    let socket: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    let delay = 1000
    const connect = () => {
      const base = new URL(import.meta.env.VITE_API_BASE || '/api', window.location.origin)
      base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
      base.pathname = '/ws'; base.search = ''
      const current = new WebSocket(base, ['algoflow'])
      socket = current
      current.onopen = () => { delay = 1000 }
      current.onmessage = () => window.dispatchEvent(new Event('algoflow:update'))
      current.onclose = async (event) => {
        if (!stopped && event.code === 1008) {
          // MFA rotates the cookie; the old socket must close, but the browser
          // may already hold a valid replacement session.
          try { await api.auth.session() }
          catch (error) {
            if (error instanceof api.ApiError && error.status === 401) {
              if (!stopped) redirectToLogin()
              return
            }
          }
        }
        if (!stopped) {
          retry = setTimeout(connect, delay)
          delay = Math.min(delay * 2, 30000)
        }
      }
      current.onerror = () => current.close()
    }
    connect()
    return () => { stopped = true; clearTimeout(retry); socket?.close() }
  }, [])
}
