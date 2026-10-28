import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export function Badge({
  className,
  tone = 'neutral',
  ...props
}: HTMLAttributes<HTMLSpanElement> & {
  tone?: 'neutral' | 'accent' | 'ok' | 'warn' | 'lock'
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium tracking-wide',
        tone === 'neutral' && 'bg-paper-2 text-ink-muted',
        tone === 'accent' && 'bg-accent/10 text-accent',
        tone === 'ok' && 'bg-ok/10 text-ok',
        tone === 'warn' && 'bg-warn/10 text-warn',
        tone === 'lock' && 'bg-lock/10 text-lock',
        className,
      )}
      {...props}
    />
  )
}
