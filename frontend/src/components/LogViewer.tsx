import { useEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, AlertTriangle, CheckCircle2, Info, Search } from 'lucide-react'
import clsx from 'clsx'
import type { LogEntry } from '../types'

/** Reserved status colours; each pairs with an icon and the level in text. */
const LEVEL: Record<LogEntry['level'], { icon: typeof Info; color: string; label: string }> = {
  info: { icon: Info, color: 'text-severity-low', label: 'INFO' },
  success: { icon: CheckCircle2, color: 'text-severity-none', label: 'OK' },
  warning: { icon: AlertTriangle, color: 'text-severity-medium', label: 'WARN' },
  error: { icon: AlertCircle, color: 'text-severity-critical', label: 'ERROR' },
}

const time = (d: Date) =>
  d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

interface LogViewerProps {
  logs: LogEntry[]
}

export function LogViewer({ logs }: LogViewerProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(true)
  const [query, setQuery] = useState('')
  const [levels, setLevels] = useState<Set<LogEntry['level']>>(new Set())

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return logs.filter((log) => {
      if (levels.size > 0 && !levels.has(log.level)) return false
      if (needle && !log.message.toLowerCase().includes(needle)) return false
      return true
    })
  }, [logs, query, levels])

  useEffect(() => {
    const el = scrollRef.current
    if (el && pinned) el.scrollTop = el.scrollHeight
  }, [visible, pinned])

  const toggleLevel = (level: LogEntry['level']) => {
    setLevels((prev) => {
      const next = new Set(prev)
      next.has(level) ? next.delete(level) : next.add(level)
      return next
    })
  }

  const counts = useMemo(() => {
    const c = { info: 0, success: 0, warning: 0, error: 0 }
    for (const log of logs) c[log.level] += 1
    return c
  }, [logs])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Filters sit in one row above the content. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <div className="relative min-w-[8rem] flex-1 basis-full sm:basis-auto">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted"
            aria-hidden="true"
          />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter logs"
            aria-label="Filter logs by text"
            className="field py-1 pl-8 text-xs"
          />
        </div>

        <div className="flex shrink-0 items-center gap-1" role="group" aria-label="Filter by level">
          {(Object.keys(LEVEL) as LogEntry['level'][]).map((level) => {
            const active = levels.has(level)
            return (
              <button
                key={level}
                onClick={() => toggleLevel(level)}
                aria-pressed={active}
                className={clsx(
                  'rounded-sm border px-1.5 py-1 text-[0.6875rem] font-medium transition-colors',
                  active
                    ? 'border-accent bg-accent-subtle text-accent'
                    : 'border-line text-muted hover:text-ink',
                )}
              >
                {LEVEL[level].label}
                <span className="tabular ml-1 opacity-60">{counts[level]}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div
        ref={scrollRef}
        onScroll={() => {
          const el = scrollRef.current
          if (el) setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 40)
        }}
        className="min-h-0 flex-1 overflow-y-auto px-2 py-2 font-mono text-xs"
      >
        {visible.length === 0 ? (
          <p className="py-8 text-center text-xs text-muted">
            {logs.length === 0 ? 'No log output yet' : 'No entries match this filter'}
          </p>
        ) : (
          <ul className="space-y-px">
            {visible.map((log) => {
              const { icon: Icon, color, label } = LEVEL[log.level]
              return (
                <li
                  key={log.id}
                  className="flex items-start gap-2 rounded-sm px-1.5 py-1 hover:bg-surface-2"
                >
                  <time className="tabular shrink-0 text-ink-muted">
                    {time(log.timestamp)}
                  </time>
                  <span className={clsx('flex w-14 shrink-0 items-center gap-1', color)}>
                    <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
                    {label}
                  </span>
                  <span className="min-w-0 flex-1 break-words text-secondary">
                    {log.message}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
