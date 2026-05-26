import { useEffect, useRef } from 'react'
import type { LogEntry } from '../types'
import clsx from 'clsx'

const levelColors = {
  info: 'text-blue-400 bg-blue-500/10',
  warning: 'text-yellow-400 bg-yellow-500/10',
  error: 'text-red-400 bg-red-500/10',
  success: 'text-green-400 bg-green-500/10',
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
      className="flex-1 overflow-y-auto p-3 bg-card/50 rounded-lg border border-border font-mono text-xs"
    >
      {logs.length === 0 ? (
        <div className="text-muted-foreground text-center py-8">
          No logs yet
        </div>
      ) : (
        <div className="space-y-1">
          {logs.map((log) => (
            <div
              key={log.id}
              className={clsx(
                'px-2 py-1 rounded flex gap-3 items-start',
                levelColors[log.level],
              )}
            >
              <span className="text-muted-foreground shrink-0">
                [{log.timestamp.toLocaleTimeString()}]
              </span>
              <span className="font-bold shrink-0 w-10">
                {log.level.toUpperCase()}
              </span>
              <span className="flex-1 break-words">{log.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
