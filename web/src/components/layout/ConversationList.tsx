import { useEffect, useState } from 'react'
import { NavLink, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquarePlus, Pin, Search, Trash2 } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { conversations } from '@/lib/api'

/**
 * Debounced so typing a five-letter query fires one request, not five.
 *
 * The timer is set and cleared in an effect. Doing it during render would schedule a new timer
 * on every render and update state mid-render, which React rightly refuses to allow.
 */
function useDebounced<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}

export function ConversationList({ workspaceId }: { workspaceId: number }) {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const debouncedQuery = useDebounced(query)

  const { data } = useQuery({
    queryKey: ['conversations', workspaceId, debouncedQuery],
    queryFn: () => conversations.list(workspaceId, debouncedQuery || undefined),
  })

  const create = useMutation({
    mutationFn: () => conversations.create(workspaceId),
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ['conversations', workspaceId] })
      navigate(`/w/${workspaceId}/c/${conversation.id}`)
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => conversations.remove(workspaceId, id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['conversations', workspaceId] })
      if (String(id) === conversationId) navigate(`/w/${workspaceId}`)
    },
  })

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 border-b border-border p-2">
        <button
          type="button"
          onClick={() => create.mutate()}
          className="flex w-full items-center gap-2 rounded-md bg-primary px-2.5 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <MessageSquarePlus className="size-4" aria-hidden />
          New chat
        </button>

        <div className="relative">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search conversations"
            aria-label="Search conversations"
            className="h-8 pl-8 text-sm"
          />
        </div>
      </div>

      <nav aria-label="Conversations" className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {data?.length === 0 && (
          <p className="px-2.5 py-6 text-center text-xs text-muted-foreground">
            {query ? 'Nothing matches that.' : 'No conversations yet.'}
          </p>
        )}

        {data?.map((conversation) => (
          <div key={conversation.id} className="group relative">
            <NavLink
              to={`/w/${workspaceId}/c/${conversation.id}`}
              className={({ isActive }) =>
                [
                  'block rounded-md px-2.5 py-2 pr-8 transition-colors',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                    : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground',
                ].join(' ')
              }
            >
              <span className="flex items-center gap-1.5">
                {conversation.is_pinned && (
                  <Pin className="size-3 shrink-0 text-primary" aria-label="Pinned" />
                )}
                <span className="truncate text-sm">{conversation.title}</span>
              </span>
              {conversation.preview && (
                <span className="mt-0.5 block truncate text-xs text-muted-foreground/70">
                  {conversation.preview}
                </span>
              )}
            </NavLink>

            <button
              type="button"
              onClick={() => {
                if (window.confirm(`Delete "${conversation.title}"?`)) remove.mutate(conversation.id)
              }}
              aria-label={`Delete ${conversation.title}`}
              className="absolute right-1.5 top-2 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
            >
              <Trash2 className="size-3.5" aria-hidden />
            </button>
          </div>
        ))}
      </nav>
    </div>
  )
}
