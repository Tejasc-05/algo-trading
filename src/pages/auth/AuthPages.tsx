import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'
import { useStrategyStore } from '@/store/useStrategyStore'

export function LoginPage() {
  const navigate = useNavigate()
  const setUser = useAppStore((s) => s.setUser)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [totpCode, setTotpCode] = useState('')

  return (
    <div className="space-y-6">
      <div className="text-center lg:text-left">
        <h1 className="text-2xl font-bold">Welcome back</h1>
        <p className="text-muted-foreground mt-1">Sign in to your AlgoFlow account</p>
      </div>

      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault();
        if (busy) return
        setBusy(true); setError('')
        const email = (document.getElementById('email') as HTMLInputElement).value;
        const password = (document.getElementById('password') as HTMLInputElement).value;
        try {
          const res = await api.auth.login(email, password, totpCode || undefined);
          useStrategyStore.getState().reset();
          setUser({ name: res.user.full_name || res.user.name || '', email: res.user.email });
          navigate('/dashboard');
        } catch (error) {
          setError(error instanceof Error ? error.message : 'Unable to sign in.');
        } finally { setBusy(false) }
      }}>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required autoComplete="email" placeholder="you@example.com" />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link to="/forgot-password" className="text-xs text-primary hover:underline">
              Forgot password?
            </Link>
          </div>
          <Input id="password" type="password" required autoComplete="current-password" placeholder="••••••••" />
        </div>
        <div className="space-y-2"><Label htmlFor="login-code">Authenticator code (if enabled)</Label>
          <Input id="login-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={totpCode} onChange={e => setTotpCode(e.target.value)} /></div>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        <Button variant="gradient" className="w-full" type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign In'}
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        Don't have an account?{' '}
        <Link to="/signup" className="text-primary hover:underline font-medium">Sign up</Link>
      </p>
    </div>
  )
}


export function SignupPage() {
  const navigate = useNavigate()
  const setUser = useAppStore((s) => s.setUser)
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const res = await api.auth.register(email, password, fullName)
      useStrategyStore.getState().reset()
      setUser({ name: res.user.full_name || res.user.name || '', email: res.user.email })
      navigate('/dashboard')
    } catch (error) {
      console.error('Signup error:', error)
      alert('Signup failed. Please try again.')
    }
  }

  return (
    <div className="space-y-6">
      <div className="text-center lg:text-left">
        <h1 className="text-2xl font-bold">Create your account</h1>
        <p className="text-muted-foreground mt-1">Start building trading strategies for free</p>
      </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="name">Full Name</Label>
            <Input id="name" placeholder="Alex Chen" value={fullName} onChange={e => setFullName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" required autoComplete="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" required minLength={8} autoComplete="new-password" placeholder="Min. 8 characters" value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          <Button variant="gradient" className="w-full" type="submit">
            Create Account
          </Button>
        </form>





      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{' '}
        <Link to="/login" className="text-primary hover:underline font-medium">Sign in</Link>
      </p>
    </div>
  )
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const pending = useRef(false)
  return <div className="space-y-6">
    <div className="text-center lg:text-left">
      <h1 className="text-2xl font-bold">Reset your password</h1>
      <p className="text-muted-foreground mt-1">Enter your account email to request a password reset link.</p>
    </div>
    <form className="space-y-4" onSubmit={async e => {
      e.preventDefault()
      if (pending.current) return
      pending.current = true; setBusy(true); setMessage(''); setError('')
      try { const result = await api.auth.forgotPassword(email.trim()); setMessage(result.message) }
      catch (e) { setError(e instanceof Error ? e.message : 'Unable to request a reset link. Try again later.') }
      finally { pending.current = false; setBusy(false) }
    }}>
      <div className="space-y-2"><Label htmlFor="reset-email">Email</Label>
        <Input id="reset-email" type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" disabled={busy} />
      </div>
      {message && <p role="status" className="text-sm text-success">{message}</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <Button variant="gradient" className="w-full min-h-11" type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send Reset Link'}</Button>
    </form>
    <p className="text-center text-sm text-muted-foreground">Remember your password? <Link to="/login" className="text-primary hover:underline font-medium">Sign in</Link></p>
  </div>
}

export function ResetPasswordPage() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  useEffect(() => {
    // The fragment never reaches the server. Remove it from browser history too.
    window.history.replaceState(window.history.state, '', window.location.pathname)
    const meta = document.createElement('meta')
    meta.name = 'referrer'; meta.content = 'no-referrer'; document.head.appendChild(meta)
    return () => meta.remove()
  }, [])
  return <div className="space-y-6">
    <div className="text-center lg:text-left"><h1 className="text-2xl font-bold">Choose a new password</h1>
      <p className="text-muted-foreground mt-1">Use at least 8 characters. Use a current reset link from your email.</p>
    </div>
    {done ? <div className="space-y-4"><p role="status" className="text-sm text-success">Password reset successfully. Sign in with your new password.</p><Button asChild className="w-full min-h-11"><Link to="/login">Sign in</Link></Button></div> : !token ? <div className="space-y-4"><p role="alert" className="text-sm text-destructive">This page needs a reset link. Open the link from your email or request another.</p><Button asChild variant="outline" className="w-full min-h-11"><Link to="/forgot-password">Request a new reset link</Link></Button></div> :
      <form className="space-y-4" onSubmit={async e => {
        e.preventDefault(); setError('')
        if (pending.current) return
        if (password !== confirmation) { setError('Passwords do not match'); return }
        if (new TextEncoder().encode(password).length > 72) { setError('Password must be at most 72 UTF-8 bytes.'); return }
        pending.current = true; setBusy(true)
        try {
          await api.auth.resetPassword(token, password, confirmation)
          useAppStore.getState().logout()
          setPassword(''); setConfirmation(''); setDone(true)
        } catch (e) { setError(e instanceof Error ? e.message : 'Unable to reset your password.') }
        finally { pending.current = false; setBusy(false) }
      }}>
        <div className="space-y-2"><Label htmlFor="new-password">New password</Label><Input id="new-password" type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} disabled={busy} /></div>
        <div className="space-y-2"><Label htmlFor="confirm-password">Confirm password</Label><Input id="confirm-password" type="password" required minLength={8} maxLength={128} autoComplete="new-password" value={confirmation} onChange={e => setConfirmation(e.target.value)} disabled={busy} /></div>
        {error && <div className="space-y-2"><p role="alert" className="text-sm text-destructive">{error}</p><Link to="/forgot-password" className="text-sm text-primary hover:underline">Request a new reset link</Link></div>}
        <Button variant="gradient" type="submit" disabled={busy} className="w-full min-h-11">{busy ? 'Resetting…' : 'Reset password'}</Button>
      </form>}
  </div>
}
