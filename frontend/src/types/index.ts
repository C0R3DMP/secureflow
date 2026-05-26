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
  status: 'pending' | 'running' | 'completed'
  startTime?: Date
  duration?: number
}

export interface Provider {
  name: 'claude' | 'gemini' | 'ollama' | 'opencode'
  status: 'available' | 'limited' | 'unavailable'
  priority: number
  lastCheck?: Date
}

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
  event: 'start' | 'agent_message' | 'phase_complete' | 'complete' | 'error'
  target?: string
  agent?: AgentRole
  phase?: string
  n?: number
  total?: number
  result?: string
  message?: string
  timestamp?: string
}
