import { useState, useCallback, useEffect } from 'react'
import { Play, Download, Settings, History } from 'lucide-react'
import { AgentMessages } from './AgentMessages'
import { LogViewer } from './LogViewer'
import { ProgressPhases } from './ProgressPhases'
import { ProviderStatus } from './ProviderStatus'
import { SettingsModal } from './SettingsModal'
import { ScanHistory } from './ScanHistory'
import { useSSE } from '../hooks/useSSE'
import { authFetch } from '../lib/auth'
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
  const [providers, setProviders] = useState<Provider[]>([
    { name: 'claude', status: 'unavailable', priority: 1 },
    { name: 'gemini', status: 'available', priority: 2, lastCheck: new Date() },
    { name: 'openrouter', status: 'unavailable', priority: 2, lastCheck: new Date() },
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
      } else if (event.event === 'report_ready') {
        if (event.report) {
          setReport(event.report)
          addLog('success', 'Report generated and ready for download')
          addMessage('system', '✅ Professional report generated!')
        }
      } else if (event.event === 'complete') {
        addLog('success', 'Security assessment complete')
        addMessage('system', 'Assessment complete! Report ready for download.')
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
      const response = await authFetch('/api/history')
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

  useEffect(() => {
    // Fetch provider status from API
    const fetchProviderStatus = async () => {
      try {
        const response = await authFetch('/api/providers')
        if (!response.ok) throw new Error('Failed to fetch provider status')
        const data = await response.json()

        setProviders((prev) =>
          prev.map((provider) => {
            const statusData = data[provider.name]
            if (statusData) {
              return {
                ...provider,
                status: statusData.available ? 'available' : 'unavailable',
                mode: statusData.mode,
                lastCheck: new Date(),
              }
            }
            return provider
          }),
        )
      } catch (error) {
        console.warn('Could not fetch provider status:', error)
      }
    }

    fetchProviderStatus()
    // Refresh every 5 seconds for near-real-time updates
    const interval = setInterval(fetchProviderStatus, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="flex flex-col h-screen bg-background text-foreground">
      {/* Header */}
      <header className="glass border-b border-white/10 p-6 sticky top-0 z-40">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl md:text-4xl font-bold">
              <span className="bg-gradient-to-r from-blue-400 via-purple-500 to-pink-500 bg-clip-text text-transparent">
                SecureFlow
              </span>
            </h1>
            <p className="text-xs md:text-sm text-muted-foreground mt-1">
              Distributed Security Assessment Engine
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setShowHistory(true)}
              className="p-2 rounded-lg hover:bg-white/10 transition-all duration-300 group"
              title="View scan history"
            >
              <History className="h-5 w-5 group-hover:text-accent transition-colors" />
            </button>
            <button
              onClick={() => setShowSettings(true)}
              className="p-2 rounded-lg hover:bg-white/10 transition-all duration-300 group"
              title="Settings"
            >
              <Settings className="h-5 w-5 group-hover:text-accent transition-colors" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content - 70/30 Split */}
      <div className="flex-1 overflow-hidden flex gap-4 p-4 md:p-6">
        {/* Left Panel - 70% */}
        <div className="flex-1 flex flex-col gap-4 min-h-0">
          {/* Agent Messages */}
          <div className="flex-1 flex flex-col min-h-0 glass rounded-xl p-4 md:p-6">
            <h2 className="text-lg md:text-xl font-semibold text-accent mb-4 uppercase tracking-wider">
              🤖 Agent Activity
            </h2>
            <AgentMessages messages={messages} />
          </div>

          {/* Logs */}
          <div className="flex-1 flex flex-col min-h-0 glass rounded-xl p-4 md:p-6">
            <h2 className="text-lg md:text-xl font-semibold text-accent mb-4 uppercase tracking-wider">
              📋 Live Logs
            </h2>
            <LogViewer logs={logs} />
          </div>
        </div>

        {/* Right Sidebar - 30% (Sticky) */}
        <div className="w-full md:w-[30%] flex flex-col gap-4 min-h-0">
          <div className="sticky top-24 space-y-4 overflow-y-auto max-h-[calc(100vh-8rem)] pr-2">
            {/* Scan Input */}
            <div className="glass rounded-xl p-4 md:p-5">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block mb-3">
                🎯 Target
              </label>
              <input
                type="text"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="IP, hostname, URL"
                className="input-glass w-full mb-3"
                disabled={isScanning}
              />
              <button
                onClick={startScan}
                disabled={isScanning || !target.trim()}
                className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Play className="h-4 w-4" />
                {isScanning ? 'Scanning...' : 'Start Scan'}
              </button>
            </div>

            {/* Phases */}
            <div className="glass rounded-xl p-4 md:p-5">
              <h3 className="text-sm font-semibold text-accent uppercase tracking-wider mb-4">
                📊 Progress
              </h3>
              <ProgressPhases phases={phases} />
            </div>

            {/* Providers */}
            <div className="glass rounded-xl p-4 md:p-5">
              <h3 className="text-sm font-semibold text-accent uppercase tracking-wider mb-4">
                ⚡ Providers
              </h3>
              <ProviderStatus providers={providers} />
            </div>

            {/* Actions */}
            <div className="space-y-2">
              <button
                onClick={downloadReport}
                disabled={!report}
                className="w-full flex items-center justify-center gap-2 btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Download className="h-4 w-4" />
                Download
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
                className="w-full px-4 py-2 glass rounded-lg hover:bg-white/20 font-semibold text-sm transition-all text-destructive"
              >
                Clear
              </button>
            </div>
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
