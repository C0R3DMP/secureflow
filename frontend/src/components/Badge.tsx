import type { ReactNode } from 'react'
import clsx from 'clsx'

type Tone = 'neutral' | 'accent' | 'critical' | 'high' | 'medium' | 'low' | 'success'

const TONES: Record<Tone, string> = {
  neutral: 'bg-surface-2 text-ink-secondary border-line-strong',
  accent: 'bg-accent-subtle text-accent border-accent/30',
  critical: 'bg-severity-critical/10 text-severity-critical border-severity-critical/35',
  high: 'bg-severity-high/10 text-severity-high border-severity-high/35',
  medium: 'bg-severity-medium/10 text-severity-medium border-severity-medium/35',
  low: 'bg-severity-low/10 text-severity-low border-severity-low/35',
  success: 'bg-severity-none/10 text-severity-none border-severity-none/35',
}

interface BadgeProps {
  children: ReactNode
  tone?: Tone
  className?: string
}

/** Small status pill. Always carries a text label — never colour alone. */
export function Badge({ children, tone = 'neutral', className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5',
        'text-[0.6875rem] font-medium leading-none',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
