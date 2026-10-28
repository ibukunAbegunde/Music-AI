export type AutonomyMode = 'suggest-only' | 'collaborative' | 'autonomous'
export type ScratchOrRelease = 'scratch' | 'release'

export interface BriefDocument {
  id: string
  project_id?: string | null
  title: string
  free_text: string
  bpm?: number | null
  key?: string | null
  meter: string
  genre_template_id?: string | null
  energy_curve: { bar: number; value: number }[]
  borrow_chips: { reference_id?: string | null; trait: string; weight: number }[]
  section_map: { name: string; start_bar: number; end_bar: number; intensity_target: number }[]
  novelty: number
  length_bars: number
  locked_roles: string[]
  recipe_id?: string | null
  scratch_or_release: ScratchOrRelease
  autonomy_mode: AutonomyMode
  seed?: number | null
}

export interface MusicTrack {
  id: string
  role: string
  locked: boolean
  note_events: unknown[]
  drum_events: unknown[]
  enabled: boolean
}

export interface MusicProject {
  id: string
  name: string
  bpm: number
  key_estimate?: string | null
  length_bars: number
  status: string
  seed?: number | null
  genre_template_id?: string | null
  version_id?: string | null
  generation_brief?: string | null
  tracks: MusicTrack[]
  sections: { name: string; start_bar: number; end_bar: number; intensity_target: number }[]
  autonomy_policy?: { mode: string; scratch_or_release: string }
}

export interface CandidatePackage {
  id: string
  project_id: string
  version_id: string
  seed?: number | null
  cir_snapshot_ref?: string | null
  midi_paths: string[]
  loudness_notes: {
    target_lufs?: number | null
    measured_lufs?: number | null
    normalization_status?: string | null
  }
  one_line_diff: string
  parent_version_id?: string | null
}

export interface DawOperation {
  action_type: string
  target_role?: string | null
  predicted_impact?: string | null
  explanation?: string | null
  risk_level?: string | null
}

export interface ComposeResponse {
  project: MusicProject
  version: { id: string; one_line_diff?: string | null }
  brief: BriefDocument
  candidate: CandidatePackage | null
  midi_paths: Record<string, string>
  next_moves: DawOperation[]
  daw: Record<string, unknown> | null
  job_id?: string
  arrangement?: {
    plan: Record<string, unknown>
    manual_steps: string[]
    gated: boolean
  }
  diff?: MusicalDiff
  undo_available?: boolean
}

export interface MusicalDiff {
  one_line_summary: string
  roles_changed: string[]
  density_delta?: number | null
  locked_roles_respected?: boolean
  note_count_delta_by_role?: Record<string, number>
}

export interface VersionEntry {
  version_id: string
  parent_version_id?: string | null
  created_at?: string | null
  one_line_diff?: string | null
  seed?: number | null
  restorable: boolean
  musical_diff?: MusicalDiff | null
}

export interface CandidateSide {
  label: string
  version_id: string
  candidate_id?: string | null
  seed?: number | null
  midi_proxy_path?: string | null
  loudness_notes: CandidatePackage['loudness_notes']
  one_line_diff: string
}

export interface AbCompareResponse {
  comparison_id: string
  project_id: string
  path_mode: string
  side_a: CandidateSide
  side_b: CandidateSide
  musical_diff: MusicalDiff
  preference?: { user_choice: string; optional_reason?: string | null } | null
  session_path: string
}

export interface JobRecord {
  id: string
  project_id?: string | null
  kind: string
  status: string
  detail: Record<string, unknown>
  created_at?: string | null
  updated_at?: string | null
}

export interface GenreTemplate {
  id: string
  name: string
  default_bpm: number
  bpm_range: [number, number]
  notes?: string | null
}

export interface ReferenceListItem {
  asset: {
    id: string
    original_filename: string
    license_class: string
    analysis_status: string
    duration_sec?: number | null
    stem_role_mappings?: { stem_type: string; role: string; locked: boolean }[]
  }
  profile?: {
    bpm_estimate?: number | null
    key_estimate?: string | null
    available_borrow_traits?: string[]
    genre_hypotheses?: string[]
  } | null
}

export interface SettingsInfo {
  daw_mode: string
  workspace_dir: string
  llm_provider: string
  allow_cloud_audio: boolean
  allow_cloud_llm: boolean
  music_ai_separator: string
  music_ai_transcriber: string
  taste_encoder: string
  autonomy_default: string
  schema_version: string
}

export interface HealthInfo {
  status: string
  schema_version: string
  daw_mode: string
  workspace: string
}
