import { ShieldAlert, ShieldX, ShieldQuestion, Info, ShieldCheck } from 'lucide-react'
import { SEVERITY_ORDER, type Severity, type SeverityCounts } from '../types'

/**
 * A KPI row of stat tiles — the right form for a handful of headline numbers.
 *
 * Severity is rendered as separated, individually labelled tiles rather than a
 * stacked bar: red/orange/yellow sit too close together to be told apart as
 * adjacent segments, and every tile pairs its status colour with an icon and a
 * text label so colour never carries the meaning alone.
 */

const TILE: Record<Severity, { label: string; icon: typeof ShieldAlert; color: string }> = {
  critical: { label: 'Critical', icon: ShieldX, color: 'text-severity-critical' },
  high: { label: 'High', icon: ShieldAlert, color: 'text-severity-high' },
  medium: { label: 'Medium', icon: ShieldQuestion, color: 'text-severity-medium' },
  low: { label: 'Low', icon: Info, color: 'text-severity-low' },
}

interface SeverityTilesProps {
  counts: SeverityCounts
  /** No scan has produced findings yet. */
  empty?: boolean
}

export function SeverityTiles({ counts, empty = false }: SeverityTilesProps) {
  const total = SEVERITY_ORDER.reduce((sum, s) => sum + (counts[s] ?? 0), 0)

  if (empty) {
    return (
      <div className="flex items-center gap-2.5 px-4 py-3 text-sm text-muted">
        <ShieldQuestion className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span>No findings yet — run an assessment to populate this summary.</span>
      </div>
    )
  }

  if (total === 0) {
    return (
      <div className="flex items-center gap-2.5 px-4 py-3 text-sm">
        <ShieldCheck className="h-4 w-4 shrink-0 text-severity-none" aria-hidden="true" />
        <span className="text-secondary">
          No findings reported for this target.
        </span>
      </div>
    )
  }

  return (
    <div
      className="grid grid-cols-2 gap-2 p-3 sm:grid-cols-4"
      role="group"
      aria-label="Findings by severity"
    >
      {SEVERITY_ORDER.map((severity) => {
        const { label, icon: Icon, color } = TILE[severity]
        const value = counts[severity] ?? 0
        const share = total > 0 ? Math.round((value / total) * 100) : 0

        return (
          <div
            key={severity}
            className="panel-inset px-3 py-2.5"
            // The accessible name states severity and count together, so the
            // reading never depends on the tile's colour.
            aria-label={`${label}: ${value} finding${value === 1 ? '' : 's'}, ${share}% of total`}
          >
            <div className="flex items-center gap-1.5">
              <Icon className={`h-3.5 w-3.5 shrink-0 ${color}`} aria-hidden="true" />
              <span className="label-caps">{label}</span>
            </div>
            <div className="mt-1.5 flex items-baseline gap-1.5">
              <span className={`tabular text-2xl font-semibold leading-none ${color}`}>
                {value}
              </span>
              {value > 0 && (
                <span className="tabular text-xs text-muted">{share}%</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
