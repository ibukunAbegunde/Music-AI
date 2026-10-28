import { AlertCircle, Loader2, Music2 } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Button } from './button'

export function LoadingState({ label = 'Working…' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-ink-muted animate-fade-up">
      <Loader2 className="h-6 w-6 animate-spin text-accent" />
      <p className="text-sm">{label}</p>
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center animate-fade-up">
      <div className="rounded-full bg-paper-2 p-3 text-accent">
        <Music2 className="h-6 w-6" />
      </div>
      <div>
        <h3 className="font-display text-lg text-ink">{title}</h3>
        {description ? <p className="mt-1 max-w-sm text-sm text-ink-muted">{description}</p> : null}
      </div>
      {action}
    </div>
  )
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-start gap-3 rounded-lg border border-danger/20 bg-danger/5 p-4 text-sm animate-fade-up',
      )}
      role="alert"
    >
      <div className="flex items-start gap-2 text-danger">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <p>{message}</p>
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  )
}
