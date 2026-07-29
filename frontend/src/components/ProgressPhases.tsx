import { useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import type { PhaseStatus } from '../types'

const PHASE_LABEL: Record<PhaseStatus['name'], string> = {
  reconnaissance: 'Reconnaissance',
  analysis: 'Vulnerability analysis',
  reporting: 'Report generation',
}

const STATUS_TEXT: Record<PhaseStatus['status'], string> = {
  pending: 'Queued',
  running: 'In progress',
  completed: 'Complete',
}

interface ProgressPhasesProps {
  phases: PhaseStatus[]
}

/**
 * Vertical stepper. Each step states its status in words next to the icon, so
 * progress is never conveyed by colour or motion alone.
 */
export function ProgressPhases({ phases }: ProgressPhasesProps) {
  const done = phases.filter((p) => p.status === 'completed').length

  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between">
        <span className="label-caps">Progress</span>
        <span className="tabular text-xs text-muted">
          {done}/{phases.length}
        </span>
      </div>

      <ol className="space-y-1">
        {phases.map((phase, index) => {
          const isLast = index === phases.length - 1
          return (
            <li key={phase.name} className="relative flex gap-3">
              {/* Connector */}
              {!isLast && (
                <span
                  aria-hidden="true"
                  className={clsx(
                    'absolute left-[0.6875rem] top-6 h-[calc(100%-0.5rem)] w-px',
                    phase.status === 'completed' ? 'bg-severity-none/40' : 'bg-line',
                  )}
                />
              )}

              <StepIcon status={phase.status} />

              <div className="flex min-w-0 flex-1 items-baseline justify-between gap-2 pb-3">
                <div className="min-w-0">
                  <p
                    className={clsx(
                      'truncate text-sm',
                      phase.status === 'pending'
                        ? 'text-muted'
                        : 'font-medium text-ink',
                    )}
                  >
                    {PHASE_LABEL[phase.name]}
                  </p>
                  <p className="text-xs text-muted">{STATUS_TEXT[phase.status]}</p>
                </div>

                {phase.startTime && phase.status !== 'pending' && (
                  <Elapsed
                    startTime={phase.startTime}
                    running={phase.status === 'running'}
                  />
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function StepIcon({ status }: { status: PhaseStatus['status'] }) {
  if (status === 'completed') {
    return (
      <span className="relative z-10 flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center rounded-full bg-severity-none/15 text-severity-none">
        <Check className="h-3 w-3" aria-hidden="true" />
      </span>
    )
  }
  if (status === 'running') {
    return (
      <span className="relative z-10 flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center rounded-full bg-accent-subtle text-accent">
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
      </span>
    )
  }
  return (
    <span
      className="relative z-10 flex h-[1.375rem] w-[1.375rem] shrink-0 items-center justify-center rounded-full border border-line bg-surface-2"
      aria-hidden="true"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-ink-muted/50" />
    </span>
  )
}

function Elapsed({ startTime, running }: { startTime: Date; running: boolean }) {
  const [seconds, setSeconds] = useState(() =>
    Math.floor((Date.now() - startTime.getTime()) / 1000),
  )

  useEffect(() => {
    if (!running) return
    const tick = () =>
      setSeconds(Math.floor((Date.now() - startTime.getTime()) / 1000))
    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [running, startTime])

  const mm = Math.floor(seconds / 60)
    .toString()
    .padStart(2, '0')
  const ss = (seconds % 60).toString().padStart(2, '0')

  return (
    <span className="tabular shrink-0 font-mono text-xs text-muted">
      {mm}:{ss}
    </span>
  )
}
