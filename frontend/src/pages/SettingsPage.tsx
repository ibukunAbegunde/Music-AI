import { api } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ErrorState, LoadingState } from '@/components/ui/state'
import { useAsync } from '@/hooks/useAsync'

export function SettingsPage() {
  const settings = useAsync(() => api.settings(), [])
  const health = useAsync(() => api.health(), [])
  const doctor = useAsync(() => api.doctor(), [])

  const loading = settings.loading || health.loading
  const error = settings.error || health.error

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-2xl">Settings</h1>
        <p className="text-sm text-ink-muted">
          Read-only view of local env. Edit <code>.env</code> and restart the API to change values.
        </p>
      </div>

      {loading ? <LoadingState /> : null}
      {error ? (
        <ErrorState
          message={error}
          onRetry={() => {
            void settings.reload()
            void health.reload()
          }}
        />
      ) : null}

      {settings.data && health.data ? (
        <section className="grid gap-3 sm:grid-cols-2 animate-fade-up">
          {[
            ['API status', health.data.status],
            ['Schema', settings.data.schema_version],
            ['DAW mode', settings.data.daw_mode],
            ['Workspace', settings.data.workspace_dir],
            ['LLM provider', settings.data.llm_provider],
            ['Autonomy default', settings.data.autonomy_default],
            ['Separator', settings.data.music_ai_separator],
            ['Transcriber', settings.data.music_ai_transcriber],
            ['Taste encoder', settings.data.taste_encoder],
            ['Cloud audio', String(settings.data.allow_cloud_audio)],
            ['Cloud LLM', String(settings.data.allow_cloud_llm)],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-line bg-white/70 p-4">
              <p className="text-[11px] uppercase tracking-wider text-ink-muted">{label}</p>
              <p className="mt-1 break-all text-sm font-medium text-ink">{value}</p>
            </div>
          ))}
        </section>
      ) : null}

      <section className="rounded-xl border border-line bg-white/70 p-4 sm:p-5">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="font-display text-xl">Doctor</h2>
          <Button size="sm" variant="secondary" onClick={() => void doctor.reload()}>
            Re-run
          </Button>
        </div>
        {doctor.loading ? <LoadingState label="Probing environment…" /> : null}
        {doctor.error ? <ErrorState message={doctor.error} /> : null}
        {doctor.data ? (
          <div className="space-y-2 text-sm">
            <div className="flex flex-wrap gap-2">
              <Badge tone="accent">os {(doctor.data.os as { system?: string })?.system ?? '?'}</Badge>
              <Badge>
                python{' '}
                {String((doctor.data.python as { ok?: boolean })?.ok ? 'ok' : 'check version')}
              </Badge>
              <Badge tone="warn">PostFader / FL not required for this UI</Badge>
            </div>
            <pre className="max-h-64 overflow-auto rounded-md bg-ink/[0.04] p-3 text-[11px] leading-relaxed text-ink-muted">
              {JSON.stringify(doctor.data, null, 2)}
            </pre>
          </div>
        ) : null}
      </section>
    </div>
  )
}
