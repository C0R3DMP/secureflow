import { CheckCircle2, AlertCircle, XCircle, RefreshCw } from 'lucide-react'
import { Badge } from './Badge'
import type { Provider } from '../types'
import clsx from 'clsx'
import { useState } from 'react'

const providerEmojis = {
  claude: '🤖',
  gemini: '✨',
  ollama: '🦙',
  opencode: '💻',
  'gemini-cli': '🌟',
}

interface ProviderStatusProps {
  providers: Provider[]
  onTest?: (name: string) => void
}

export function ProviderStatus({ providers, onTest }: ProviderStatusProps) {
  const [testing, setTesting] = useState<string | null>(null)

  const handleTest = async (name: string) => {
    setTesting(name)
    onTest?.(name)
    setTimeout(() => setTesting(null), 2000)
  }

  return (
    <div className="space-y-2">
      {providers.map((provider) => (
        <div
          key={provider.name}
          className={clsx(
            'flex items-center justify-between p-3 rounded-lg border transition-colors',
            provider.status === 'available'
              ? 'border-success/30 bg-success/5'
              : provider.status === 'limited'
              ? 'border-yellow-500/30 bg-yellow-500/5'
              : 'border-destructive/30 bg-destructive/5',
          )}
        >
          <div className="flex items-center gap-3">
            <span className="text-lg">
              {providerEmojis[provider.name]}
            </span>
            <div>
              <p className="text-sm font-semibold capitalize text-foreground">
                {provider.name}
              </p>
              <p className="text-xs text-muted-foreground">
                Priority: #{provider.priority}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {provider.status === 'available' && (
              <CheckCircle2 className="h-5 w-5 text-success" />
            )}
            {provider.status === 'limited' && (
              <AlertCircle className="h-5 w-5 text-yellow-500" />
            )}
            {provider.status === 'unavailable' && (
              <XCircle className="h-5 w-5 text-destructive" />
            )}

            <Badge
              variant={
                provider.status === 'available'
                  ? 'success'
                  : provider.status === 'limited'
                  ? 'warning'
                  : 'destructive'
              }
            >
              {provider.status}
            </Badge>

            <button
              onClick={() => handleTest(provider.name)}
              disabled={testing === provider.name}
              className={clsx(
                'p-1 rounded hover:bg-primary/20 transition-colors disabled:opacity-50',
                testing === provider.name && 'animate-spin',
              )}
              title="Test connection"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
