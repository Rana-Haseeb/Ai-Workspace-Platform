import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, Check, Loader2 } from 'lucide-react'

import { AuthLayout } from '@/components/auth/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'

const MIN_PASSWORD_LENGTH = 8

export default function Register() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [touchedPassword, setTouchedPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const longEnough = password.length >= MIN_PASSWORD_LENGTH
  // Validate on blur, not on every keystroke — flagging "too short" while someone is still
  // typing their password is noise, not help.
  const showPasswordHint = touchedPassword && !longEnough

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await register(email, password, displayName)
      navigate('/', { replace: true })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not create the account.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Workspaces, memory, and documents — all private to you."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div className="space-y-2">
          <Label htmlFor="name">
            Name <span className="text-muted-foreground">(optional)</span>
          </Label>
          <Input
            id="name"
            autoComplete="name"
            placeholder="Ada Lovelace"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            placeholder="name@company.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            aria-describedby="password-hint"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            onBlur={() => setTouchedPassword(true)}
            required
          />
          <p
            id="password-hint"
            className={`flex items-center gap-1.5 text-xs ${
              showPasswordHint ? 'text-destructive' : 'text-muted-foreground'
            }`}
          >
            {longEnough && <Check className="size-3.5" aria-hidden />}
            At least {MIN_PASSWORD_LENGTH} characters. A phrase beats a short, complex password.
          </p>
        </div>

        {error && (
          <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting && <Loader2 className="size-4 animate-spin" aria-hidden />}
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>
      </form>
    </AuthLayout>
  )
}
