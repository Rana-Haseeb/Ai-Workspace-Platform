import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrainCircuit, Check, Loader2, Pin, Plus, Trash2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { memory, type MemoryItem, type WorkspaceDetail } from '@/lib/api'

const KIND_LABEL: Record<string, string> = {
  preference: 'Preference',
  fact: 'Fact',
  topic: 'Topic',
  pinned: 'Pinned',
}

export default function Memory() {
  const workspace = useOutletContext<WorkspaceDetail>()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState('')
  const [editing, setEditing] = useState<number | null>(null)
  const [editText, setEditText] = useState('')

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['memory', workspace.id] })
    queryClient.invalidateQueries({ queryKey: ['memory-status', workspace.id] })
  }

  const list = useQuery({
    queryKey: ['memory', workspace.id],
    queryFn: () => memory.list(workspace.id),
  })
  const status = useQuery({
    queryKey: ['memory-status', workspace.id],
    queryFn: () => memory.status(workspace.id),
  })

  const add = useMutation({
    mutationFn: () => memory.create(workspace.id, { content: draft.trim(), kind: 'fact' }),
    onSuccess: () => {
      setDraft('')
      invalidate()
    },
  })
  const update = useMutation({
    mutationFn: (vars: { id: number; changes: Parameters<typeof memory.update>[2] }) =>
      memory.update(workspace.id, vars.id, vars.changes),
    onSuccess: () => {
      setEditing(null)
      invalidate()
    },
  })
  const remove = useMutation({
    mutationFn: (id: number) => memory.remove(workspace.id, id),
    onSuccess: invalidate,
  })
  const forgetAll = useMutation({
    mutationFn: () => memory.forgetAll(workspace.id),
    onSuccess: invalidate,
  })

  const items = list.data ?? []

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <h1 className="text-xl font-semibold tracking-tight">Memory</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        What {workspace.settings.assistant_name} has learned about you. Everything here is
        editable — it shapes every answer, so it should be yours to correct.
      </p>

      {!status.data?.enabled && (
        <p className="mt-4 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
          Memory is turned off for this workspace. Existing memories are kept but not used.
        </p>
      )}

      {status.data && status.data.total > 0 && (
        <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg bg-muted/40 px-4 py-3">
          <div>
            <p className="text-[11px] text-muted-foreground">Remembered</p>
            <p className="tabular text-sm font-medium">{status.data.total}</p>
          </div>
          <div>
            <p className="text-[11px] text-muted-foreground">Used per answer</p>
            <p className="tabular text-sm font-medium">
              {status.data.in_context} of {status.data.max_in_context}
            </p>
          </div>
          <div>
            <p className="text-[11px] text-muted-foreground">Pinned</p>
            <p className="tabular text-sm font-medium">{status.data.pinned}</p>
          </div>
        </div>
      )}

      <form
        className="mt-6 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          if (draft.trim()) add.mutate()
        }}
      >
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Teach it something, e.g. Prefers British English"
          aria-label="New memory"
        />
        <Button type="submit" disabled={!draft.trim() || add.isPending}>
          {add.isPending ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Plus className="size-4" aria-hidden />
          )}
          Add
        </Button>
      </form>

      <div className="mt-6 space-y-2">
        {items.length === 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Nothing remembered yet</CardTitle>
              <CardDescription>
                Tell the assistant a preference in a conversation and it will appear here. You can
                also add one directly above.
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {items.map((item: MemoryItem) => (
          <div
            key={item.id}
            className={[
              'rounded-lg border px-4 py-3 transition-colors',
              // A quiet ring on the ones that will actually be sent. Ranking is invisible
              // otherwise, and "why did it not use that?" is the obvious first question.
              item.in_context ? 'border-primary/40 bg-primary/5' : 'border-border',
            ].join(' ')}
          >
            {editing === item.id ? (
              <div className="flex gap-2">
                <Input
                  value={editText}
                  onChange={(event) => setEditText(event.target.value)}
                  aria-label="Edit memory"
                  autoFocus
                />
                <Button
                  size="icon"
                  onClick={() => update.mutate({ id: item.id, changes: { content: editText } })}
                  aria-label="Save"
                >
                  <Check className="size-4" aria-hidden />
                </Button>
                <Button
                  size="icon"
                  variant="ghost"
                  onClick={() => setEditing(null)}
                  aria-label="Cancel"
                >
                  <X className="size-4" aria-hidden />
                </Button>
              </div>
            ) : (
              <>
                <div className="flex items-start gap-2">
                  <BrainCircuit
                    className={`mt-0.5 size-4 shrink-0 ${
                      item.in_context ? 'text-primary' : 'text-muted-foreground'
                    }`}
                    aria-hidden
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setEditing(item.id)
                      setEditText(item.content)
                    }}
                    className="flex-1 text-left text-sm hover:underline"
                    title="Click to edit"
                  >
                    {item.content}
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      update.mutate({ id: item.id, changes: { is_pinned: !item.is_pinned } })
                    }
                    aria-label={item.is_pinned ? 'Unpin memory' : 'Pin memory'}
                    aria-pressed={item.is_pinned}
                    className={`shrink-0 rounded p-1 ${
                      item.is_pinned ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <Pin className="size-3.5" aria-hidden />
                  </button>
                  <button
                    type="button"
                    onClick={() => remove.mutate(item.id)}
                    aria-label={`Forget: ${item.content.slice(0, 40)}`}
                    className="shrink-0 rounded p-1 text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="size-3.5" aria-hidden />
                  </button>
                </div>

                <div className="mt-1.5 flex flex-wrap items-center gap-2 pl-6 text-[11px] text-muted-foreground">
                  <span className="rounded border border-border px-1.5 py-0.5">
                    {KIND_LABEL[item.kind] ?? item.kind}
                  </span>
                  {item.workspace_id === null && (
                    <span title="Applies in every workspace">All workspaces</span>
                  )}
                  <span className="tabular">importance {item.importance.toFixed(2)}</span>
                  <span className="tabular">rank {item.rank_score.toFixed(3)}</span>
                  {item.use_count > 0 && (
                    <span className="tabular">used {item.use_count}x</span>
                  )}
                  {item.in_context && <span className="text-primary">in context</span>}
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      {items.length > 0 && (
        <div className="mt-8 border-t border-border pt-5">
          <Button
            variant="outline"
            className="border-destructive/50 text-destructive hover:bg-destructive/10"
            onClick={() => {
              if (window.confirm('Forget everything? This cannot be undone.')) forgetAll.mutate()
            }}
            disabled={forgetAll.isPending}
          >
            {forgetAll.isPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <Trash2 className="size-4" aria-hidden />
            )}
            Forget everything
          </Button>
        </div>
      )}
    </div>
  )
}
