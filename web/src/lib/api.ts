/**
 * The only module in the frontend that talks HTTP.
 *
 * Every other file imports typed functions from here. That rule is enforced by a test in Phase 9
 * and exists so the API surface is discoverable in one place, error handling is uniform, and
 * swapping transport (say, to streaming for chat) touches one file.
 *
 * Paths are relative on purpose. In development Vite proxies `/api` to the backend port; in
 * production uvicorn serves this bundle itself. Same-origin in both, so the session cookie just
 * works and there is no base URL to configure or get wrong.
 */

export class ApiError extends Error {
  // Declared explicitly rather than as a constructor parameter property: the project builds with
  // `erasableSyntaxOnly`, which only permits TypeScript syntax that vanishes at compile time.
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    // Send and accept the httpOnly session cookie.
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...init.headers,
    },
  })

  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

/** Pull a human-readable message out of a FastAPI error body, whatever shape it took. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    // 422 from Pydantic: [{ loc: [...], msg: "...", type: "..." }]
    if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      return body.detail.map((d: { msg: string }) => d.msg).join('. ')
    }
  } catch {
    /* fall through to the generic message */
  }
  return response.status === 401 ? 'Please sign in again.' : 'Something went wrong.'
}

// ------------------------------------------------------------------------ types
export interface User {
  id: number
  email: string
  display_name: string | null
  created_at: string
}

export interface AuthResponse {
  user: User
  access_token: string
  token_type: string
}

export interface Workspace {
  id: number
  name: string
  description: string | null
  icon: string
  created_at: string
}

export interface AssistantSettings {
  assistant_name: string
  role: string
  system_prompt: string
  model: string | null
  temperature: number
  max_tokens: number
  personality: string
  response_style: string
  use_memory: boolean
  use_knowledge_base: boolean
}

export interface WorkspaceDetail extends Workspace {
  settings: AssistantSettings
}

export interface WorkspaceMeta {
  icons: string[]
  models: { id: string; label: string }[]
  personalities: string[]
  response_styles: string[]
}

// ------------------------------------------------------------------------- auth
export const auth = {
  register: (email: string, password: string, displayName?: string) =>
    request<AuthResponse>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, display_name: displayName || null }),
    }),

  login: (email: string, password: string) =>
    request<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),

  me: () => request<User>('/api/auth/me'),
}

// ------------------------------------------------------------------- workspaces
export const workspaces = {
  /** The choices the server will accept — icons, models, personalities, response styles. */
  meta: () => request<WorkspaceMeta>('/api/workspaces/meta'),

  list: () => request<Workspace[]>('/api/workspaces'),

  create: (name: string, description?: string, icon = 'folder') =>
    request<WorkspaceDetail>('/api/workspaces', {
      method: 'POST',
      body: JSON.stringify({ name, description: description || null, icon }),
    }),

  get: (id: number) => request<WorkspaceDetail>(`/api/workspaces/${id}`),

  update: (id: number, changes: Partial<Pick<Workspace, 'name' | 'description' | 'icon'>>) =>
    request<WorkspaceDetail>(`/api/workspaces/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),

  remove: (id: number) => request<void>(`/api/workspaces/${id}`, { method: 'DELETE' }),

  getSettings: (id: number) => request<AssistantSettings>(`/api/workspaces/${id}/settings`),

  /** Send only what changed; omitted fields keep their stored values. */
  updateSettings: (id: number, changes: Partial<AssistantSettings>) =>
    request<AssistantSettings>(`/api/workspaces/${id}/settings`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
}
