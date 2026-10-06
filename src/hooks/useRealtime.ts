import { useEffect } from 'react'

/** One socket per authenticated layout. Tokens do not appear in request URLs. */
export function useRealtime() {
  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) return
    let stopped = false
    let socket: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | undefined
    let delay = 1000
    const connect = () => {
      const base = new URL(import.meta.env.VITE_API_BASE || '/api', window.location.origin)
      base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
      base.pathname = '/ws'; base.search = ''
      socket = new WebSocket(base, ['algoflow', token])
      socket.onopen = () => { delay = 1000 }
      socket.onmessage = () => window.dispatchEvent(new Event('algoflow:update'))
      socket.onclose = (event) => {
        if (!stopped && event.code !== 1008) {
          retry = setTimeout(connect, delay)
          delay = Math.min(delay * 2, 30000)
        }
      }
      socket.onerror = () => socket?.close()
    }
    connect()
    return () => { stopped = true; clearTimeout(retry); socket?.close() }
  }, [])
}
