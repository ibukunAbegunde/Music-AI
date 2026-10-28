import { useEffect, useState } from 'react'
import { Play, RefreshCw, Sparkles, Wand2 } from 'lucide-react'
import { api, ApiError } from '@/api/client'
import { BriefCanvas } from '@/components/brief/BriefCanvas'
import { TrackLocks } from '@/components/workspace/TrackLocks'
import { VersionTimeline } from '@/components/workspace/VersionTimeline'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state'
import { Textarea } from '@/components/ui/textarea'
import { shortId } from '@/lib/utils'
import type { BriefDocument, ComposeResponse, GenreTemplate, VersionEntry } from '@/types/api'

const PROJECT_KEY = 'music-ai.activeProjectId'

export function WorkspacePage() {
  const [prompt, setPrompt] = useState('mellow Afrobeats 110 BPM in A minor with Rhodes chords')
  const [revisePrompt, setRevisePrompt] = useState('keep the drums, soften bass')
  const [brief, setBrief] = useState<BriefDocument | null>(null)
  const [templates, setTemplates] = useState<GenreTemplate[]>([])
  const [bars, setBars] = useState(8)
  const [seed, setSeed] = useState('42')
  const [lockedRoles, setLockedRoles] = useState<string[]>([])
  const [borrowTraits, setBorrowTraits] = useState<string[]>(['bass_bounce'])
  const [mode, setMode] = useState<'loop' | 'full'>('loop')
  const [scratchOrRelease, setScratchOrRelease] = useState<'scratch' | 'release'>('scratch')
  const [parsing, setParsing] = useState(false)
  const [composing, setComposing] = useState(false)
  const [revising, setRevising] = useState(false)
  const [result, setResult] = useState<ComposeResponse | null>(null)
  const [versions, setVersions] = useState<VersionEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [restoringId, setRestoringId] = useState<string | null>(null)
  const [bootLoading, setBootLoading] = useState(true)

  useEffect(() => {
    void (async () => {
      try {
        const t = await api.templates()
        setTemplates(t)
        const stored = localStorage.getItem(PROJECT_KEY)
        if (stored) {
          const { project, metadata } = await api.getProject(stored)
          const vs = await api.versions(stored)
          setVersions(vs)
          setResult({
            project,
            version: { id: project.version_id ?? '', one_line_diff: undefined },
            brief: (metadata.brief as BriefDocument) ?? {
              id: 'restored',
              title: project.name,
              free_text: project.generation_brief ?? '',
              meter: '4/4',
              energy_curve: [],
              borrow_chips: [],
              section_map: [],
              novelty: 0.4,
              length_bars: project.length_bars,
              locked_roles: project.tracks.filter((tr) => tr.locked).map((tr) => tr.role),
              scratch_or_release: 'scratch',
              autonomy_mode: 'collaborative',
            },
            candidate: (metadata.candidate as ComposeResponse['candidate']) ?? null,
            midi_paths: {},
            next_moves: (metadata.next_moves as ComposeResponse['next_moves']) ?? [],
            daw: (metadata.daw as Record<string, unknown>) ?? null,
          })
          setBrief((metadata.brief as BriefDocument) ?? null)
        }
      } catch {
        /* empty workspace is fine */
      } finally {
        setBootLoading(false)
      }
    })()
  }, [])

  async function refreshVersions(projectId: string) {
    const vs = await api.versions(projectId)
    setVersions(vs)
  }

  async function handleParse() {
    setParsing(true)
    setError(null)
    try {
      const parsed = await api.parseBrief({
        prompt,
        seed: seed ? Number(seed) : null,
        bars,
        locked_roles: lockedRoles,
        scratch_or_release: scratchOrRelease,
      })
      setBrief(parsed)
      if (parsed.length_bars) setBars(parsed.length_bars)
      if (parsed.locked_roles?.length) setLockedRoles(parsed.locked_roles)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Parse failed')
    } finally {
      setParsing(false)
    }
  }

  async function handleCompose() {
    setComposing(true)
    setError(null)
    try {
      const composed = await api.compose({
        prompt,
        seed: seed ? Number(seed) : null,
        bars: mode === 'full' ? Math.max(bars, 16) : bars,
        locked_roles: lockedRoles,
        mode,
        scratch_or_release: scratchOrRelease,
        autonomy_mode: 'collaborative',
      })
      setResult(composed)
      setBrief(composed.brief)
      localStorage.setItem(PROJECT_KEY, composed.project.id)
      await refreshVersions(composed.project.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Compose failed')
    } finally {
      setComposing(false)
    }
  }

  async function handleRevise() {
    if (!result?.project.id) return
    setRevising(true)
    setError(null)
    try {
      const revised = await api.revise(result.project.id, {
        prompt: revisePrompt,
        seed: seed ? Number(seed) + 1 : null,
        locked_roles: lockedRoles,
      })
      setResult(revised)
      localStorage.setItem(PROJECT_KEY, revised.project.id)
      await refreshVersions(revised.project.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Revise failed')
    } finally {
      setRevising(false)
    }
  }

  async function handleRestore(versionId: string) {
    if (!result?.project.id) return
    setRestoringId(versionId)
    setError(null)
    try {
      await api.restore(result.project.id, versionId)
      const { project, metadata } = await api.getProject(result.project.id)
      setResult((prev) =>
        prev
          ? {
              ...prev,
              project,
              version: { id: project.version_id ?? versionId, one_line_diff: 'Restored' },
              candidate: (metadata.candidate as ComposeResponse['candidate']) ?? prev.candidate,
              next_moves: (metadata.next_moves as ComposeResponse['next_moves']) ?? [],
            }
          : prev,
      )
      await refreshVersions(result.project.id)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Restore failed')
    } finally {
      setRestoringId(null)
    }
  }

  function toggleLock(role: string) {
    setLockedRoles((prev) => (prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]))
  }

  function toggleBorrow(trait: string) {
    setBorrowTraits((prev) => (prev.includes(trait) ? prev.filter((t) => t !== trait) : [...prev, trait]))
  }

  if (bootLoading) return <LoadingState label="Loading workspace…" />

  return (
    <div className="space-y-6">
      <BriefCanvas
        prompt={prompt}
        onPromptChange={setPrompt}
        brief={brief}
        templates={templates}
        bars={bars}
        onBarsChange={setBars}
        seed={seed}
        onSeedChange={setSeed}
        lockedRoles={lockedRoles}
        onToggleLock={toggleLock}
        borrowTraits={borrowTraits}
        onToggleBorrow={toggleBorrow}
        mode={mode}
        onModeChange={(m) => {
          setMode(m)
          setBars((b) => (m === 'full' ? Math.max(b, 32) : Math.min(b, 16)))
        }}
        scratchOrRelease={scratchOrRelease}
        onScratchChange={setScratchOrRelease}
        onParse={() => void handleParse()}
        parsing={parsing}
      />

      <div className="flex flex-wrap gap-2">
        <Button
          className={composing ? 'animate-pulse-soft' : ''}
          onClick={() => void handleCompose()}
          disabled={composing || !prompt.trim()}
        >
          <Sparkles className="h-4 w-4" />
          {composing ? 'Composing…' : mode === 'full' ? 'Full compose' : 'Compose loop'}
        </Button>
        <Button
          variant="secondary"
          onClick={() => void handleParse()}
          disabled={parsing || !prompt.trim()}
        >
          <Wand2 className="h-4 w-4" />
          Refresh brief
        </Button>
      </div>

      {error ? <ErrorState message={error} onRetry={() => setError(null)} /> : null}

      {!result ? (
        <EmptyState
          title="No project yet"
          description="Fill the brief canvas and compose an 8–16 bar loop (or full-length arrangement). Simulation MIDI exports land in workspace/."
          action={
            <Button onClick={() => void handleCompose()} disabled={composing}>
              Generate first idea
            </Button>
          }
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-xl border border-line bg-white/70 p-4 sm:p-5">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="font-display text-xl">{result.project.name}</h2>
                <p className="text-sm text-ink-muted">
                  {result.project.bpm} BPM · {result.project.key_estimate ?? '—'} ·{' '}
                  {result.project.length_bars} bars · seed {result.project.seed ?? '—'}
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <Badge tone="accent">{shortId(result.project.id)}</Badge>
                <Badge>{result.project.status}</Badge>
                {result.candidate?.loudness_notes.normalization_status ? (
                  <Badge tone="warn">{result.candidate.loudness_notes.normalization_status}</Badge>
                ) : null}
              </div>
            </div>

            {result.candidate ? (
              <div className="mb-4 rounded-lg border border-line bg-paper/70 p-3">
                <p className="text-xs uppercase tracking-wider text-ink-muted">Candidate package</p>
                <p className="mt-1 text-sm text-ink">{result.candidate.one_line_diff || 'Baseline package'}</p>
                <p className="mt-1 text-xs text-ink-muted">
                  seed {result.candidate.seed ?? '—'} · CIR {result.candidate.cir_snapshot_ref ?? '—'} ·
                  target {result.candidate.loudness_notes.target_lufs ?? -14} LUFS
                </p>
              </div>
            ) : null}

            <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-ink-muted">Tracks / locks</h3>
            <TrackLocks tracks={result.project.tracks} />

            {result.next_moves?.length ? (
              <div className="mt-4">
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-ink-muted">
                  Next moves (≤3 typed PatchOps)
                </h3>
                <ul className="space-y-2">
                  {result.next_moves.slice(0, 3).map((op, i) => (
                    <li key={`${op.action_type}-${i}`} className="rounded-md border border-line bg-white/80 px-3 py-2 text-sm">
                      <span className="font-medium text-accent">{op.action_type}</span>
                      {op.target_role ? ` → ${op.target_role}` : ''}
                      <span className="block text-xs text-ink-muted">
                        {op.predicted_impact || op.explanation || '—'}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {result.arrangement?.manual_steps?.length ? (
              <div className="mt-4 rounded-lg border border-dashed border-line p-3 text-xs text-ink-muted">
                <p className="font-medium text-ink">Manual FL steps (no live DAW)</p>
                <ol className="mt-1 list-decimal space-y-1 pl-4">
                  {result.arrangement.manual_steps.slice(0, 6).map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ol>
              </div>
            ) : null}

            <div className="mt-5 space-y-2 border-t border-line pt-4">
              <label className="text-xs font-medium uppercase tracking-wider text-ink-muted">
                Revise (role-locks honored)
              </label>
              <Textarea
                value={revisePrompt}
                onChange={(e) => setRevisePrompt(e.target.value)}
                rows={2}
              />
              <Button variant="secondary" onClick={() => void handleRevise()} disabled={revising}>
                <RefreshCw className={`h-4 w-4 ${revising ? 'animate-spin' : ''}`} />
                {revising ? 'Revising…' : 'Apply revise'}
              </Button>
              {result.diff ? (
                <p className="text-sm text-ink">
                  Diff: {result.diff.one_line_summary}
                  <span className="text-ink-muted">
                    {' '}
                    · changed {result.diff.roles_changed.join(', ') || 'none'}
                  </span>
                </p>
              ) : null}
            </div>
          </section>

          <section className="rounded-xl border border-line bg-white/70 p-4 sm:p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-display text-xl">Versions</h2>
              <Badge tone="neutral">
                <Play className="mr-1 inline h-3 w-3" />
                MIDI proxy
              </Badge>
            </div>
            <VersionTimeline
              versions={versions}
              onRestore={(id) => void handleRestore(id)}
              restoringId={restoringId}
            />
          </section>
        </div>
      )}
    </div>
  )
}
