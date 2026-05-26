import { CheckCircle2, Circle, Loader2 } from 'lucide-react'
import type { PhaseStatus } from '../types'
import clsx from 'clsx'

interface ProgressPhasesProps {
  phases: PhaseStatus[]
}

export function ProgressPhases({ phases }: ProgressPhasesProps) {
  return (
    <div className="space-y-3">
      {phases.map((phase) => (
        <div
          key={phase.name}
          className={clsx(
            'flex items-center gap-3 p-4 rounded-lg border transition-all duration-300',
            phase.status === 'completed'
              ? 'border-success/50 bg-success/5'
              : phase.status === 'running'
              ? 'border-primary/50 bg-primary/5 shadow-lg shadow-primary/20'
              : 'border-border bg-card/50',
          )}
        >
          <div className="relative w-10 h-10 flex-shrink-0">
            {phase.status === 'completed' && (
              <CheckCircle2 className="w-10 h-10 text-success" />
            )}
            {phase.status === 'running' && (
              <Loader2 className="w-10 h-10 text-primary animate-spin" />
            )}
            {phase.status === 'pending' && (
              <Circle className="w-10 h-10 text-muted-foreground" />
            )}
          </div>

          <div className="flex-1">
            <h3 className="text-sm font-semibold text-foreground capitalize">
              {phase.name.replace('_', ' ')}
            </h3>
            <p className="text-xs text-muted-foreground">
              {phase.status === 'pending' && 'Waiting...'}
              {phase.status === 'running' && 'In Progress'}
              {phase.status === 'completed' && 'Completed ✓'}
            </p>
          </div>

          {phase.startTime && (
            <Timer startTime={phase.startTime} isRunning={phase.status === 'running'} />
          )}
        </div>
      ))}
    </div>
  )
}

function Timer({ startTime, isRunning }: { startTime: Date; isRunning: boolean }) {
  const [time, setTime] = React.useState(0)

  React.useEffect(() => {
    if (!isRunning) return

    const interval = setInterval(() => {
      setTime(Math.floor((Date.now() - startTime.getTime()) / 1000))
    }, 1000)

    return () => clearInterval(interval)
  }, [isRunning, startTime])

  const mins = Math.floor(time / 60)
  const secs = time % 60

  return (
    <div className="text-sm font-mono text-primary font-semibold">
      {mins.toString().padStart(2, '0')}:{secs.toString().padStart(2, '0')}
    </div>
  )
}

import React from 'react'
