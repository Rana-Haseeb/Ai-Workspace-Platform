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

export interface Citation {
  chunk_id: number
  document_id: number
  filename: string
  page: number | null
  snippet: string
  score: number
}

export interface DocumentRow {
  id: number
  filename: string
  mime_type: string
  size_bytes: number
  page_count: number
  chunk_count: number
  status: 'pending' | 'processing' | 'ready' | 'failed'
  error: string | null
  created_at: string
}

export interface KnowledgeBaseStatus {
  documents: number
  chunks: number
  embedded_chunks: number
  embedding_backend: string
  retrieval_mode: string
  semantic_search_available: boolean
}

export interface DocumentChunk {
  id: number
  ordinal: number
  text: string
  page: number | null
}

export interface Message {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  citations: Citation[]
  memory_used: unknown[]
  is_pinned: boolean
  model: string | null
  tokens_in: number
  tokens_out: number
  cost_usd: number
  latency_ms: number
  created_at: string
}

export interface Conversation {
  id: number
  title: string
  session_id: string
  is_pinned: boolean
  tags: string[]
  created_at: string
  updated_at: string
  message_count: number
  preview: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

/** One line of the NDJSON chat stream. */
export type StreamEvent =
  | {
      type: 'start'
      conversation_id: number
      user_message_id: number
      citations: Citation[]
      retrieval_mode: string
    }
  | { type: 'token'; text: string }
  | { type: 'done'; message_id: number; title: string; model: string | null; latency_ms: number; tokens_out: number }
  | { type: 'error'; detail: string }

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

// -------------------------------------------------------------------- documents
export const documents = {
  list: (workspaceId: number) =>
    request<DocumentRow[]>(`/api/workspaces/${workspaceId}/documents`),

  status: (workspaceId: number) =>
    request<KnowledgeBaseStatus>(`/api/workspaces/${workspaceId}/documents/status`),

  /**
   * Upload one file.
   *
   * No `Content-Type` header on purpose: the browser must set it itself so it can add the
   * multipart boundary. Setting it by hand produces a body the server cannot parse.
   */
  async upload(workspaceId: number, file: File): Promise<DocumentRow> {
    const form = new FormData()
    form.append('file', file)
    const response = await fetch(`/api/workspaces/${workspaceId}/documents`, {
      method: 'POST',
      credentials: 'include',
      body: form,
    })
    if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
    return response.json() as Promise<DocumentRow>
  },

  remove: (workspaceId: number, id: number) =>
    request<void>(`/api/workspaces/${workspaceId}/documents/${id}`, { method: 'DELETE' }),

  chunks: (workspaceId: number, id: number) =>
    request<DocumentChunk[]>(`/api/workspaces/${workspaceId}/documents/${id}/chunks`),

  search: (workspaceId: number, query: string, topK = 6) =>
    request<{
      query: string
      mode: string
      citations: Citation[]
      took_ms: number
      vector_error: string | null
    }>(`/api/workspaces/${workspaceId}/documents/search`, {
      method: 'POST',
      body: JSON.stringify({ query, top_k: topK }),
    }),
}

// ----------------------------------------------------------------- conversations
export const conversations = {
  list: (workspaceId: number, query?: string) =>
    request<Conversation[]>(
      `/api/workspaces/${workspaceId}/conversations${query ? `?q=${encodeURIComponent(query)}` : ''}`,
    ),

  create: (workspaceId: number) =>
    request<ConversationDetail>(`/api/workspaces/${workspaceId}/conversations`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  get: (workspaceId: number, id: number) =>
    request<ConversationDetail>(`/api/workspaces/${workspaceId}/conversations/${id}`),

  update: (
    workspaceId: number,
    id: number,
    changes: { title?: string; is_pinned?: boolean; tags?: string[] },
  ) =>
    request<Conversation>(`/api/workspaces/${workspaceId}/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),

  remove: (workspaceId: number, id: number) =>
    request<void>(`/api/workspaces/${workspaceId}/conversations/${id}`, { method: 'DELETE' }),

  togglePin: (workspaceId: number, id: number, messageId: number) =>
    request<Message>(
      `/api/workspaces/${workspaceId}/conversations/${id}/messages/${messageId}/pin`,
      { method: 'PATCH' },
    ),

  /**
   * Send a message and yield each stream event as it arrives.
   *
   * An async generator rather than a callback: the caller writes a plain `for await` loop, and
   * cancellation is `break`, which propagates to the reader and aborts the request.
   *
   * The buffer matters. A network chunk is not a line — one chunk can hold three events, or half
   * of one. Splitting on the last newline and carrying the remainder forward is what stops a
   * token being dropped or a partial JSON object being parsed.
   */
  async *stream(
    workspaceId: number,
    conversationId: number,
    content: string,
    signal?: AbortSignal,
  ): AsyncGenerator<StreamEvent> {
    const response = await fetch(
      `/api/workspaces/${workspaceId}/conversations/${conversationId}/stream`,
      {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
        signal,
      },
    )

    if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
    if (!response.body) throw new ApiError(500, 'The server sent no response body.')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.trim()) yield JSON.parse(line) as StreamEvent
        }
      }
      if (buffer.trim()) yield JSON.parse(buffer) as StreamEvent
    } finally {
      reader.cancel().catch(() => {})
    }
  },
}
