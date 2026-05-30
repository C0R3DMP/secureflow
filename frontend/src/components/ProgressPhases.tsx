import { useState, useEffect } from 'react'
import type { PhaseStatus } from '../types'

const PHASE_CFG: Record<PhaseStatus['name'], { icon: string; code: string }> = {
  reconnaissance: { icon: '◉', code: 'RECON' },
  analysis:       { icon: '◈', code: 'ANALYZ' },
  reporting:      { icon: '◆', code: 'REPORT' },
}

function Timer({ startTime, isRunning }: { startTime: Date; isRunning: boolean }) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!isRunning) return
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime.getTime()) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [isRunning, startTime])

  const m = Math.floor(elapsed / 60).toString().padStart(2, '0')
  const s = (elapsed % 60).toString().padStart(2, '0')
  return (
    <span style={{ color: 'var(--cyan)', fontFamily: 'var(--font-mono)', fontSize: '0.65rem' }}>
      {m}:{s}
    </span>
  )
}

interface ProgressPhasesProps {
  phases: PhaseStatus[]
}

export function ProgressPhases({ phases }: ProgressPhasesProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      {phases.map((phase, idx) => {
        const cfg = PHASE_CFG[phase.name]
        const isRunning   = phase.status === 'running'
        const isCompleted = phase.status === 'completed'
        const isPending   = phase.status === 'pending'

        const borderColor  = isRunning ? 'var(--cyan)' : isCompleted ? 'var(--green)' : 'var(--border-dim)'
        const iconColor    = isRunning ? 'var(--cyan)' : isCompleted ? 'var(--green)'  : 'var(--text-dim)'
        const labelColor   = isRunning ? 'var(--cyan)' : isCompleted ? 'var(--green)'  : 'var(--text-secondary)'
        const bgColor      = isRunning ? 'rgba(0,240,255,0.05)' : isCompleted ? 'rgba(0,255,110,0.04)' : 'transparent'
        const boxShadow    = isRunning ? '0 0 12px rgba(0,240,255,0.2), inset 0 0 6px rgba(0,240,255,0.05)' : 'none'

        return (
          <div key={phase.name}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.6rem',
                padding: '0.5rem 0.6rem',
                border: `1px solid ${borderColor}`,
                background: bgColor,
                boxShadow,
                transition: 'all 0.3s',
                animation: isRunning ? 'border-flow 2s ease-in-out infinite' : 'none',
              }}
            >
              {/* Node number */}
              <div style={{
                width: '20px',
                height: '20px',
                border: `1px solid ${borderColor}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                fontSize: '0.55rem',
                fontWeight: 700,
                color: iconColor,
                fontFamily: 'var(--font-mono)',
              }}>
                {idx + 1}
              </div>

              {/* Phase icon */}
              <span style={{
                fontSize: '0.9rem',
                color: iconColor,
                textShadow: isRunning ? `0 0 8px ${iconColor}` : isCompleted ? `0 0 6px var(--green)` : 'none',
                animation: isRunning ? 'neon-pulse 1.5s ease-in-out infinite' : 'none',
              }}>
                {cfg.icon}
              </span>

              {/* Phase label */}
              <div style={{ flex: 1 }}>
                <div style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.62rem',
                  fontWeight: 700,
                  letterSpacing: '0.15em',
                  color: labelColor,
                  textTransform: 'uppercase',
                }}>
                  {cfg.code}
                </div>
                <div style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.55rem',
                  color: 'var(--text-dim)',
                  letterSpacing: '0.08em',
                }}>
                  {isPending && 'STANDBY'}
                  {isRunning && 'PROCESSING...'}
                  {isCompleted && '[ COMPLETE ]'}
                </div>
              </div>

              {/* Timer / status indicator */}
              <div>
                {isRunning && phase.startTime && (
                  <Timer startTime={phase.startTime} isRunning />
                )}
                {isCompleted && (
                  <span style={{ color: 'var(--green)', fontSize: '0.9rem', textShadow: '0 0 6px var(--green)' }}>
                    ✓
                  </span>
                )}
                {isPending && (
                  <span style={{ color: 'var(--text-dim)', fontSize: '0.8rem' }}>○</span>
                )}
              </div>
            </div>

            {/* Connector line between phases */}
            {idx < phases.length - 1 && (
              <div style={{
                width: '1px',
                height: '6px',
                marginLeft: '25px',
                background: isCompleted
                  ? 'linear-gradient(180deg, var(--green), var(--border-dim))'
                  : 'var(--border-dim)',
              }} />
            )}
          </div>
        )
      })}
    </div>
  )
}
