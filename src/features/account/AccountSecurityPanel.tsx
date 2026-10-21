import { useState } from 'react'
import { useApi } from '@/hooks/useApi'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function AccountSecurityPanel() {
  const status = useApi(() => api.security.status())
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [secret, setSecret] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  async function perform(action: () => Promise<{ message?: string }>) {
    if (busy) return
    setBusy(true); setMessage(''); setError('')
    try { const result = await action(); setMessage(result.message || 'Security settings updated.'); status.refetch() }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to update security settings.') }
    finally { setBusy(false); setPassword(''); setCode('') }
  }
  return <section className="space-y-4" aria-label="Account verification and MFA">
    {status.error && <p role="alert" className="text-sm text-destructive">{status.error}</p>}
    <p className="text-sm">Email: {status.loading ? 'Checking…' : status.data?.email_verified ? 'Verified' : 'Verification required'}</p>
    <Button variant="outline" disabled={busy || status.loading || !!status.data?.email_verified}
      onClick={() => perform(() => api.security.requestEmail())}>Send verification email</Button>
    <p className="text-sm">Authenticator: {status.loading ? 'Checking…' : status.data?.mfa_enabled ? 'Enabled' : 'Not enabled'}</p>
    {!status.data?.mfa_enabled && <p className="text-xs text-muted-foreground">Keep your authenticator backed up. Self-service MFA recovery is not available yet; password reset keeps MFA enabled.</p>}
    <form className="space-y-3" onSubmit={e => {
      e.preventDefault()
      void perform(async () => {
        if (status.data?.mfa_enabled) return api.security.stepUp(password, code)
        if (secret) { const result = await api.security.confirmMfa(code); setSecret(''); return result }
        const result = await api.security.enrollMfa(password); setSecret(result.secret)
        return { message: 'Add the setup key to your authenticator app, then enter its six-digit code to confirm.' }
      })
    }}>
      {(!secret || status.data?.mfa_enabled) && <div className="space-y-2"><Label htmlFor="security-password">Current password</Label>
        <Input id="security-password" type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e => setPassword(e.target.value)} disabled={busy || status.loading} /></div>}
      {secret && <div className="space-y-2"><Label htmlFor="authenticator-secret">Authenticator setup key</Label>
        <Input id="authenticator-secret" readOnly value={secret} autoComplete="off" />
        <p className="text-xs text-muted-foreground">Choose “Enter a setup key” in your authenticator, select time-based codes, and use this key. It expires in ten minutes.</p></div>}
      {(secret || status.data?.mfa_enabled) && <div className="space-y-2"><Label htmlFor="security-code">Authenticator code</Label>
        <Input id="security-code" inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{6}" maxLength={6} value={code} onChange={e => setCode(e.target.value)} disabled={busy} /></div>}
      <Button type="submit" variant="outline" disabled={busy || status.loading || !!status.error}>
        {busy ? 'Checking…' : status.data?.mfa_enabled ? 'Confirm identity for live actions' : secret ? 'Confirm authenticator' : 'Set up authenticator'}
      </Button>
    </form>
    {message && <p role="status" className="text-sm text-success">{message}</p>}
    {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
  </section>
}
