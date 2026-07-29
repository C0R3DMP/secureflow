import { useState } from 'react'
import { CircleDashed, Play, Square } from 'lucide-react'
import clsx from 'clsx'
import { authFetch } from '../lib/auth'
import type { Provider } from '../types'

const PROVIDER_LABEL: Record<Provider['name'], string> = {
  claude: 'Claude',
  gemini: 'Gemini',
  openrouter: 'OpenRouter',
  ollama: 'Ollama',
  opencode: 'OpenCode',
}

const STATUS: Record<Provider['status'], { label: string; dot: string; text: string }> = {
  available: { label: 'Online', dot: 'bg-severity-none', text: 'text-severity-none' },
  limited: { label: 'Limited', dot: 'bg-severity-medium', text: 'text-severity-medium' },
  unavailable: { label: 'Offline', dot: 'bg-ink-muted/50', text: 'text-muted' },
  unknown: { label: 'Checking', dot: 'bg-ink-muted/40', text: 'text-muted' },
}

interface ProviderStatusProps {
  providers: Provider[]
  onRefresh?: () => void
}

export function ProviderStatus({ providers, onRefresh }: ProviderStatusProps) {
  const [busy, setBusy] = useState<'start' | 'stop' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const controlOpenCode = async (action: 'start' | 'stop') => {
    setBusy(action)
    setError(null)
    try {
      const response = await authFetch(`/api/opencode/${action}`, { method: 'POST' })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        setError(body.message ?? `Could not ${action} OpenCode`)
        return
      }
      // Give the process a moment to bind its port, then re-poll — far less
      // disruptive than the full window.location.reload() this used to do.
      setTimeout(() => onRefresh?.(), 900)
    } catch {
      setError(`Could not reach the server to ${action} OpenCode`)
    } finally {
      setBusy(null)
    }
  }

  const online = providers.filter((p) => p.status === 'available').length
  const settled = providers.some((p) => p.status !== 'unknown')

  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between">
        <span className="label-caps">Providers</span>
        <span className="tabular text-xs text-muted">
          {settled ? `${online}/${providers.length} online` : 'checking…'}
        </span>
      </div>

      <ul className="space-y-px">
        {providers.map((provider) => {
          const status = STATUS[provider.status] ?? STATUS.unknown
          return (
            <li
              key={provider.name}
              className="flex items-center gap-2.5 rounded-sm px-1.5 py-1.5 hover:bg-surface-2"
            >
              <span
                className={clsx(
                  'dot',
                  status.dot,
                  provider.status === 'unknown' && 'dot-live',
                )}
                aria-hidden="true"
              />

              <span className="min-w-0 flex-1 truncate text-[0.8125rem] text-ink">
                {PROVIDER_LABEL[provider.name]}
                {provider.mode && (
                  <span className="ml-1.5 font-mono text-[0.6875rem] text-muted">
                    {provider.mode}
                  </span>
                )}
              </span>

              {/* Status is spelled out, so the dot's colour is reinforcement. */}
              <span className={clsx('shrink-0 text-[0.6875rem]', status.text)}>
                {status.label}
              </span>

              {provider.name === 'opencode' && (
                <span className="flex shrink-0 items-center gap-0.5">
                  <button
                    onClick={() => controlOpenCode('start')}
                    disabled={busy !== null || provider.status === 'available'}
                    className="icon-btn h-6 w-6 disabled:opacity-30"
                    aria-label="Start OpenCode server"
                    title="Start OpenCode"
                  >
                    {busy === 'start' ? (
                      <CircleDashed className="h-3 w-3 animate-spin" aria-hidden="true" />
                    ) : (
                      <Play className="h-3 w-3" aria-hidden="true" />
                    )}
                  </button>
                  <button
                    onClick={() => controlOpenCode('stop')}
                    disabled={busy !== null || provider.status !== 'available'}
                    className="icon-btn h-6 w-6 disabled:opacity-30"
                    aria-label="Stop OpenCode server"
                    title="Stop OpenCode"
                  >
                    {busy === 'stop' ? (
                      <CircleDashed className="h-3 w-3 animate-spin" aria-hidden="true" />
                    ) : (
                      <Square className="h-3 w-3" aria-hidden="true" />
                    )}
                  </button>
                </span>
              )}
            </li>
          )
        })}
      </ul>

      {error && (
        <p role="alert" className="mt-2 text-xs text-severity-critical">
          {error}
        </p>
      )}
    </div>
  )
}
