import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  Crosshair,
  Download,
  Eraser,
  FileJson,
  FileText,
  History,
  MessageSquare,
  Moon,
  Play,
  Settings,
  Shield,
  Square,
  Sun,
  Terminal,
} from 'lucide-react'
import { AgentMessages } from './AgentMessages'
import { DiffSummary } from './DiffSummary'
import { LogViewer } from './LogViewer'
import { ProgressPhases } from './ProgressPhases'
import { ProviderStatus } from './ProviderStatus'
import { SettingsModal } from './SettingsModal'
import { ScanHistory } from './ScanHistory'
import { SeverityTiles } from './SeverityTiles'
import { ChatPanel } from './ChatPanel'
import { ReportModal } from './ReportModal'
import { TokenGate } from './TokenGate'
import { Badge } from './Badge'
import { useSSE } from '../hooks/useSSE'
import { useTheme } from '../hooks/useTheme'
import { authFetch, hasToken } from '../lib/auth'
import {
  SEVERITY_ORDER,
  type AgentMessage,
  type Finding,
  type LogEntry,
  type PhaseStatus,
  type Provider,
  type ScanSession,
  type Severity,
  type SeverityCounts,
  type StreamEvent,
} from '../types'

const uid = () =>
  typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `id-${Date.now()}-${Math.random().toString(16).slice(2)}`

const EMPTY_COUNTS: SeverityCounts = { critical: 0, high: 0, medium: 0, low: 0 }

const INITIAL_PHASES: PhaseStatus[] = [
  { name: 'reconnaissance', status: 'pending' },
  { name: 'analysis', status: 'pending' },
  { name: 'reporting', status: 'pending' },
]

/** Providers start 'unknown' — claiming availability before the API answers was a lie. */
const INITIAL_PROVIDERS: Provider[] = [
  { name: 'gemini', status: 'unknown', priority: 1 },
  { name: 'openrouter', status: 'unknown', priority: 2 },
  { name: 'ollama', status: 'unknown', priority: 3 },
  { name: 'claude', status: 'unknown', priority: 4 },
  { name: 'opencode', status: 'unknown', priority: 5 },
]

/**
 * Mirrors the server's validate_target(): hostname, IPv4, IPv6, CIDR or URL.
 * Purely for immediate feedback — the server remains the authority.
 */
function validateTarget(raw: string): string | null {
  const value = raw.trim()
  if (!value) return 'Enter a target to assess.'
  if (value.startsWith('-')) return 'A target cannot start with "-".'
  if (/[\s;|&$`<>()'"\\!*?[\]{}]/.test(value)) return 'Remove shell metacharacters from the target.'
  if (value.length > 253) return 'Target is too long.'

  let host = value
  if (value.includes('://')) {
    try {
      host = new URL(value).hostname
    } catch {
      return 'That URL could not be parsed.'
    }
  }
  if (!host) return 'Could not extract a host from that URL.'
  if (host.includes(':')) return null // IPv6
  const bare = host.split('/')[0]
  if (!/^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*\.?$/.test(bare)) {
    return 'Enter a valid hostname, IP address, CIDR range or URL.'
  }
  return null
}

/**
 * Normalise the server's severity tally.
 *
 * These counts are derived from CVSS baseSeverity values returned by NVD. An
 * earlier version counted severity *words* in the agents' prose, which double
 * counted whenever an agent summarised its own findings — a fabricated metric
 * in a tool whose whole job is accurate reporting.
 */
function readCounts(raw: unknown): SeverityCounts {
  const counts = { ...EMPTY_COUNTS }
  if (!raw || typeof raw !== 'object') return counts
  const source = raw as Record<string, unknown>
  for (const severity of SEVERITY_ORDER) {
    const value = Number(source[severity])
    counts[severity as Severity] = Number.isFinite(value) && value > 0 ? value : 0
  }
  return counts
}

function TabButton({
  active,
  onClick,
  icon,
  label,
  controls,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
  controls: string
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      aria-controls={controls}
      onClick={onClick}
      className={`flex items-center gap-1.5 rounded-sm px-2 py-1 text-[0.8125rem] font-medium transition-colors ${
        active
          ? 'bg-surface-2 text-ink'
          : 'text-muted hover:bg-surface-2 hover:text-ink-secondary'
      }`}
    >
      {icon}
      {label}
    </button>
  )
}

export function Dashboard() {
  const { theme, toggle: toggleTheme } = useTheme()

  const [authed, setAuthed] = useState(true)
  const [target, setTarget] = useState('')
  const [activeTarget, setActiveTarget] = useState('')
  const [targetError, setTargetError] = useState<string | null>(null)
  const [isScanning, setIsScanning] = useState(false)
  const [startedAt, setStartedAt] = useState<Date | null>(null)

  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [phases, setPhases] = useState<PhaseStatus[]>(INITIAL_PHASES)
  const [providers, setProviders] = useState<Provider[]>(INITIAL_PROVIDERS)
  const [severity, setSeverity] = useState<SeverityCounts>(EMPTY_COUNTS)
  const [hasFindings, setHasFindings] = useState(false)
  const [diff, setDiff] = useState<{ new: Finding[]; resolved: Finding[] } | null>(null)

  const [showExportMenu, setShowExportMenu] = useState(false)
  const [bottomTab, setBottomTab] = useState<'log' | 'chat'>('log')
  const [showSettings, setShowSettings] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const [history, setHistory] = useState<ScanSession[]>([])
  const [report, setReport] = useState<string | null>(null)

  const inputRef = useRef<HTMLInputElement>(null)
  /** Set once a scan reports 'complete', to suppress the stream-close error. */
  const completedRef = useRef(false)

  const addLog = useCallback((level: LogEntry['level'], message: string) => {
    setLogs((prev) => [...prev, { id: uid(), timestamp: new Date(), level, message }])
  }, [])

  const addMessage = useCallback((agent: AgentMessage['agent'], message: string) => {
    setMessages((prev) => [...prev, { id: uid(), agent, message, timestamp: new Date() }])
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const response = await authFetch('/api/history')
      if (response.status === 401) {
        setAuthed(false)
        return
      }
      const data = await response.json()
      if (Array.isArray(data.sessions)) {
        setHistory(
          data.sessions.map((s: Record<string, unknown>) => ({
            id: String(s.id),
            target: String(s.target ?? ''),
            type: (s.type as ScanSession['type']) ?? 'security',
            status: (s.status as ScanSession['status']) ?? 'success',
            startedAt: new Date(String(s.timestamp ?? Date.now())),
            summary: s.summary ? String(s.summary) : undefined,
          })),
        )
      }
    } catch {
      addLog('warning', 'Could not load assessment history')
    }
  }, [addLog])

  const fetchProviders = useCallback(async () => {
    try {
      const response = await authFetch('/api/providers')
      if (response.status === 401) {
        setAuthed(false)
        return
      }
      if (!response.ok) return
      const data = await response.json()
      setProviders((prev) =>
        prev.map((provider) => {
          const info = data[provider.name]
          if (!info) return { ...provider, status: 'unavailable' as const }
          const q = info.quota
          return {
            ...provider,
            status: info.available ? ('available' as const) : ('unavailable' as const),
            mode: info.mode ?? undefined,
            lastCheck: new Date(),
            quota: q
              ? {
                  attemptsToday: q.attempts_today ?? 0,
                  knownLimit: q.known_limit ?? null,
                  exhaustedAt: q.exhausted_at ?? null,
                  estimate: true,
                }
              : undefined,
          }
        }),
      )
    } catch {
      /* transient — the next poll will retry */
    }
  }, [])

  // --- streaming ---------------------------------------------------------

  const advancePhase = useCallback((completedIndex: number) => {
    setPhases((prev) =>
      prev.map((phase, index) => {
        if (index < completedIndex) return { ...phase, status: 'completed' }
        if (index === completedIndex) return { ...phase, status: 'completed' }
        if (index === completedIndex + 1) {
          return { ...phase, status: 'running', startTime: new Date() }
        }
        return phase
      }),
    )
  }, [])

  const handleSSEEvent = useCallback(
    (event: StreamEvent) => {
      switch (event.event) {
        case 'start':
          addLog('info', `Assessment started against ${event.target}`)
          break

        case 'agent_message':
          addMessage((event.agent as AgentMessage['agent']) ?? 'system', event.message ?? '')
          break

        case 'findings':
          // Authoritative tally from the server — replace, never accumulate.
          setSeverity(readCounts(event.counts))
          setHasFindings(true)
          break

        case 'diff_ready':
          // Only ever sent when this target has a prior recorded scan.
          setDiff({ new: event.new ?? [], resolved: event.resolved ?? [] })
          break

        case 'phase_complete': {
          const index = (event.n ?? 1) - 1
          advancePhase(index)
          addLog('success', `Phase ${event.n}/${event.total}: ${event.phase} complete`)
          break
        }

        case 'report_ready':
          if (event.report) {
            setReport(event.report)
            setHasFindings(true)
            addLog('success', 'Report generated')
          }
          break

        case 'complete':
          setPhases((prev) => prev.map((p) => ({ ...p, status: 'completed' })))
          addLog('success', 'Assessment complete')
          completedRef.current = true
          setIsScanning(false)
          loadHistory()
          break

        case 'error':
          addLog('error', event.message ?? 'Assessment failed')
          // Mark whichever phase was in flight as failed, rather than leaving
          // its spinner running forever — verified live that a crew failure
          // with no LLM provider previously left the UI showing all phases
          // green with zero agent activity and no report.
          setPhases((prev) => {
            const activeIndex = prev.findIndex((p) => p.status === 'running')
            if (activeIndex === -1) return prev
            return prev.map((p, i) => (i === activeIndex ? { ...p, status: 'failed' } : p))
          })
          completedRef.current = true
          setIsScanning(false)
          break
      }
    },
    [addLog, addMessage, advancePhase, loadHistory],
  )

  const handleSSEError = useCallback(
    (error: Error) => {
      // The server closes the stream right after 'complete', which EventSource
      // surfaces as an error. Reporting that as a failure made every successful
      // scan end with "Connection to server lost".
      if (completedRef.current) return
      addLog('error', error.message)
      setIsScanning(false)
    },
    [addLog],
  )

  useSSE(isScanning ? activeTarget : null, handleSSEEvent, handleSSEError)

  // --- actions -----------------------------------------------------------

  const startScan = () => {
    const problem = validateTarget(target)
    if (problem) {
      setTargetError(problem)
      inputRef.current?.focus()
      return
    }

    setTargetError(null)
    completedRef.current = false
    setActiveTarget(target.trim())
    setMessages([])
    setLogs([])
    setReport(null)
    setSeverity(EMPTY_COUNTS)
    setHasFindings(false)
    setDiff(null)
    setStartedAt(new Date())
    setPhases([
      { name: 'reconnaissance', status: 'running', startTime: new Date() },
      { name: 'analysis', status: 'pending' },
      { name: 'reporting', status: 'pending' },
    ])
    setIsScanning(true)
    addLog('info', `Queued assessment for ${target.trim()}`)
  }

  const stopScan = () => {
    setIsScanning(false)
    addLog('warning', 'Stopped following the assessment stream')
  }

  const downloadReport = () => {
    if (!report) return
    const blob = new Blob([report], { type: 'text/html' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `secureflow-${activeTarget || 'report'}-${
      new Date().toISOString().split('T')[0]
    }.html`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    addLog('info', 'Report downloaded')
  }

  /** Structured, per-CVE findings — severity, confidence, CVE reference — as
   * a file a ticketing system or CI pipeline can actually ingest, unlike the
   * prose/HTML report. Pulled from the just-completed scan via the same
   * export endpoint the CLI's `--format` flag uses. */
  const exportStructured = async (format: 'json' | 'sarif') => {
    setShowExportMenu(false)
    if (!activeTarget) return
    try {
      const response = await authFetch(
        `/api/reports/export?target=${encodeURIComponent(activeTarget)}&format=${format}`,
      )
      if (!response.ok) {
        addLog('error', `Could not export ${format.toUpperCase()} findings`)
        return
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `secureflow-${activeTarget}-${
        new Date().toISOString().split('T')[0]
      }.${format}`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      addLog('info', `${format.toUpperCase()} findings exported`)
    } catch {
      addLog('error', `Could not reach the server to export ${format.toUpperCase()}`)
    }
  }

  const clearOutput = () => {
    setMessages([])
    setLogs([])
    addLog('info', 'Output cleared')
  }

  // --- effects -----------------------------------------------------------

  useEffect(() => {
    if (!hasToken()) {
      // No stored token yet; probe once to learn whether auth is even enabled.
      fetch('/api/providers').then((r) => setAuthed(r.status !== 401)).catch(() => {})
    }
    loadHistory()
    fetchProviders()
  }, [loadHistory, fetchProviders])

  useEffect(() => {
    // Poll faster while a scan is live, slower when idle.
    const interval = setInterval(fetchProviders, isScanning ? 5000 : 20000)
    return () => clearInterval(interval)
  }, [fetchProviders, isScanning])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const onlineProviders = useMemo(
    () => providers.filter((p) => p.status === 'available').length,
    [providers],
  )

  if (!authed) {
    return (
      <TokenGate
        onAuthenticated={() => {
          setAuthed(true)
          loadHistory()
          fetchProviders()
        }}
      />
    )
  }

  return (
    <div className="flex h-screen flex-col bg-canvas text-ink">
      {/* ---------------------------------------------------------------- */}
      {/* Header                                                            */}
      {/* ---------------------------------------------------------------- */}
      <header className="flex shrink-0 items-center gap-4 border-b border-line bg-surface-1 px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <Shield className="h-5 w-5 text-accent" aria-hidden="true" />
          <div className="leading-tight">
            <h1 className="text-sm font-semibold tracking-tight">SecureFlow</h1>
            <p className="text-[0.6875rem] text-muted">Security assessment console</p>
          </div>
        </div>

        <div className="ml-2 hidden items-center gap-2 sm:flex">
          {isScanning ? (
            <Badge tone="accent">
              <span className="dot dot-live bg-accent" aria-hidden="true" />
              Scanning
            </Badge>
          ) : (
            <Badge tone="neutral">Idle</Badge>
          )}
          {activeTarget && (
            <span className="max-w-[16rem] truncate font-mono text-xs text-muted">
              {activeTarget}
            </span>
          )}
        </div>

        <div className="ml-auto flex items-center gap-1">
          <span className="mr-1 hidden items-center gap-1.5 text-xs text-muted md:flex">
            <Activity className="h-3.5 w-3.5" aria-hidden="true" />
            {onlineProviders}/{providers.length} providers
          </span>

          <button
            onClick={toggleTheme}
            className="icon-btn"
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            title="Toggle theme"
          >
            {theme === 'dark' ? (
              <Sun className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Moon className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
          <button
            onClick={() => setShowHistory(true)}
            className="icon-btn"
            aria-label="Open assessment history"
            title="History"
          >
            <History className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            onClick={() => setShowSettings(true)}
            className="icon-btn"
            aria-label="Open settings"
            title="Settings"
          >
            <Settings className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </header>

      {/* ---------------------------------------------------------------- */}
      {/* Command bar                                                       */}
      {/* ---------------------------------------------------------------- */}
      <div className="shrink-0 border-b border-line bg-surface-1 px-4 py-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
          <div className="min-w-0 flex-1">
            <label htmlFor="target" className="sr-only">
              Assessment target
            </label>
            <div className="relative">
              <Crosshair
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted"
                aria-hidden="true"
              />
              <input
                id="target"
                ref={inputRef}
                type="text"
                value={target}
                onChange={(e) => {
                  setTarget(e.target.value)
                  if (targetError) setTargetError(null)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !isScanning) startScan()
                }}
                placeholder="hostname, IP address, CIDR range or URL"
                disabled={isScanning}
                aria-invalid={Boolean(targetError)}
                aria-describedby={targetError ? 'target-error' : undefined}
                className={`field pl-9 pr-16 ${targetError ? 'field-invalid' : ''}`}
              />
              <kbd className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 rounded border border-line-strong px-1.5 py-0.5 text-[0.625rem] text-ink-muted sm:block">
                ⌘K
              </kbd>
            </div>
            {targetError && (
              <p id="target-error" role="alert" className="mt-1.5 text-xs text-severity-critical">
                {targetError}
              </p>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {isScanning ? (
              <button onClick={stopScan} className="btn btn-danger">
                <Square className="h-4 w-4" aria-hidden="true" />
                Stop
              </button>
            ) : (
              <button onClick={startScan} className="btn btn-primary">
                <Play className="h-4 w-4" aria-hidden="true" />
                Start assessment
              </button>
            )}

            <button
              onClick={() => setShowReport(true)}
              disabled={!report}
              className="btn btn-secondary"
              title={report ? 'View report' : 'No report yet'}
            >
              <FileText className="h-4 w-4" aria-hidden="true" />
              <span className="hidden lg:inline">Report</span>
            </button>
            <button
              onClick={downloadReport}
              disabled={!report}
              className="icon-btn"
              aria-label="Download report"
              title="Download report"
            >
              <Download className="h-4 w-4" aria-hidden="true" />
            </button>

            <div className="relative">
              <button
                onClick={() => setShowExportMenu((v) => !v)}
                disabled={!report}
                className="icon-btn"
                aria-label="Export structured findings"
                aria-haspopup="menu"
                aria-expanded={showExportMenu}
                title="Export findings (JSON/SARIF)"
              >
                <FileJson className="h-4 w-4" aria-hidden="true" />
              </button>
              {showExportMenu && (
                <div
                  role="menu"
                  className="absolute right-0 top-full z-10 mt-1 w-40 rounded-md border border-line bg-surface-1 py-1 shadow-lg"
                >
                  <button
                    role="menuitem"
                    onClick={() => exportStructured('json')}
                    className="block w-full px-3 py-1.5 text-left text-xs text-ink-secondary hover:bg-surface-2 hover:text-ink"
                  >
                    Findings (JSON)
                  </button>
                  <button
                    role="menuitem"
                    onClick={() => exportStructured('sarif')}
                    className="block w-full px-3 py-1.5 text-left text-xs text-ink-secondary hover:bg-surface-2 hover:text-ink"
                  >
                    Findings (SARIF)
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Body                                                              */}
      {/* ---------------------------------------------------------------- */}
      {/* On narrow screens the page scrolls and panels take explicit heights;
          only from `lg` up do they share the viewport as flex siblings. Using
          flex ratios inside a scrolling column collapsed them into each other. */}
      <main className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3 lg:flex-row lg:overflow-hidden">
        {/* Primary column */}
        <div className="flex flex-col gap-3 lg:min-h-0 lg:flex-1">
          <section className="panel shrink-0">
            <div className="panel-header">
              <h2 className="panel-title">Findings by severity</h2>
              {isScanning && <span className="text-[0.6875rem] text-muted">live</span>}
            </div>
            <SeverityTiles counts={severity} empty={!hasFindings} />
          </section>

          <section className="panel flex h-[26rem] shrink-0 flex-col overflow-hidden lg:h-auto lg:min-h-[16rem] lg:shrink lg:flex-[3]">
            <div className="panel-header">
              <h2 className="panel-title">
                <Activity className="h-4 w-4 text-ink-muted" aria-hidden="true" />
                Agent activity
              </h2>
              <span className="tabular text-xs text-muted">{messages.length}</span>
            </div>
            <AgentMessages messages={messages} scanning={isScanning} />
          </section>

          <section className="panel flex h-[20rem] shrink-0 flex-col overflow-hidden lg:h-auto lg:min-h-[12rem] lg:shrink lg:flex-[2]">
            <div className="panel-header">
              <div className="flex items-center gap-1" role="tablist" aria-label="Output view">
                <TabButton
                  active={bottomTab === 'log'}
                  onClick={() => setBottomTab('log')}
                  icon={<Terminal className="h-3.5 w-3.5" aria-hidden="true" />}
                  label="Event log"
                  controls="panel-log"
                />
                <TabButton
                  active={bottomTab === 'chat'}
                  onClick={() => setBottomTab('chat')}
                  icon={<MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />}
                  label="Ask AI"
                  controls="panel-chat"
                />
              </div>

              {bottomTab === 'log' && (
                <button
                  onClick={clearOutput}
                  className="btn btn-ghost px-2 py-1 text-xs"
                  disabled={logs.length === 0 && messages.length === 0}
                >
                  <Eraser className="h-3.5 w-3.5" aria-hidden="true" />
                  Clear
                </button>
              )}
            </div>

            {/* Both panels stay mounted so switching tabs never discards an
                in-flight reply or the accumulated log. */}
            <div
              id="panel-log"
              role="tabpanel"
              hidden={bottomTab !== 'log'}
              className={bottomTab === 'log' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}
            >
              <LogViewer logs={logs} />
            </div>
            <div
              id="panel-chat"
              role="tabpanel"
              hidden={bottomTab !== 'chat'}
              className={bottomTab === 'chat' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}
            >
              <ChatPanel target={activeTarget || undefined} />
            </div>
          </section>
        </div>

        {/* Sidebar */}
        <aside className="flex w-full shrink-0 flex-col gap-3 lg:w-80 lg:min-h-0 lg:overflow-y-auto">
          <section className="panel p-4">
            <ProgressPhases phases={phases} />
            {startedAt && (
              <p className="mt-3 border-t border-line pt-3 text-xs text-muted">
                Started {startedAt.toLocaleTimeString()}
              </p>
            )}
          </section>

          <DiffSummary diff={diff} />

          <section className="panel p-4">
            <ProviderStatus providers={providers} onRefresh={fetchProviders} />
          </section>
        </aside>
      </main>

      {/* Modals */}
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
      {showHistory && (
        <ScanHistory
          sessions={history}
          onClose={() => setShowHistory(false)}
          onSelect={(t) => setTarget(t)}
        />
      )}
      {showReport && report && (
        <ReportModal
          report={report}
          target={activeTarget}
          onClose={() => setShowReport(false)}
          onDownload={downloadReport}
        />
      )}
    </div>
  )
}
