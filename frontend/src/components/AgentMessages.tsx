import { useEffect, useRef, useState } from 'react'
import { Radar, Microscope, FileText, Cog, PenTool, Code2, ClipboardCheck } from 'lucide-react'
import clsx from 'clsx'
import type { AgentMessage, AgentRole } from '../types'

/**
 * Agents are distinct identities, so they take categorical hues — assigned in a
 * fixed order and never cycled. They are also always labelled by name and icon,
 * so the hue is reinforcement rather than the sole carrier of identity.
 */
const AGENT: Record<AgentRole, { label: string; icon: typeof Radar; accent: string }> = {
  recon: { label: 'Recon', icon: Radar, accent: 'text-[#3987e5] border-l-[#3987e5]' },
  analyst: { label: 'Analyst', icon: Microscope, accent: 'text-[#d95926] border-l-[#d95926]' },
  reporter: { label: 'Reporter', icon: FileText, accent: 'text-[#199e70] border-l-[#199e70]' },
  architect: { label: 'Architect', icon: PenTool, accent: 'text-[#9085e9] border-l-[#9085e9]' },
  developer: { label: 'Developer', icon: Code2, accent: 'text-[#c98500] border-l-[#c98500]' },
  reviewer: { label: 'Reviewer', icon: ClipboardCheck, accent: 'text-[#d55181] border-l-[#d55181]' },
  system: { label: 'System', icon: Cog, accent: 'text-ink-muted border-l-line-strong' },
}

const time = (d: Date) =>
  d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

interface AgentMessagesProps {
  messages: AgentMessage[]
  scanning: boolean
}

export function AgentMessages({ messages, scanning }: AgentMessagesProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(true)

  // Follow the tail only while the operator is already at the bottom —
  // auto-scrolling out from under someone reading history is hostile.
  useEffect(() => {
    const el = scrollRef.current
    if (el && pinned) el.scrollTop = el.scrollHeight
  }, [messages, pinned])

  const onScroll = () => {
    const el = scrollRef.current
    if (!el) return
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < 48)
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3"
        role="log"
        aria-live="polite"
        aria-label="Agent activity"
      >
        {messages.length === 0 ? (
          <EmptyState scanning={scanning} />
        ) : (
          messages.map((msg) => {
            const meta = AGENT[msg.agent] ?? AGENT.system
            const Icon = meta.icon
            return (
              <article
                key={msg.id}
                className={clsx(
                  'animate-fade-in rounded-sm border-l-2 bg-surface-2/60 py-2 pl-3 pr-3',
                  meta.accent,
                )}
              >
                <header className="mb-1 flex items-center gap-2">
                  <Icon className={clsx('h-3.5 w-3.5 shrink-0', meta.accent)} aria-hidden="true" />
                  <span className="text-xs font-semibold text-ink">{meta.label}</span>
                  <time className="tabular ml-auto font-mono text-[0.6875rem] text-muted">
                    {time(msg.timestamp)}
                  </time>
                </header>
                <p className="whitespace-pre-wrap break-words text-[0.8125rem] leading-relaxed text-secondary">
                  {msg.message}
                </p>
              </article>
            )
          })
        )}
      </div>

      {!pinned && (
        <button
          onClick={() => setPinned(true)}
          className="btn btn-secondary absolute bottom-3 left-1/2 -translate-x-1/2 py-1 text-xs shadow-md"
        >
          Jump to latest
        </button>
      )}
    </div>
  )
}

function EmptyState({ scanning }: { scanning: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 py-10 text-center">
      <Radar
        className={clsx('h-7 w-7 text-ink-muted', scanning && 'animate-spin')}
        aria-hidden="true"
      />
      <p className="text-sm text-secondary">
        {scanning ? 'Waiting for the first agent response…' : 'No agent activity yet'}
      </p>
      {!scanning && (
        <p className="max-w-xs text-xs text-muted">
          Enter a target and start an assessment to watch the recon, analyst and
          reporter agents collaborate here.
        </p>
      )}
    </div>
  )
}
