import { api } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state'
import { useAsync } from '@/hooks/useAsync'
import { shortId } from '@/lib/utils'

function toneFor(status: string): 'ok' | 'warn' | 'neutral' | 'accent' {
  if (status === 'completed') return 'ok'
  if (status === 'failed') return 'warn'
  if (status === 'cancelled') return 'neutral'
  if (status === 'pending' || status === 'running') return 'warn'
  return 'accent'
}

export function JobsPage() {
  const { data, error, loading, reload } = useAsync(() => api.listJobs(), [])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl">Jobs / history</h1>
          <p className="text-sm text-ink-muted">Compose, revise, ref-pipeline, and A/B job records (SQLite).</p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void reload()}>
          Refresh
        </Button>
      </div>

      {loading ? <LoadingState label="Loading jobs…" /> : null}
      {error ? <ErrorState message={error} onRetry={() => void reload()} /> : null}

      {!loading && !error && (!data || data.length === 0) ? (
        <EmptyState
          title="No jobs yet"
          description="Run compose / revise / reference pipeline from the Workspace or References pages."
        />
      ) : null}

      {data && data.length > 0 ? (
        <ul className="space-y-2">
          {data.map((job) => (
            <li
              key={job.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-white/70 px-4 py-3 animate-fade-up"
            >
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-sm">{job.kind}</span>
                  <Badge tone={toneFor(job.status)}>{job.status}</Badge>
                </div>
                <p className="mt-1 text-xs text-ink-muted">
                  {shortId(job.id, 10)}
                  {job.project_id ? ` · project ${shortId(job.project_id)}` : ''}
                  {job.created_at ? ` · ${new Date(job.created_at).toLocaleString()}` : ''}
                </p>
                {job.detail && Object.keys(job.detail).length > 0 ? (
                  <p className="mt-1 max-w-xl truncate text-xs text-ink-muted">
                    {JSON.stringify(job.detail)}
                  </p>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
