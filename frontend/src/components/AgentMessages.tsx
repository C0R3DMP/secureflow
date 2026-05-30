import { useEffect, useRef } from 'react'
import type { AgentMessage } from '../types'

const AGENT_CONFIG: Record<
  AgentMessage['agent'],
  { label: string; color: string; accent: string; dot: string }
> = {
  recon:     { label: 'RECON-AGENT',    color: 'var(--cyan)',   accent: 'rgba(0,240,255,0.08)',   dot: 'ok' },
  analyst:   { label: 'ANALYST-NODE',   color: 'var(--purple)', accent: 'rgba(168,85,247,0.08)',  dot: 'warn' },
  reporter:  { label: 'REPORTER-UNIT',  color: 'var(--green)',  accent: 'rgba(0,255,110,0.08)',   dot: 'ok' },
  architect: { label: 'ARCH-CORE',      color: 'var(--cyan)',   accent: 'rgba(0,240,255,0.06)',   dot: 'ok' },
  developer: { label: 'DEV-NODE',       color: 'var(--amber)',  accent: 'rgba(255,179,0,0.08)',   dot: 'warn' },
  reviewer:  { label: 'REVIEW-DAEMON',  color: 'var(--amber)',  accent: 'rgba(255,179,0,0.06)',   dot: 'warn' },
  system:    { label: 'SYS-KERNEL',     color: 'var(--pink)',   accent: 'rgba(255,0,122,0.08)',   dot: 'err' },
}

function formatTime(d: Date) {
  return d.toLocaleTimeString('en-US', { hour12: false })
}

interface AgentMessagesProps {
  messages: AgentMessage[]
}

export function AgentMessages({ messages }: AgentMessagesProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto space-y-2 pr-1"
      style={{ scrollbarGutter: 'stable' }}
    >
      {messages.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center h-full"
          style={{ color: 'var(--text-dim)' }}
        >
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" style={{ opacity: 0.3 }}>
            <circle cx="24" cy="24" r="20" stroke="var(--cyan)" strokeWidth="1" />
            <circle cx="24" cy="24" r="14" stroke="var(--cyan)" strokeWidth="0.5" />
            <line x1="24" y1="4" x2="24" y2="12" stroke="var(--cyan)" strokeWidth="1.5" />
            <line x1="24" y1="36" x2="24" y2="44" stroke="var(--cyan)" strokeWidth="1.5" />
            <line x1="4" y1="24" x2="12" y2="24" stroke="var(--cyan)" strokeWidth="1.5" />
            <line x1="36" y1="24" x2="44" y2="24" stroke="var(--cyan)" strokeWidth="1.5" />
          </svg>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', letterSpacing: '0.15em', marginTop: '0.75rem' }}>
            AWAITING NEURAL TRANSMISSION
          </p>
          <p style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
            initiate scan to begin agent collaboration
          </p>
        </div>
      ) : (
        messages.map((msg) => {
          const cfg = AGENT_CONFIG[msg.agent] ?? AGENT_CONFIG.system
          return (
            <div
              key={msg.id}
              className="new-msg"
              style={{
                background: cfg.accent,
                borderLeft: `2px solid ${cfg.color}`,
                padding: '0.5rem 0.75rem',
                position: 'relative',
              }}
            >
              {/* Transmission header */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                marginBottom: '0.3rem',
              }}>
                <span className={`status-dot ${cfg.dot}`} />
                <span style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.6rem',
                  fontWeight: 700,
                  letterSpacing: '0.18em',
                  color: cfg.color,
                  textShadow: `0 0 8px ${cfg.color}`,
                }}>
                  {cfg.label}
                </span>
                <span style={{
                  marginLeft: 'auto',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.55rem',
                  color: 'var(--text-dim)',
                  letterSpacing: '0.1em',
                }}>
                  {formatTime(msg.timestamp)}
                </span>
              </div>
              {/* Message body */}
              <p style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.72rem',
                color: 'var(--text-primary)',
                lineHeight: 1.5,
                wordBreak: 'break-word',
              }}>
                {msg.message}
              </p>
            </div>
          )
        })
      )}
    </div>
  )
}
