import { useEffect, useState } from 'react'
import { api, ApiError } from '@/api/client'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state'
import { Input } from '@/components/ui/input'
import { shortId } from '@/lib/utils'
import type { AbCompareResponse } from '@/types/api'

const PROJECT_KEY = 'music-ai.activeProjectId'
const TRAITS = ['bass_bounce', 'percussion_texture', 'groove', 'drums', 'chords']

export function CandidatesPage() {
  const [prompt, setPrompt] = useState('original mellow Afrobeats with bass bounce')
  const [traits, setTraits] = useState<string[]>(['bass_bounce', 'percussion_texture'])
  const [projectId, setProjectId] = useState(() => localStorage.getItem(PROJECT_KEY) ?? '')
  const [candidates, setCandidates] = useState<
    { index: number; seed: number; version_id: string; one_line_diff: string }[]
  >([])
  const [ab, setAb] = useState<AbCompareResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [choosing, setChoosing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadingSession, setLoadingSession] = useState(false)

  useEffect(() => {
    if (!projectId) return
    setLoadingSession(true)
    void api
      .candidates(projectId)
      .then((res) => {
        const list = (res.candidates ?? []).map((c, i) => ({
          index: typeof c.index === 'number' ? c.index : i,
          seed: typeof c.seed === 'number' ? c.seed : 0,
          version_id: String(c.version_id ?? ''),
          one_line_diff: String(c.one_line_diff ?? ''),
        }))
        setCandidates(list.filter((c) => c.version_id))
      })
      .catch(() => setCandidates([]))
      .finally(() => setLoadingSession(false))
  }, [projectId])

  async function generate() {
    setBusy(true)
    setError(null)
    setAb(null)
    try {
      const res = await api.refCompose({
        prompt,
        traits,
        n: 2,
        seed: 42,
        bars: 8,
      })
      setProjectId(res.project_id)
      localStorage.setItem(PROJECT_KEY, res.project_id)
      setCandidates(
        res.candidates.map((c) => ({
          index: c.index,
          seed: c.seed,
          version_id: c.version_id,
          one_line_diff: c.one_line_diff,
        })),
      )
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'ref-compose failed')
    } finally {
      setBusy(false)
    }
  }

  async function compare(choice?: 'a' | 'b' | 'tie' | 'skip') {
    if (!projectId) return
    setChoosing(true)
    setError(null)
    try {
      const res = await api.ab(projectId, {
        index_a: 0,
        index_b: 1,
        choice: choice ?? null,
        reason: choice ? `UI preference: ${choice}` : null,
      })
      setAb(res)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'A/B failed')
    } finally {
      setChoosing(false)
    }
  }

  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-line bg-white/70 p-4 sm:p-5">
        <h1 className="font-display text-2xl">A/B · candidates</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Multi-seed CandidatePackages with musical diff. Audio uses MIDI proxies until bounce WAVs exist.
        </p>
        <div className="mt-4 space-y-3">
          <Input value={prompt} onChange={(e) => setPrompt(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            {TRAITS.map((t) => {
              const on = traits.includes(t)
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() =>
                    setTraits((prev) => (on ? prev.filter((x) => x !== t) : [...prev, t]))
                  }
                  className={`rounded-md border px-2.5 py-1 text-xs ${
                    on ? 'border-accent/40 bg-accent/10 text-accent' : 'border-line text-ink-muted'
                  }`}
                >
                  {t.replaceAll('_', ' ')}
                </button>
              )
            })}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void generate()} disabled={busy || !prompt.trim()}>
              {busy ? 'Generating…' : 'Generate 2 candidates'}
            </Button>
            <Button
              variant="secondary"
              disabled={!projectId || candidates.length < 2 || choosing}
              onClick={() => void compare()}
            >
              {choosing ? 'Comparing…' : 'Compare A/B'}
            </Button>
          </div>
          {projectId ? (
            <p className="text-xs text-ink-muted">
              Active project <code>{shortId(projectId, 12)}</code>
            </p>
          ) : null}
        </div>
      </section>

      {error ? <ErrorState message={error} /> : null}
      {loadingSession ? <LoadingState label="Loading candidate session…" /> : null}

      {!busy && !loadingSession && candidates.length === 0 ? (
        <EmptyState
          title="No candidates"
          description="Generate a reference-conditioned pair, or open a project that already has a candidate_session_*.json."
        />
      ) : null}

      {candidates.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {candidates.map((c, i) => (
            <article key={c.version_id} className="rounded-xl border border-line bg-white/70 p-4 animate-fade-up">
              <div className="flex items-center justify-between">
                <h2 className="font-display text-lg">Candidate {String.fromCharCode(65 + i)}</h2>
                <Badge>seed {c.seed}</Badge>
              </div>
              <p className="mt-2 text-sm text-ink">{c.one_line_diff || '—'}</p>
              <p className="mt-1 text-xs text-ink-muted">version {shortId(c.version_id)}</p>
            </article>
          ))}
        </div>
      ) : null}

      {ab ? (
        <section className="rounded-xl border border-line bg-white/70 p-4 sm:p-5 animate-fade-up">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h2 className="font-display text-xl">Musical diff</h2>
            <Badge tone="warn">{ab.path_mode}</Badge>
          </div>
          <p className="text-sm text-ink">{ab.musical_diff.one_line_summary}</p>
          <p className="mt-1 text-xs text-ink-muted">
            roles changed: {ab.musical_diff.roles_changed.join(', ') || 'none'} · locks{' '}
            {ab.musical_diff.locked_roles_respected == null
              ? 'n/a'
              : ab.musical_diff.locked_roles_respected
                ? 'honored'
                : 'broken'}
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {[ab.side_a, ab.side_b].map((side) => (
              <div key={side.label} className="rounded-lg border border-line bg-paper/60 p-3">
                <p className="font-medium">Side {side.label}</p>
                <p className="text-xs text-ink-muted">
                  seed {side.seed ?? '—'} · {side.loudness_notes.normalization_status} · target{' '}
                  {side.loudness_notes.target_lufs ?? -14} LUFS
                </p>
                <p className="mt-1 text-sm">{side.one_line_diff || '—'}</p>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {(['a', 'b', 'tie', 'skip'] as const).map((c) => (
              <Button key={c} size="sm" variant="outline" disabled={choosing} onClick={() => void compare(c)}>
                Prefer {c.toUpperCase()}
              </Button>
            ))}
          </div>
          {ab.preference ? (
            <p className="mt-3 text-sm text-ok">Recorded choice: {ab.preference.user_choice}</p>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
