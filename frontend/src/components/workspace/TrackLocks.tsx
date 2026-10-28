import { Lock, Unlock } from 'lucide-react'
import type { MusicTrack } from '@/types/api'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export function TrackLocks({ tracks }: { tracks: MusicTrack[] }) {
  if (!tracks.length) {
    return <p className="text-sm text-ink-muted">No tracks yet.</p>
  }
  return (
    <ul className="space-y-2">
      {tracks.map((t) => (
        <li
          key={t.id}
          className={cn(
            'flex items-center justify-between rounded-md border border-line bg-white/70 px-3 py-2',
            t.locked && 'border-lock/30 bg-lock/5',
          )}
        >
          <div className="flex items-center gap-2">
            {t.locked ? (
              <Lock className="h-3.5 w-3.5 text-lock animate-lock-pop" />
            ) : (
              <Unlock className="h-3.5 w-3.5 text-ink-muted" />
            )}
            <span className="text-sm font-medium capitalize">{t.role}</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            <span>{t.note_events?.length ?? 0} notes</span>
            {t.locked ? <Badge tone="lock">locked</Badge> : null}
          </div>
        </li>
      ))}
    </ul>
  )
}
