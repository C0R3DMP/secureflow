import { X, CheckCircle2, XCircle, Clock } from 'lucide-react'
import type { ScanSession } from '../types'

interface ScanHistoryProps {
  sessions: ScanSession[]
  onClose: () => void
}

export function ScanHistory({ sessions, onClose }: ScanHistoryProps) {
  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-card border border-border rounded-lg shadow-lg max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-border sticky top-0 bg-card">
          <h2 className="text-lg font-bold text-foreground">📋 Scan History</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-card/80 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {sessions.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No scans recorded yet
            </div>
          ) : (
            <div className="space-y-3">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className="flex items-center gap-4 p-4 rounded-lg border border-border bg-card/50 hover:border-primary/50 transition-colors"
                >
                  {/* Icon */}
                  <div>
                    {session.status === 'success' ? (
                      <CheckCircle2 className="h-5 w-5 text-success" />
                    ) : (
                      <XCircle className="h-5 w-5 text-destructive" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className="font-semibold text-foreground">
                        {session.target}
                      </p>
                      <span className="text-xs px-2 py-0.5 rounded bg-primary/20 text-primary">
                        {session.type}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {session.summary ||
                        (session.status === 'success'
                          ? 'Assessment completed'
                          : 'Assessment failed')}
                    </p>
                  </div>

                  {/* Time */}
                  <div className="text-right">
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {session.startedAt.toLocaleTimeString()}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {session.startedAt.toLocaleDateString()}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-border">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 bg-card border border-border hover:bg-card/80 rounded-md font-semibold transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
