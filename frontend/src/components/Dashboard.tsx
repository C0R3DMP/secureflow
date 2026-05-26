import { useState, useCallback, useEffect } from 'react'
import { Play, Download, Settings, History } from 'lucide-react'
import { AgentMessages } from './AgentMessages'
import { LogViewer } from './LogViewer'
import { ProgressPhases } from './ProgressPhases'
import { ProviderStatus } from './ProviderStatus'
import { SettingsModal } from './SettingsModal'
import { ScanHistory } from './ScanHistory'
import { useSSE } from '../hooks/useSSE'
import type {
  AgentMessage,
  LogEntry,
  PhaseStatus,
  Provider,
  StreamEvent,
  ScanSession,
} from '../types'

// UUID helper
function uuidv4(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export function Dashboard() {
  const [target, setTarget] = useState('')
  const [isScanning, setIsScanning] = useState(false)
  const [messages, setMessages] = useState<AgentMessage[]>([
    {
      id: uuidv4(),
      agent: 'system',
      message: 'Dashboard initialized. Ready for security assessment.',
      timestamp: new Date(),
    },
  ])
  const [logs, setLogs] = useState<LogEntry[]>([
    {
      id: uuidv4(),
      timestamp: new Date(),
      level: 'info',
      message: 'SecureFlow Dashboard loaded',
    },
  ])
  const [phases, setPhases] = useState<PhaseStatus[]>([
    { name: 'reconnaissance', status: 'pending' },
    { name: 'analysis', status: 'pending' },
    { name: 'reporting', status: 'pending' },
  ])
  const [providers] = useState<Provider[]>([
    { name: 'claude', status: 'unavailable', priority: 1 },
    { name: 'gemini', status: 'available', priority: 2, lastCheck: new Date() },
    { name: 'ollama', status: 'available', priority: 3, lastCheck: new Date() },
    { name: 'opencode', status: 'unavailable', priority: 4 },
  ])
  const [showSettings, setShowSettings] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState<ScanSession[]>([])
  const [report, setReport] = useState<string | null>(null)

  const addLog = useCallback(
    (level: LogEntry['level'], message: string) => {
      setLogs((prev) => [
        ...prev,
        {
          id: uuidv4(),
          timestamp: new Date(),
          level,
          message,
        },
      ])
    },
    [],
  )

  const addMessage = useCallback(
    (agent: AgentMessage['agent'], message: string) => {
      setMessages((prev) => [
        ...prev,
        {
          id: uuidv4(),
          agent,
          message,
          timestamp: new Date(),
        },
      ])
    },
    [],
  )

  const handleSSEEvent = useCallback(
    (event: StreamEvent) => {
      if (event.event === 'start') {
        addLog('info', `Scan started: ${event.target}`)
      } else if (event.event === 'agent_message') {
        addMessage(event.agent as any || 'system', event.message || '')
        addLog('info', `[${event.agent}] ${event.message}`)
      } else if (event.event === 'phase_complete') {
        const phaseMap: Record<string, PhaseStatus['name']> = {
          'Reconnaissance': 'reconnaissance',
          'Vulnerability Analysis': 'analysis',
          'Report Generation': 'reporting',
        }
        const phaseName = phaseMap[event.phase || '']
        if (phaseName) {
          setPhases((prev) =>
            prev.map((p) =>
              p.name === phaseName ? { ...p, status: 'completed' as const } : p,
            ),
          )
        }
        addMessage('system', `✓ ${event.phase} complete (${event.n}/${event.total})`)
        addLog('success', `Phase ${event.n}/${event.total}: ${event.phase}`)
      } else if (event.event === 'complete') {
        addLog('success', 'Security assessment complete')
        addMessage('system', 'Assessment complete! Report ready for download.')
        setReport(event.result || null)
        setIsScanning(false)
        loadHistory()
      } else if (event.event === 'error') {
        addLog('error', event.message || 'Unknown error occurred')
        setIsScanning(false)
      }
    },
    [addLog, addMessage],
  )

  const handleSSEError = useCallback(
    (error: Error) => {
      addLog('error', error.message)
      setIsScanning(false)
    },
    [addLog],
  )

  useSSE(isScanning ? target : null, handleSSEEvent, handleSSEError)

  const startScan = async () => {
    if (!target.trim()) {
      addLog('warning', 'Please enter a target')
      return
    }

    setIsScanning(true)
    setMessages([])
    setLogs([])
    setReport(null)
    setPhases([
      { name: 'reconnaissance', status: 'pending', startTime: new Date() },
      { name: 'analysis', status: 'pending' },
      { name: 'reporting', status: 'pending' },
    ])

    addLog('info', `Starting scan on target: ${target}`)
    addMessage('system', `Initializing security assessment for ${target}`)
  }

  const downloadReport = () => {
    if (!report) {
      addLog('warning', 'No report available')
      return
    }

    const element = document.createElement('a')
    const file = new Blob([report], { type: 'text/html' })
    element.href = URL.createObjectURL(file)
    element.download = `secureflow-report-${target}-${new Date().toISOString().split('T')[0]}.html`
    document.body.appendChild(element)
    element.click()
    document.body.removeChild(element)
    addLog('info', 'Report downloaded')
  }

  const loadHistory = async () => {
    try {
      const response = await fetch('/api/history')
      const data = await response.json()
      if (data.sessions) {
        setHistory(
          data.sessions.map((s: any) => ({
            id: s.id,
            target: s.target,
            type: s.type || 'security',
            status: s.status,
            startedAt: new Date(s.timestamp),
            summary: s.summary,
          })),
        )
      }
    } catch (e) {
      addLog('warning', 'Could not load history')
    }
  }

  useEffect(() => {
    loadHistory()
  }, [])

  return (
    <div className="flex flex-col h-screen bg-background text-foreground">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur-sm p-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-primary via-accent to-primary bg-clip-text text-transparent">
              SecureFlow AI
            </h1>
            <p className="text-xs text-muted-foreground">
              Professional Distributed Security Assessment Engine
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setShowHistory(true)}
              className="p-2 rounded-lg hover:bg-card transition-colors"
              title="View scan history"
            >
              <History className="h-5 w-5" />
            </button>
            <button
              onClick={() => setShowSettings(true)}
              className="p-2 rounded-lg hover:bg-card transition-colors"
              title="Settings"
            >
              <Settings className="h-5 w-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden grid grid-cols-4 gap-4 p-4 max-w-7xl mx-auto w-full">
        {/* Left Panel - Messages and Logs */}
        <div className="col-span-3 flex flex-col gap-4 min-h-0">
          {/* Agent Messages */}
          <div className="flex-1 flex flex-col min-h-0">
            <h2 className="text-sm font-semibold text-primary uppercase tracking-wider mb-2">
              Agent Collaboration
            </h2>
            <AgentMessages messages={messages} />
          </div>

          {/* Logs */}
          <div className="flex-1 flex flex-col min-h-0">
            <h2 className="text-sm font-semibold text-primary uppercase tracking-wider mb-2">
              Live Logs
            </h2>
            <LogViewer logs={logs} />
          </div>
        </div>

        {/* Right Sidebar */}
        <div className="col-span-1 flex flex-col gap-4 min-h-0">
          {/* Scan Input */}
          <div className="bg-card/50 rounded-lg border border-border p-4">
            <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-2">
              Target
            </label>
            <input
              type="text"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="IP, hostname, or URL"
              className="w-full px-3 py-2 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary mb-3"
              disabled={isScanning}
            />
            <button
              onClick={startScan}
              disabled={isScanning || !target.trim()}
              className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed text-primary-foreground px-4 py-2 rounded-md font-semibold text-sm transition-colors"
            >
              <Play className="h-4 w-4" />
              {isScanning ? 'Scanning...' : 'Start Scan'}
            </button>
          </div>

          {/* Phases */}
          <div className="bg-card/50 rounded-lg border border-border p-4 flex-1 overflow-y-auto">
            <h3 className="text-xs font-semibold text-primary uppercase tracking-wider mb-3">
              Progress Phases
            </h3>
            <ProgressPhases phases={phases} />
          </div>

          {/* Providers */}
          <div className="bg-card/50 rounded-lg border border-border p-4">
            <h3 className="text-xs font-semibold text-primary uppercase tracking-wider mb-3">
              LLM Providers
            </h3>
            <ProviderStatus providers={providers} />
          </div>

          {/* Actions */}
          <div className="space-y-2">
            <button
              onClick={downloadReport}
              disabled={!report}
              className="w-full flex items-center justify-center gap-2 bg-success hover:bg-success/90 disabled:opacity-50 disabled:cursor-not-allowed text-success-foreground px-4 py-2 rounded-md font-semibold text-sm transition-colors"
            >
              <Download className="h-4 w-4" />
              Download Report
            </button>
            <button
              onClick={() => {
                setMessages([])
                setLogs([
                  {
                    id: uuidv4(),
                    timestamp: new Date(),
                    level: 'info',
                    message: 'Logs cleared',
                  },
                ])
              }}
              className="w-full px-4 py-2 bg-card hover:bg-card/80 border border-border rounded-md font-semibold text-sm transition-colors text-destructive"
            >
              Clear Logs
            </button>
          </div>
        </div>
      </div>

      {/* Modals */}
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
      {showHistory && (
        <ScanHistory sessions={history} onClose={() => setShowHistory(false)} />
      )}
    </div>
  )
}
