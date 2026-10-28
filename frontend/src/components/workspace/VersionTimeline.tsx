import { RotateCcw } from 'lucide-react'
import type { VersionEntry } from '@/types/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { shortId } from '@/lib/utils'

export function VersionTimeline({
  versions,
  onRestore,
  restoringId,
}: {
  versions: VersionEntry[]
  onRestore?: (versionId: string) => void
  restoringId?: string | null
}) {
  if (!versions.length) {
    return <p className="text-sm text-ink-muted">No versions yet — compose to create a tip.</p>
  }
  return (
    <ol className="relative space-y-3 border-l border-line pl-4">
      {[...versions].reverse().map((v, i) => (
        <li key={v.version_id} className="relative animate-fade-up" style={{ animationDelay: `${i * 40}ms` }}>
          <span className="absolute -left-[1.3rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-accent bg-paper" />
          <div className="rounded-md border border-line bg-white/70 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <code className="text-xs text-ink">{shortId(v.version_id)}</code>
                {i === 0 ? <Badge tone="accent">tip</Badge> : null}
                {v.seed != null ? <Badge>seed {v.seed}</Badge> : null}
              </div>
              {onRestore && v.restorable && i !== 0 ? (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={restoringId === v.version_id}
                  onClick={() => onRestore(v.version_id)}
                >
                  <RotateCcw className="h-3 w-3" />
                  Restore
                </Button>
              ) : null}
            </div>
            <p className="mt-1.5 text-sm text-ink">{v.one_line_diff || '—'}</p>
            {v.musical_diff ? (
              <p className="mt-1 text-xs text-ink-muted">
                roles: {v.musical_diff.roles_changed.join(', ') || 'none'}
                {v.musical_diff.locked_roles_respected != null
                  ? ` · locks ${v.musical_diff.locked_roles_respected ? 'honored' : 'broken'}`
                  : ''}
              </p>
            ) : null}
            {v.created_at ? (
              <p className="mt-1 text-[11px] text-ink-muted">{new Date(v.created_at).toLocaleString()}</p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  )
}
