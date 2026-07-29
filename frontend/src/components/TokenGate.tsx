import { useState, type FormEvent } from 'react'
import { KeyRound, ShieldCheck, AlertCircle } from 'lucide-react'
import { setToken } from '../lib/auth'

/**
 * Shown when the API rejects our credentials (401).
 *
 * The server enforces a bearer secret on every /api and /stream route, and
 * prints a generated token at startup when MCP_SECRET is unset. Without this
 * screen the dashboard would simply appear broken.
 */
export function TokenGate({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const token = value.trim()
    if (!token) {
      setError('Enter the token printed in the server log.')
      return
    }

    setChecking(true)
    setError(null)
    try {
      const response = await fetch('/api/providers', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (response.status === 401) {
        setError('That token was rejected by the server.')
        return
      }
      if (!response.ok) {
        setError(`Server returned ${response.status}. Is it running?`)
        return
      }
      setToken(token)
      onAuthenticated()
    } catch {
      setError('Could not reach the server. Is it running on this host?')
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <div className="panel w-full max-w-md shadow-lg">
        <div className="flex flex-col items-center gap-3 border-b border-line px-6 py-7 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-accent-subtle">
            <ShieldCheck className="h-5 w-5 text-accent" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-base font-semibold">Authentication required</h1>
            <p className="mt-1 text-sm text-secondary">
              SecureFlow protects every API route with a bearer token.
            </p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4 px-6 py-6">
          <div>
            <label htmlFor="token" className="label-caps mb-2 block">
              Access token
            </label>
            <div className="relative">
              <KeyRound
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted"
                aria-hidden="true"
              />
              <input
                id="token"
                type="password"
                autoFocus
                autoComplete="current-password"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="MCP_SECRET"
                className={`field pl-9 ${error ? 'field-invalid' : ''}`}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? 'token-error' : 'token-hint'}
              />
            </div>

            {error ? (
              <p
                id="token-error"
                role="alert"
                className="mt-2 flex items-start gap-1.5 text-xs text-severity-critical"
              >
                <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {error}
              </p>
            ) : (
              <p id="token-hint" className="mt-2 text-xs text-muted">
                Set <code className="text-ink-secondary">MCP_SECRET</code> in your
                environment, or copy the token printed when the server started.
              </p>
            )}
          </div>

          <button type="submit" className="btn btn-primary w-full" disabled={checking}>
            {checking ? 'Verifying…' : 'Continue'}
          </button>
        </form>
      </div>
    </div>
  )
}
