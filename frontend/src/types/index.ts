export type AgentRole = 'recon' | 'analyst' | 'reporter' | 'system' | 'architect' | 'developer' | 'reviewer'

export interface AgentMessage {
  id: string
  agent: AgentRole
  message: string
  timestamp: Date
}

export interface LogEntry {
  id: string
  timestamp: Date
  level: 'info' | 'warning' | 'error' | 'success'
  message: string
}

export type Phase = 'reconnaissance' | 'analysis' | 'reporting'

export interface PhaseStatus {
  name: Phase
  status: 'pending' | 'running' | 'completed' | 'failed'
  startTime?: Date
  duration?: number
}

/**
 * Best-effort, locally-tracked request budget for one provider — see
 * secureflow/quota.py. Never authoritative: the server can't query a
 * provider's real remaining quota in advance, only report what this process
 * has itself attempted today (UTC) plus whatever a 429 has revealed.
 */
export interface QuotaSnapshot {
  attemptsToday: number
  knownLimit: number | null
  exhaustedAt: string | null
  estimate: true
}

export interface Provider {
  name: 'claude' | 'gemini' | 'openrouter' | 'ollama' | 'opencode'
  /** 'unknown' until the first /api/providers response lands. */
  status: 'available' | 'limited' | 'unavailable' | 'unknown'
  priority: number
  lastCheck?: Date
  mode?: 'cli' | 'api'
  quota?: QuotaSnapshot
}

/** Ordered from most to least severe. */
export type Severity = 'critical' | 'high' | 'medium' | 'low'

export const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low']

export type SeverityCounts = Record<Severity, number>

export interface ScanSession {
  id: string
  target: string
  type: 'security' | 'dev'
  status: 'success' | 'error'
  startedAt: Date
  completedAt?: Date
  summary?: string
}

export interface StreamEvent {
  event:
    | 'start'
    | 'agent_message'
    | 'phase_complete'
    | 'findings'
    | 'report_ready'
    | 'complete'
    | 'error'
  target?: string
  agent?: AgentRole
  phase?: string
  n?: number
  total?: number
  result?: string
  message?: string
  timestamp?: string
  report?: string
  /** Severity tally from the server, present on 'findings' events. */
  counts?: Partial<SeverityCounts>
}
