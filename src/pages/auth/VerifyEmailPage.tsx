import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'

export function VerifyEmailPage() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') || '')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  return <div className="space-y-4">
    <h1 className="text-2xl font-bold">Verify your email</h1>
    <p className="text-sm text-muted-foreground">Sign in to the same account, then confirm this verification link. You can sign in in another tab and return here.</p>
    <Link to="/login" target="_blank" rel="noopener noreferrer" className="text-primary underline">Open sign in</Link>
    <Button className="w-full" disabled={busy || !token || !!message} onClick={async () => {
      if (busy) return
      setBusy(true); setError('')
      try {
        await api.auth.session()
        const result = await api.security.verifyEmail(token)
        window.history.replaceState(null, '', window.location.pathname)
        setMessage(result.message)
      } catch (e) { setError(e instanceof Error ? e.message : 'Unable to verify this email.') }
      finally { setBusy(false) }
    }}>{busy ? 'Verifying…' : 'Verify email address'}</Button>
    {!token && <p role="alert">Open the complete link from your verification email.</p>}
    {error && <p role="alert" className="text-destructive text-sm">{error}</p>}
    {message && <p role="status" className="text-success text-sm">{message} <Link to="/settings" className="underline">Return to settings</Link></p>}
  </div>
}
