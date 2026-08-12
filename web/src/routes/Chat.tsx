import { useEffect, useRef, useState } from 'react'
import { useOutletContext, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Sparkles } from 'lucide-react'

import { Composer } from '@/components/chat/Composer'
import { MessageBubble } from '@/components/chat/MessageBubble'
import {
  conversations,
  skills as skillsApi,
  type Citation,
  type MemoryUsed,
  type Message,
  type WorkspaceDetail,
} from '@/lib/api'

/** A placeholder message object for text that is still arriving. */
function draftMessage(
  content: string,
  citations: Citation[] = [],
  memoryUsed: MemoryUsed[] = [],
): Message {
  return {
    id: -1,
    role: 'assistant',
    content,
    citations,
    memory_used: memoryUsed,
    is_pinned: false,
    model: null,
    tokens_in: 0,
    tokens_out: 0,
    cost_usd: 0,
    latency_ms: 0,
    created_at: new Date().toISOString(),
  }
}

export default function Chat() {
  const workspace = useOutletContext<WorkspaceDetail>()
  const { conversationId } = useParams()
  const id = Number(conversationId)
  const queryClient = useQueryClient()

  const [streamed, setStreamed] = useState<string | null>(null)
  const [streamCitations, setStreamCitations] = useState<Citation[]>([])
  const [streamMemory, setStreamMemory] = useState<MemoryUsed[]>([])
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['conversation', id],
    queryFn: () => conversations.get(workspace.id, id),
    enabled: Number.isFinite(id),
  })

  const { data: availableSkills } = useQuery({
    queryKey: ['skills', workspace.id],
    queryFn: () => skillsApi.list(workspace.id),
  })

  const streaming = streamed !== null

  // Follow the reply as it grows. `block: 'end'` rather than smooth scrolling — a smooth scroll
  // restarting on every token fights the user if they try to scroll up mid-reply.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [data?.messages.length, streamed, pending])

  const togglePin = useMutation({
    mutationFn: (messageId: number) => conversations.togglePin(workspace.id, id, messageId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conversation', id] }),
  })

  async function send(text: string, skillSlug?: string) {
    setError(null)

    // A skill run is a one-shot call, not a conversation turn: it has its own system prompt and
    // no history. Sending it down the chat stream would layer the workspace persona on top of
    // the skill's instructions, which is exactly what the skill is trying to replace.
    if (skillSlug) {
      setPending(text)
      try {
        // The conversation id makes the backend store the run as a user/assistant pair, so the
        // result survives a reload instead of living only in this component's state.
        await skillsApi.run(workspace.id, skillSlug, text, id)
        await queryClient.invalidateQueries({ queryKey: ['conversation', id] })
        queryClient.invalidateQueries({ queryKey: ['conversations', workspace.id] })
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'The skill failed.')
      } finally {
        setPending(null)
      }
      return
    }

    setPending(text)
    setStreamed('')
    setStreamCitations([])
    setStreamMemory([])

    const controller = new AbortController()
    abortRef.current = controller

    try {
      for await (const event of conversations.stream(workspace.id, id, text, controller.signal)) {
        // Sources arrive in the opening event, before any text, so the reader can see what is
        // being consulted while the answer is still being written.
        if (event.type === 'start') {
          setStreamCitations(event.citations ?? [])
          setStreamMemory(event.memory_used ?? [])
        }
        if (event.type === 'token') setStreamed((current) => (current ?? '') + event.text)
        if (event.type === 'error') setError(event.detail)
      }
    } catch (caught) {
      // An abort is the user pressing stop, not a failure worth reporting.
      if (!(caught instanceof DOMException && caught.name === 'AbortError')) {
        setError(caught instanceof Error ? caught.message : 'The reply failed.')
      }
    } finally {
      abortRef.current = null
      setStreamed(null)
      setPending(null)
      // Re-read from the server so the transcript shows the persisted rows, with their real ids,
      // model names and latency, rather than the optimistic text.
      queryClient.invalidateQueries({ queryKey: ['conversation', id] })
      queryClient.invalidateQueries({ queryKey: ['conversations', workspace.id] })
    }
  }

  const assistantName = workspace.settings.assistant_name
  const messages = data?.messages ?? []
  const empty = !isLoading && messages.length === 0 && !streaming

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
          {empty && (
            <div className="flex flex-col items-center py-20 text-center">
              <div className="flex size-11 items-center justify-center rounded-xl bg-primary">
                <Sparkles className="size-5 text-primary-foreground" aria-hidden />
              </div>
              <h2 className="mt-5 text-lg font-semibold tracking-tight">{assistantName}</h2>
              <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">
                {workspace.settings.role}
              </p>
            </div>
          )}

          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              assistantName={assistantName}
              onTogglePin={
                message.role === 'assistant' ? () => togglePin.mutate(message.id) : undefined
              }
            />
          ))}

          {/* The turn in flight, rendered optimistically so the question appears instantly. */}
          {pending && (
            <MessageBubble
              message={{ ...draftMessage(pending), role: 'user' }}
              assistantName={assistantName}
            />
          )}
          {streaming && (
            <MessageBubble
              message={draftMessage(streamed ?? '', streamCitations, streamMemory)}
              assistantName={assistantName}
              streaming
            />
          )}

          {error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-sm text-destructive"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>{error}</span>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <Composer
        onSend={send}
        onStop={() => abortRef.current?.abort()}
        streaming={streaming}
        placeholder={`Message ${assistantName}`}
        skills={availableSkills ?? []}
      />
    </div>
  )
}
