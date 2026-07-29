import { useEffect, useRef } from 'react'
import { CheckCircle2, Clock, History, X, XCircle } from 'lucide-react'
import { Badge } from './Badge'
import type { ScanSession } from '../types'

interface ScanHistoryProps {
  sessions: ScanSession[]
  onClose: () => void
  onSelect?: (target: string) => void
}

export function ScanHistory({ sessions, onClose, onSelect }: ScanHistoryProps) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-overlay/80 p-4 pt-16 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="history-title"
      onClick={onClose}
    >
      <div
        className="panel flex max-h-[75vh] w-full max-w-2xl flex-col shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="panel-header">
          <h2 id="history-title" className="panel-title">
            <History className="h-4 w-4 text-ink-muted" aria-hidden="true" />
            Assessment history
            <span className="tabular ml-1 text-xs font-normal text-muted">
              {sessions.length}
            </span>
          </h2>
          <button ref={closeRef} onClick={onClose} className="icon-btn" aria-label="Close history">
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {sessions.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
              <History className="h-7 w-7 text-ink-muted" aria-hidden="true" />
              <p className="text-sm text-secondary">No assessments recorded yet</p>
              <p className="max-w-xs text-xs text-muted">
                Completed scans are persisted and will appear here.
              </p>
            </div>
          ) : (
            <ul className="space-y-1">
              {sessions.map((session) => {
                const ok = session.status === 'success'
                return (
                  <li key={session.id}>
                    <button
                      onClick={() => {
                        onSelect?.(session.target)
                        onClose()
                      }}
                      className="w-full rounded-sm px-3 py-2.5 text-left transition-colors hover:bg-surface-2"
                    >
                      <div className="flex items-center gap-2.5">
                        {ok ? (
                          <CheckCircle2
                            className="h-4 w-4 shrink-0 text-severity-none"
                            aria-hidden="true"
                          />
                        ) : (
                          <XCircle
                            className="h-4 w-4 shrink-0 text-severity-critical"
                            aria-hidden="true"
                          />
                        )}

                        <span className="min-w-0 flex-1 truncate font-mono text-[0.8125rem] text-ink">
                          {session.target}
                        </span>

                        <Badge tone={ok ? 'success' : 'critical'}>
                          {ok ? 'Success' : 'Failed'}
                        </Badge>

                        <span className="tabular flex shrink-0 items-center gap-1 text-[0.6875rem] text-muted">
                          <Clock className="h-3 w-3" aria-hidden="true" />
                          <time dateTime={session.startedAt.toISOString()}>
                            {session.startedAt.toLocaleString([], {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </time>
                        </span>
                      </div>

                      {session.summary && (
                        <p className="clamp-3 mt-1 pl-6 text-xs text-muted">
                          {session.summary}
                        </p>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
