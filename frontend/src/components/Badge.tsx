import clsx from 'clsx'

interface BadgeProps {
  variant?: 'default' | 'secondary' | 'destructive' | 'success' | 'warning'
  children: React.ReactNode
  className?: string
}

const variants = {
  default: 'bg-primary text-primary-foreground',
  secondary: 'bg-secondary text-secondary-foreground',
  destructive: 'bg-destructive text-destructive-foreground',
  success: 'bg-success text-success-foreground',
  warning: 'bg-yellow-900/30 text-yellow-200',
}

export function Badge({
  variant = 'default',
  children,
  className,
}: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors',
        variants[variant],
        className,
      )}
    >
      {children}
    </span>
  )
}
