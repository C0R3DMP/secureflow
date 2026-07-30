import { useState } from 'react'
import { ChevronDown, ChevronRight, PlusCircle, CheckCircle2 } from 'lucide-react'
import { Badge } from './Badge'
import type { Finding, Severity } from '../types'

const SEVERITY_TONE: Record<Severity, 'critical' | 'high' | 'medium' | 'low'> = {
  critical: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
}

function FindingRow({ finding }: { finding: Finding }) {
  return (
    <li className="flex items-center gap-2 py-1 text-xs">
      <Badge tone={SEVERITY_TONE[finding.severity]}>{finding.severity}</Badge>
      <span className="min-w-0 truncate font-mono text-ink-secondary">
        {finding.reference || finding.source}
      </span>
      <span className="ml-auto shrink-0 text-muted">{finding.confidence}</span>
    </li>
  )
}

interface DiffSummaryProps {
  diff: { new: Finding[]; resolved: Finding[] } | null
}

/**
 * "What changed since the last scan of this target" — a recon-native
 * question the scan-history storage already made possible; this just asks
 * it. Only rendered once the server has actually sent a diff (i.e. this
 * target has a prior recorded scan) — a first-ever scan has nothing to
 * diff against, and showing "0 new / 0 resolved" would read as false signal.
 */
export function DiffSummary({ diff }: DiffSummaryProps) {
  const [expanded, setExpanded] = useState<'new' | 'resolved' | null>(null)

  if (!diff || (diff.new.length === 0 && diff.resolved.length === 0)) return null

  return (
    <section className="panel p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="label-caps">Since last scan</span>
      </div>

      <div className="space-y-1.5">
        {diff.new.length > 0 && (
          <div>
            <button
              onClick={() => setExpanded(expanded === 'new' ? null : 'new')}
              className="flex w-full items-center gap-1.5 rounded-sm px-1 py-1 text-left text-xs hover:bg-surface-2"
              aria-expanded={expanded === 'new'}
            >
              {expanded === 'new' ? (
                <ChevronDown className="h-3 w-3 shrink-0 text-ink-muted" aria-hidden="true" />
              ) : (
                <ChevronRight className="h-3 w-3 shrink-0 text-ink-muted" aria-hidden="true" />
              )}
              <PlusCircle className="h-3.5 w-3.5 shrink-0 text-severity-high" aria-hidden="true" />
              <span className="text-ink">
                {diff.new.length} new finding{diff.new.length === 1 ? '' : 's'}
              </span>
            </button>
            {expanded === 'new' && (
              <ul className="ml-6 border-l border-line pl-2">
                {diff.new.map((f, i) => (
                  <FindingRow key={`${f.reference || f.source}-${i}`} finding={f} />
                ))}
              </ul>
            )}
          </div>
        )}

        {diff.resolved.length > 0 && (
          <div>
            <button
              onClick={() => setExpanded(expanded === 'resolved' ? null : 'resolved')}
              className="flex w-full items-center gap-1.5 rounded-sm px-1 py-1 text-left text-xs hover:bg-surface-2"
              aria-expanded={expanded === 'resolved'}
            >
              {expanded === 'resolved' ? (
                <ChevronDown className="h-3 w-3 shrink-0 text-ink-muted" aria-hidden="true" />
              ) : (
                <ChevronRight className="h-3 w-3 shrink-0 text-ink-muted" aria-hidden="true" />
              )}
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-severity-none" aria-hidden="true" />
              <span className="text-ink">
                {diff.resolved.length} resolved since last time
              </span>
            </button>
            {expanded === 'resolved' && (
              <ul className="ml-6 border-l border-line pl-2">
                {diff.resolved.map((f, i) => (
                  <FindingRow key={`${f.reference || f.source}-${i}`} finding={f} />
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
