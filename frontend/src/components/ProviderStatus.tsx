import { useState } from 'react'
import type { Provider } from '../types'

const PROVIDER_GLYPHS: Record<string, string> = {
  claude:      '◈',
  gemini:      '◆',
  openrouter:  '○',
  ollama:      '◉',
  opencode:    '▣',
}

const PRIORITY_LABEL = ['', 'PRIMARY', 'SECONDARY', 'TERTIARY', 'FALLBACK']

function dotClass(status: Provider['status']): string {
  if (status === 'available') return 'ok'
  if (status === 'limited')   return 'warn'
  return 'off'
}

interface ProviderStatusProps {
  providers: Provider[]
  onTest?: (name: string) => void
}

export function ProviderStatus({ providers, onTest }: ProviderStatusProps) {
  const [testing, setTesting]  = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)

  const handleTest = async (name: string) => {
    setTesting(name)
    onTest?.(name)
    setTimeout(() => setTesting(null), 2000)
  }

  const handleStartOpenCode = async () => {
    setStarting(true)
    try {
      await fetch('/api/opencode/start', { method: 'POST' })
      setTimeout(() => window.location.reload(), 1000)
    } finally {
      setStarting(false)
    }
  }

  const handleStopOpenCode = async () => {
    setStopping(true)
    try {
      await fetch('/api/opencode/stop', { method: 'POST' })
      setTimeout(() => window.location.reload(), 1000)
    } finally {
      setStopping(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
      {providers.map((p) => {
        const glyph = PROVIDER_GLYPHS[p.name] ?? '◌'
        const isAvail = p.status === 'available'
        const isLimited = p.status === 'limited'
        const nodeColor = isAvail ? 'var(--green)' : isLimited ? 'var(--amber)' : 'var(--text-dim)'
        const borderColor = isAvail
          ? 'rgba(0,255,110,0.2)'
          : isLimited
          ? 'rgba(255,179,0,0.2)'
          : 'var(--border-dim)'

        return (
          <div
            key={p.name}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.35rem 0.5rem',
              border: `1px solid ${borderColor}`,
              background: isAvail
                ? 'rgba(0,255,110,0.03)'
                : isLimited
                ? 'rgba(255,179,0,0.03)'
                : 'transparent',
              transition: 'all 0.2s',
            }}
          >
            {/* Status dot */}
            <span className={`status-dot ${dotClass(p.status)}`} />

            {/* Glyph */}
            <span style={{
              color: nodeColor,
              fontFamily: 'var(--font-mono)',
              fontSize: '0.85rem',
              width: '14px',
              textAlign: 'center',
              flexShrink: 0,
              textShadow: isAvail ? `0 0 6px ${nodeColor}` : 'none',
            }}>
              {glyph}
            </span>

            {/* Name + mode */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.62rem',
                fontWeight: 700,
                letterSpacing: '0.12em',
                color: isAvail ? 'var(--text-primary)' : 'var(--text-secondary)',
                textTransform: 'uppercase',
              }}>
                {p.name}
                {p.mode && (
                  <span style={{ fontWeight: 400, marginLeft: '0.4rem', color: 'var(--text-dim)', fontSize: '0.55rem' }}>
                    [{p.mode}]
                  </span>
                )}
              </div>
              <div style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.52rem',
                color: 'var(--text-dim)',
                letterSpacing: '0.08em',
              }}>
                {PRIORITY_LABEL[p.priority] ?? `P${p.priority}`}
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: '0.2rem', flexShrink: 0 }}>
              <button
                className="cb-icon-btn"
                onClick={() => handleTest(p.name)}
                disabled={testing === p.name}
                title="Test connection"
                style={{
                  width: '1.6rem',
                  height: '1.6rem',
                  fontSize: '0.7rem',
                  animation: testing === p.name ? 'spin-ring 1s linear infinite' : 'none',
                }}
              >
                ↻
              </button>

              {p.name === 'opencode' && (
                <>
                  <button
                    className="cb-icon-btn"
                    onClick={handleStartOpenCode}
                    disabled={starting}
                    title="Start OpenCode"
                    style={{ width: '1.6rem', height: '1.6rem', fontSize: '0.7rem', color: 'var(--green)' }}
                  >
                    ▶
                  </button>
                  <button
                    className="cb-icon-btn"
                    onClick={handleStopOpenCode}
                    disabled={stopping}
                    title="Stop OpenCode"
                    style={{ width: '1.6rem', height: '1.6rem', fontSize: '0.7rem', color: 'var(--pink)' }}
                  >
                    ■
                  </button>
                </>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
