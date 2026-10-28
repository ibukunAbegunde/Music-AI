import { Lock, Unlock } from 'lucide-react'
import type { BriefDocument, GenreTemplate } from '@/types/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

const ROLES = ['drums', 'bass', 'chord', 'percussion', 'pad', 'lead'] as const
const BORROW_TRAITS = [
  'bass_bounce',
  'drums',
  'percussion_texture',
  'atmosphere',
  'chords',
  'arrangement',
  'groove',
  'energy',
] as const

export interface BriefCanvasProps {
  prompt: string
  onPromptChange: (v: string) => void
  brief: BriefDocument | null
  templates: GenreTemplate[]
  bars: number
  onBarsChange: (n: number) => void
  seed: string
  onSeedChange: (v: string) => void
  lockedRoles: string[]
  onToggleLock: (role: string) => void
  borrowTraits: string[]
  onToggleBorrow: (trait: string) => void
  mode: 'loop' | 'full'
  onModeChange: (m: 'loop' | 'full') => void
  scratchOrRelease: 'scratch' | 'release'
  onScratchChange: (v: 'scratch' | 'release') => void
  onParse: () => void
  parsing?: boolean
}

export function BriefCanvas({
  prompt,
  onPromptChange,
  brief,
  templates,
  bars,
  onBarsChange,
  seed,
  onSeedChange,
  lockedRoles,
  onToggleLock,
  borrowTraits,
  onToggleBorrow,
  mode,
  onModeChange,
  scratchOrRelease,
  onScratchChange,
  onParse,
  parsing,
}: BriefCanvasProps) {
  return (
    <section className="rounded-xl border border-line bg-white/70 p-4 shadow-[0_1px_0_rgba(26,36,34,0.04)] sm:p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-xl text-ink">Brief canvas</h2>
          <p className="text-sm text-ink-muted">Constraint-first source of truth — chat mutates this.</p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant={mode === 'loop' ? 'default' : 'secondary'}
            onClick={() => onModeChange('loop')}
          >
            Loop
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mode === 'full' ? 'default' : 'secondary'}
            onClick={() => onModeChange('full')}
          >
            Full-length
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">
          <label className="block text-xs font-medium uppercase tracking-wider text-ink-muted">
            Creative intent
          </label>
          <Textarea
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            placeholder='e.g. "mellow Afrobeats 110 BPM in A minor with Rhodes chords"'
            rows={4}
          />
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={onParse} disabled={parsing || !prompt.trim()}>
              {parsing ? 'Parsing…' : 'Parse → brief'}
            </Button>
            {brief ? (
              <Badge tone="accent">
                {brief.genre_template_id ?? 'default'} · {brief.bpm ?? '—'} BPM · {brief.key ?? 'key?'}
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="space-y-1 text-xs">
            <span className="uppercase tracking-wider text-ink-muted">Bars</span>
            <Input
              type="number"
              min={mode === 'full' ? 32 : 8}
              max={mode === 'full' ? 256 : 16}
              value={bars}
              onChange={(e) => onBarsChange(Number(e.target.value) || (mode === 'full' ? 64 : 8))}
            />
          </label>
          <label className="space-y-1 text-xs">
            <span className="uppercase tracking-wider text-ink-muted">Seed</span>
            <Input
              type="number"
              placeholder="auto"
              value={seed}
              onChange={(e) => onSeedChange(e.target.value)}
            />
          </label>
          <label className="col-span-2 space-y-1 text-xs">
            <span className="uppercase tracking-wider text-ink-muted">Scratch / Release</span>
            <div className="flex gap-2">
              {(['scratch', 'release'] as const).map((v) => (
                <Button
                  key={v}
                  type="button"
                  size="sm"
                  variant={scratchOrRelease === v ? 'default' : 'outline'}
                  onClick={() => onScratchChange(v)}
                  className="capitalize"
                >
                  {v}
                </Button>
              ))}
            </div>
          </label>
          <div className="col-span-2 space-y-1 text-xs">
            <span className="uppercase tracking-wider text-ink-muted">Genre templates</span>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {templates.slice(0, 6).map((t) => (
                <Badge key={t.id} tone={brief?.genre_template_id === t.id ? 'accent' : 'neutral'}>
                  {t.name}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-ink-muted">Role-locks</p>
          <div className="flex flex-wrap gap-2">
            {ROLES.map((role) => {
              const locked = lockedRoles.includes(role)
              return (
                <button
                  key={role}
                  type="button"
                  onClick={() => onToggleLock(role)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs transition-all',
                    locked
                      ? 'animate-lock-pop border-lock/40 bg-lock/10 text-lock'
                      : 'border-line bg-white/80 text-ink-muted hover:border-ink/20',
                  )}
                >
                  {locked ? <Lock className="h-3 w-3" /> : <Unlock className="h-3 w-3" />}
                  {role}
                </button>
              )
            })}
          </div>
        </div>
        <div>
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-ink-muted">Borrow chips</p>
          <div className="flex flex-wrap gap-2">
            {BORROW_TRAITS.map((trait) => {
              const on = borrowTraits.includes(trait)
              return (
                <button
                  key={trait}
                  type="button"
                  onClick={() => onToggleBorrow(trait)}
                  className={cn(
                    'rounded-md border px-2.5 py-1.5 text-xs transition-colors',
                    on
                      ? 'border-accent/40 bg-accent/10 text-accent'
                      : 'border-line bg-white/80 text-ink-muted hover:border-ink/20',
                  )}
                >
                  {trait.replaceAll('_', ' ')}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {brief ? (
        <div className="mt-4 rounded-lg border border-dashed border-line bg-paper/60 p-3 text-xs text-ink-muted">
          <span className="font-medium text-ink">Parsed brief</span>
          {' · '}
          novelty {brief.novelty.toFixed(2)} · autonomy {brief.autonomy_mode} · locks{' '}
          {brief.locked_roles.length ? brief.locked_roles.join(', ') : 'none'}
          {brief.borrow_chips.length
            ? ` · borrows ${brief.borrow_chips.map((c) => c.trait).join(', ')}`
            : ''}
        </div>
      ) : null}
    </section>
  )
}
