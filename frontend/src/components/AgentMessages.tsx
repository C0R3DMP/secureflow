import { useEffect, useRef } from 'react'
import { MessageCircle } from 'lucide-react'
import type { AgentMessage } from '../types'
import clsx from 'clsx'

const agentColors = {
  recon: 'border-l-blue-500 bg-blue-500/5',
  analyst: 'border-l-purple-500 bg-purple-500/5',
  reporter: 'border-l-green-500 bg-green-500/5',
  architect: 'border-l-indigo-500 bg-indigo-500/5',
  developer: 'border-l-cyan-500 bg-cyan-500/5',
  reviewer: 'border-l-amber-500 bg-amber-500/5',
  system: 'border-l-yellow-500 bg-yellow-500/5',
}

const agentLabels = {
  recon: 'Reconnaissance',
  analyst: 'Analyst',
  reporter: 'Reporter',
  architect: 'Architect',
  developer: 'Developer',
  reviewer: 'Reviewer',
  system: 'System',
}

interface AgentMessagesProps {
  messages: AgentMessage[]
}

export function AgentMessages({ messages }: AgentMessagesProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto space-y-3 p-4 bg-card/50 rounded-lg border border-border"
    >
      {messages.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
          <MessageCircle className="h-12 w-12 mb-2 opacity-50" />
          <p>Waiting for agent collaboration...</p>
        </div>
      ) : (
        messages.map((msg) => (
          <div
            key={msg.id}
            className={clsx(
              'rounded border-l-4 p-3 backdrop-blur-sm',
              agentColors[msg.agent],
            )}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-bold text-primary uppercase tracking-wider">
                {agentLabels[msg.agent]}
              </span>
              <span className="text-xs text-muted-foreground">
                {msg.timestamp.toLocaleTimeString()}
              </span>
            </div>
            <p className="text-sm text-foreground/90">{msg.message}</p>
          </div>
        ))
      )}
    </div>
  )
}
