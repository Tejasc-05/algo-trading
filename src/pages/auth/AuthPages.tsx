import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'
import { useStrategyStore } from '@/store/useStrategyStore'

function GitHubIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A8.205 8.205 0 0012 22c5.31 0 9.795-3.435 11.385-8.205.6-.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A8.205 8.205 0 0012 22z" />
    </svg>
  )
}

function SocialButton({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <Button variant="outline" className="w-full" type="button" disabled title="Social login is not configured">
      {children}
      {label}
    </Button>
  )
}

export function LoginPage() {
  const navigate = useNavigate()
  const setUser = useAppStore((s) => s.setUser)

  return (
    <div className="space-y-6">
      <div className="text-center lg:text-left">
        <h1 className="text-2xl font-bold">Welcome back</h1>
        <p className="text-muted-foreground mt-1">Sign in to your AlgoFlow account</p>
      </div>

      <div className="space-y-4">
        <SocialButton label="Continue with Google">
          <svg className="h-4 w-4" viewBox="0 0 24 24"><path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="currentColor" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="currentColor" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="currentColor" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
        </SocialButton>
        <SocialButton label="Continue with GitHub">
          <GitHubIcon className="h-4 w-4" />
        </SocialButton>
      </div>

      <div className="relative">
        <Separator />
        <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-background px-3 text-xs text-muted-foreground">
          or continue with email
        </span>
      </div>

      <form className="space-y-4" onSubmit={async (e) => {
        e.preventDefault();
        const email = (document.getElementById('email') as HTMLInputElement).value;
        const password = (document.getElementById('password') as HTMLInputElement).value;
        try {
          const res = await api.auth.login(email, password);
          useStrategyStore.getState().reset();
          localStorage.setItem('access_token', res.access_token);
          localStorage.setItem('user', JSON.stringify(res.user));
          setUser({ name: res.user.full_name || res.user.name || '', email: res.user.email });
          navigate('/dashboard');
        } catch (error) {
          console.error('Login error:', error);
          alert('Login failed. Please check your credentials.');
        }
      }}>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" placeholder="you@example.com" />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link to="/forgot-password" className="text-xs text-primary hover:underline">
              Forgot password?
            </Link>
          </div>
          <Input id="password" type="password" placeholder="••••••••" />
        </div>
        <Button variant="gradient" className="w-full" type="submit">
          Sign In
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
      localStorage.setItem('access_token', res.access_token)
      localStorage.setItem('user', JSON.stringify(res.user))
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

      <div className="space-y-4">
        <SocialButton label="Sign up with Google">
          <svg className="h-4 w-4" viewBox="0 0 24 24"><path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/></svg>
        </SocialButton>
        <SocialButton label="Sign up with GitHub">
          <GitHubIcon className="h-4 w-4" />
        </SocialButton>
      </div>

      <div className="relative">
        <Separator />
        <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-background px-3 text-xs text-muted-foreground">
          or sign up with email
        </span>
      </div>

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="space-y-2">
            <Label htmlFor="name">Full Name</Label>
            <Input id="name" placeholder="Alex Chen" value={fullName} onChange={e => setFullName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" placeholder="Min. 8 characters" value={password} onChange={e => setPassword(e.target.value)} />
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
  return (
    <div className="space-y-6">
      <div className="text-center lg:text-left">
        <h1 className="text-2xl font-bold">Reset your password</h1>
        <p className="text-muted-foreground mt-1">
          Enter your email and we'll send you a reset link
        </p>
      </div>

      <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" placeholder="you@example.com" />
        </div>
        <Button variant="gradient" className="w-full" disabled title="Password reset is not configured">Send Reset Link</Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        Remember your password?{' '}
        <Link to="/login" className="text-primary hover:underline font-medium">Sign in</Link>
      </p>
    </div>
  )
}
