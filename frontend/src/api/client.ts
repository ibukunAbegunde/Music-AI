import type {
  AbCompareResponse,
  BriefDocument,
  ComposeResponse,
  GenreTemplate,
  HealthInfo,
  JobRecord,
  MusicProject,
  ReferenceListItem,
  SettingsInfo,
  VersionEntry,
} from '@/types/api'

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail != null) detail = JSON.stringify(body.detail)
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  health: () => request<HealthInfo>('/api/health'),
  settings: () => request<SettingsInfo>('/api/settings'),
  doctor: () => request<Record<string, unknown>>('/api/doctor'),
  templates: () => request<GenreTemplate[]>('/api/templates'),

  parseBrief: (body: {
    prompt: string
    seed?: number | null
    bars?: number
    locked_roles?: string[]
    scratch_or_release?: string
  }) =>
    request<BriefDocument>('/api/brief/parse', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  listProjects: () => request<MusicProject[]>('/api/projects'),
  getProject: (id: string) =>
    request<{ project: MusicProject; metadata: Record<string, unknown> }>(`/api/projects/${id}`),

  compose: (body: Record<string, unknown>) =>
    request<ComposeResponse>('/api/compose', { method: 'POST', body: JSON.stringify(body) }),

  revise: (projectId: string, body: Record<string, unknown>) =>
    request<ComposeResponse>(`/api/projects/${projectId}/revise`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  refCompose: (body: Record<string, unknown>) =>
    request<{
      job_id: string
      project_id: string
      candidates: {
        index: number
        seed: number
        version_id: string
        one_line_diff: string
        candidate: ComposeResponse['candidate']
        midi_paths: Record<string, string>
      }[]
      traits: string[]
      brief: BriefDocument
      phase2_note: string
    }>('/api/ref-compose', { method: 'POST', body: JSON.stringify(body) }),

  versions: (projectId: string) => request<VersionEntry[]>(`/api/projects/${projectId}/versions`),
  restore: (projectId: string, versionId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/restore`, {
      method: 'POST',
      body: JSON.stringify({ version_id: versionId }),
    }),

  candidates: (projectId: string) =>
    request<{
      project_id: string
      candidates: Record<string, unknown>[]
      session: Record<string, unknown> | null
    }>(`/api/projects/${projectId}/candidates`),

  ab: (projectId: string, body: Record<string, unknown>) =>
    request<AbCompareResponse>(`/api/projects/${projectId}/ab`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  listReferences: () => request<ReferenceListItem[]>('/api/references'),
  demoFixture: () =>
    request<{
      job_id: string
      asset: ReferenceListItem['asset']
      profile: ReferenceListItem['profile']
      stems: unknown[]
      brief_with_borrows: BriefDocument | null
      simulated: Record<string, boolean>
    }>('/api/references/demo-fixture', { method: 'POST' }),

  uploadPipeline: async (file: File, opts?: { prompt?: string; borrow?: string }) => {
    const form = new FormData()
    form.append('file', file)
    form.append('license_class', 'owned')
    form.append('use_mode', 'analysis')
    if (opts?.borrow) form.append('borrow', opts.borrow)
    if (opts?.prompt) form.append('prompt', opts.prompt)
    return request<{
      job_id: string
      asset: ReferenceListItem['asset']
      profile: ReferenceListItem['profile']
      stems: unknown[]
      brief_with_borrows: BriefDocument | null
    }>('/api/references/pipeline', { method: 'POST', body: form })
  },

  listJobs: () => request<JobRecord[]>('/api/jobs'),
  getJob: (id: string) => request<JobRecord>(`/api/jobs/${id}`),
}
