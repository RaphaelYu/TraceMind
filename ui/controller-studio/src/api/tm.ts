const DEFAULT_BASE_URL = import.meta.env.VITE_TM_SERVER_URL ?? 'http://localhost:8600'
export const tmServerUrl = DEFAULT_BASE_URL

type QueryParam = string | number | boolean
type QueryParams = Record<string, QueryParam | undefined | null>

const buildUrl = (path: string, params?: QueryParams): string => {
  const url = new URL(path, DEFAULT_BASE_URL)
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value))
      }
    })
  }
  return url.toString()
}

const tmFetch = async <T>(
  path: string,
  options: RequestInit = {},
  params?: QueryParams
): Promise<T> => {
  const url = buildUrl(path, params)
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  const request: RequestInit = {
    ...options,
    headers,
  }
  if (request.body && !headers.has('Content-Type') && typeof request.body === 'string') {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(url, request)
  if (!response.ok) {
    const payload = await response.text()
    const message = payload || response.statusText
    throw new Error(`${response.status} ${message}`)
  }
  return response.json()
}

export interface WorkspaceInfo {
  workspace_id: string
  name: string
  root: string
  languages: string[]
  directories: Record<string, string>
  commit_policy: {
    required: string[]
    optional: string[]
  }
}

export interface BundleEntry {
  artifact_id: string
  artifact_type: string
  body_hash: string
  path: string
  meta: Record<string, unknown>
  version: string
  created_at: string
  status: string
  intent_id: string | null
}

export interface CycleRunResponse {
  run_id: string
  report_path: string
  success: boolean
  errors: string[]
  gap_map: string | null
  backlog: string | null
  report: Record<string, unknown>
  workspace_id: string | null
  llm_config_id: string | null
  llm_config: Record<string, unknown> | null
}

export interface RunStatus {
  run_id: string
  workspace_id: string | null
  bundle_artifact_id: string | null
  status: string
  current_step: string | null
  attempt: number
  retry_count: number
  timeout_step: string | null
  timeout_seconds: number | null
  timeout_reason: string | null
  canceled: boolean
  started_at: string
  ended_at: string | null
  errors: string[]
  last_error: string | null
}

export interface PromptTemplateInfo {
  version: string
  title: string
  description?: string | null
}

export interface LlmConfigInfo {
  config_id: string
  model: string
  prompt_template_version: string
  prompt_version: string
  created_at: string
  model_id: string | null
  model_version: string | null
}

export interface ArtifactDocument {
  envelope: Record<string, unknown>
  body: Record<string, unknown>
}

export interface ArtifactEntry {
  artifact_id: string
  artifact_type: string
  body_hash: string
  path: string
  meta: Record<string, unknown>
  version: string
  created_at: string
  status: string
  intent_id: string | null
}

export interface ArtifactDetail {
  entry: ArtifactEntry
  document: ArtifactDocument
}

export interface ArtifactCreatePayload {
  artifact_type: string
  body: Record<string, unknown>
}

export interface ArtifactDocumentResponse {
  entry: BundleEntry
  document: ArtifactDocument
}

export interface ArtifactDiffItem {
  path: string
  kind: string
  base: unknown
  compare: unknown
}

export interface ArtifactDiffResponse {
  base_id: string
  compare_id: string
  diff: ArtifactDiffItem[]
}

export interface ReportSummary {
  run_id: string
  report: Record<string, unknown>
  report_path: string
  gap_map: string | null
  backlog: string | null
}

export const listWorkspaces = () => tmFetch<WorkspaceInfo[]>('/api/v1/workspaces')
export const getCurrentWorkspace = () => tmFetch<WorkspaceInfo | null>('/api/v1/workspaces/current')
export const mountWorkspace = (path: string) =>
  tmFetch<WorkspaceInfo>('/api/v1/workspaces/mount', {
    method: 'POST',
    body: JSON.stringify({ path }),
  })
export const selectWorkspace = (workspace_id: string) =>
  tmFetch<WorkspaceInfo>('/api/v1/workspaces/select', {
    method: 'POST',
    body: JSON.stringify({ workspace_id }),
  })

export const listBundles = (workspace_id?: string) =>
  tmFetch<BundleEntry[]>('/api/controller/bundles', {}, workspace_id ? { workspace_id } : undefined)

export const runCycle = (payload: {
  bundle_artifact_id: string
  mode?: 'live' | 'dry'
  dry_run?: boolean
  run_id?: string
  workspace_id?: string
  approval_token?: string
  llm_config_id?: string
}) => tmFetch<CycleRunResponse>('/api/controller/cycle', {
  method: 'POST',
  body: JSON.stringify({
    bundle_artifact_id: payload.bundle_artifact_id,
    mode: payload.mode ?? 'live',
    dry_run: payload.dry_run ?? false,
    run_id: payload.run_id,
    workspace_id: payload.workspace_id,
    approval_token: payload.approval_token,
    llm_config_id: payload.llm_config_id,
  }),
})

export const listReports = (workspace_id?: string) =>
  tmFetch<ReportSummary[]>('/api/controller/reports', {}, workspace_id ? { workspace_id } : undefined)

export const getArtifactDocument = (artifact_id: string, workspace_id?: string) =>
  tmFetch<ArtifactDocumentResponse>(
    `/api/controller/artifacts/${encodeURIComponent(artifact_id)}`,
    {},
    workspace_id ? { workspace_id } : undefined
  )

export const diffArtifacts = (params: {
  base_id: string
  compare_id: string
  workspace_id?: string
}) =>
  tmFetch<ArtifactDiffResponse>(
    '/api/controller/artifacts/diff',
    {
      method: 'POST',
      body: JSON.stringify({
        base_id: params.base_id,
        compare_id: params.compare_id,
      }),
    },
    params.workspace_id ? { workspace_id: params.workspace_id } : undefined
  )

export const getReports = listReports

export const listArtifacts = (params: {
  artifact_type: string
  workspace_id?: string
}) =>
  tmFetch<ArtifactEntry[]>(
    '/api/v1/artifacts',
    {},
    {
      artifact_type: params.artifact_type,
      workspace_id: params.workspace_id,
    },
  )

export const getArtifactDetail = (artifact_id: string, workspace_id?: string) =>
  tmFetch<ArtifactDetail>(
    `/api/v1/artifacts/${encodeURIComponent(artifact_id)}`,
    {},
    workspace_id ? { workspace_id } : undefined,
  )

export const createArtifact = (payload: ArtifactCreatePayload, workspace_id?: string) =>
  tmFetch<ArtifactDetail>(
    '/api/v1/artifacts',
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
    workspace_id ? { workspace_id } : undefined,
  )

export const updateArtifact = (artifact_id: string, payload: ArtifactCreatePayload, workspace_id?: string) =>
  tmFetch<ArtifactDetail>(
    `/api/v1/artifacts/${encodeURIComponent(artifact_id)}`,
    {
      method: 'PUT',
      body: JSON.stringify(payload),
    },
    workspace_id ? { workspace_id } : undefined,
  )

export const listPromptTemplates = (workspace_id?: string) =>
  tmFetch<PromptTemplateInfo[]>('/api/v1/llm/prompt-templates', {}, workspace_id ? { workspace_id } : undefined)

export const listLlmConfigs = (workspace_id?: string) =>
  tmFetch<LlmConfigInfo[]>('/api/v1/llm/configs', {}, workspace_id ? { workspace_id } : undefined)

export const createLlmConfig = (
  payload: {
    model: string
    prompt_template_version: string
    prompt_version?: string
    model_id?: string
    model_version?: string
  },
  workspace_id?: string,
) =>
  tmFetch<LlmConfigInfo>(
    '/api/v1/llm/configs',
    {
      method: 'POST',
      body: JSON.stringify({
        model: payload.model,
        prompt_template_version: payload.prompt_template_version,
        prompt_version: payload.prompt_version?.trim()
          ? payload.prompt_version.trim()
          : undefined,
        model_id: payload.model_id?.trim() ? payload.model_id.trim() : undefined,
        model_version: payload.model_version?.trim() ? payload.model_version.trim() : undefined,
      }),
    },
    workspace_id ? { workspace_id } : undefined,
  )

export const getRunStatus = (run_id: string, workspace_id?: string) =>
  tmFetch<RunStatus>(
    `/api/v1/runs/${encodeURIComponent(run_id)}`,
    {},
    workspace_id ? { workspace_id } : undefined,
  )

export const cancelRun = (run_id: string, workspace_id?: string) =>
  tmFetch<RunStatus>(
    `/api/v1/runs/${encodeURIComponent(run_id)}/cancel`,
    { method: 'POST' },
    workspace_id ? { workspace_id } : undefined,
  )
