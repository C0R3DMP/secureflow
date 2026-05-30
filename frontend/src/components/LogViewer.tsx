import { useEffect, useRef } from 'react'
import type { LogEntry } from '../types'

const LEVEL_CFG = {
  info:    { color: 'var(--cyan)',  prefix: 'INFO ', glow: 'rgba(0,240,255,0.25)' },
  warning: { color: 'var(--amber)', prefix: 'WARN ', glow: 'rgba(255,179,0,0.25)' },
  error:   { color: 'var(--pink)',  prefix: 'ERR  ', glow: 'rgba(255,0,122,0.25)' },
  success: { color: 'var(--green)', prefix: 'OK   ', glow: 'rgba(0,255,110,0.25)' },
}

function formatTime(d: Date) {
  return d.toLocaleTimeString('en-US', { hour12: false })
}

interface LogViewerProps {
  logs: LogEntry[]
}

export function LogViewer({ logs }: LogViewerProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs])

  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto"
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '0.67rem',
        lineHeight: 1.6,
        background: 'rgba(0,0,0,0.4)',
        border: '1px solid var(--border-dim)',
        padding: '0.5rem',
      }}
    >
      {logs.length === 0 ? (
        <div style={{ color: 'var(--text-dim)', textAlign: 'center', padding: '2rem', letterSpacing: '0.1em' }}>
          — NO LOG ENTRIES —
        </div>
      ) : (
        logs.map((log) => {
          const cfg = LEVEL_CFG[log.level]
          return (
            <div
              key={log.id}
              className="new-msg"
              style={{
                display: 'flex',
                gap: '0.5rem',
                padding: '0.1rem 0.25rem',
                borderRadius: '1px',
              }}
            >
              <span style={{ color: 'var(--text-dim)', flexShrink: 0 }}>
                [{formatTime(log.timestamp)}]
              </span>
              <span style={{
                color: cfg.color,
                flexShrink: 0,
                textShadow: `0 0 6px ${cfg.glow}`,
                fontWeight: 700,
                minWidth: '3.5rem',
              }}>
                {cfg.prefix}
              </span>
              <span style={{ color: 'var(--text-primary)', wordBreak: 'break-word', flex: 1 }}>
                {log.message}
              </span>
            </div>
          )
        })
      )}
      {/* Blinking cursor at end */}
      {logs.length > 0 && (
        <div style={{ color: 'var(--cyan)', display: 'inline' }}>
          <span className="cb-cursor" />
        </div>
      )}
    </div>
  )
}
