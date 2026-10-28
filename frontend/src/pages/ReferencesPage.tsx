import { useRef, useState } from 'react'
import { Upload } from 'lucide-react'
import { api, ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state'
import { useAsync } from '@/hooks/useAsync'
import { shortId } from '@/lib/utils'

export function ReferencesPage() {
  const { data, error, loading, reload } = useAsync(() => api.listReferences(), [])
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [lastNote, setLastNote] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  async function runDemo() {
    setBusy(true)
    setActionError(null)
    try {
      const res = await api.demoFixture()
      setLastNote(
        `Pipeline ok · ${res.asset.original_filename} · ${res.stems.length} stems · sim separator=${String(res.simulated?.separator)}`,
      )
      await reload()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Demo fixture failed')
    } finally {
      setBusy(false)
    }
  }

  async function onUpload(file: File) {
    setBusy(true)
    setActionError(null)
    try {
      const res = await api.uploadPipeline(file, {
        prompt: 'original groove with borrowed bass bounce',
        borrow: 'bass_bounce,drums,groove',
      })
      setLastNote(`Imported ${res.asset.original_filename} · status ${res.asset.analysis_status}`)
      await reload()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.detail : 'Upload pipeline failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-line bg-white/70 p-4 sm:p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl">References</h1>
            <p className="text-sm text-ink-muted">
              Import legally held audio → analyse → stems → borrow chips. Simulation by default.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" disabled={busy} onClick={() => void runDemo()}>
              {busy ? 'Running…' : 'Run demo fixture'}
            </Button>
            <Button disabled={busy} onClick={() => fileRef.current?.click()}>
              <Upload className="h-4 w-4" />
              Upload & pipeline
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept="audio/*,.wav,.mp3,.flac,.m4a"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void onUpload(f)
                e.target.value = ''
              }}
            />
          </div>
        </div>
        {lastNote ? <p className="mt-3 text-sm text-ok">{lastNote}</p> : null}
        {actionError ? <div className="mt-3"><ErrorState message={actionError} /></div> : null}
      </section>

      {loading ? <LoadingState label="Loading references…" /> : null}
      {error ? <ErrorState message={error} onRetry={() => void reload()} /> : null}

      {!loading && !error && (!data || data.length === 0) ? (
        <EmptyState
          title="No references yet"
          description="Upload a WAV/MP3 you own, or run the synthetic demo fixture to exercise the Phase 2 pipeline."
          action={
            <Button onClick={() => void runDemo()} disabled={busy}>
              Create demo reference
            </Button>
          }
        />
      ) : null}

      {data && data.length > 0 ? (
        <ul className="grid gap-3 sm:grid-cols-2">
          {data.map(({ asset, profile }) => (
            <li
              key={asset.id}
              className="rounded-xl border border-line bg-white/70 p-4 animate-fade-up"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="font-medium text-ink">{asset.original_filename}</h2>
                  <p className="text-xs text-ink-muted">{shortId(asset.id, 12)}</p>
                </div>
                <Badge tone={asset.analysis_status === 'pending' ? 'warn' : 'ok'}>
                  {asset.analysis_status}
                </Badge>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-ink-muted">
                <div>
                  <dt className="uppercase tracking-wider">License</dt>
                  <dd className="text-ink">{asset.license_class}</dd>
                </div>
                <div>
                  <dt className="uppercase tracking-wider">BPM / key</dt>
                  <dd className="text-ink">
                    {profile?.bpm_estimate ?? '—'} / {profile?.key_estimate ?? '—'}
                  </dd>
                </div>
              </dl>
              {profile?.available_borrow_traits?.length || asset.stem_role_mappings?.length ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {(profile?.available_borrow_traits ?? []).slice(0, 6).map((t) => (
                    <Badge key={t} tone="accent">
                      {t}
                    </Badge>
                  ))}
                  {(asset.stem_role_mappings ?? []).map((m) => (
                    <Badge key={`${m.stem_type}-${m.role}`} tone={m.locked ? 'lock' : 'neutral'}>
                      {m.stem_type}→{m.role}
                      {m.locked ? ' 🔒' : ''}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
