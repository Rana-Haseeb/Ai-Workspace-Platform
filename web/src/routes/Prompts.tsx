import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, History, Loader2, Plus, Trash2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { prompts, type PromptTemplate, type WorkspaceDetail } from '@/lib/api'

const CATEGORIES = ['writing', 'programming', 'research', 'business', 'education', 'custom']

export default function Prompts() {
  const workspace = useOutletContext<WorkspaceDetail>()
  const queryClient = useQueryClient()

  const [filter, setFilter] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [category, setCategory] = useState('custom')
  const [editing, setEditing] = useState<PromptTemplate | null>(null)
  const [historyFor, setHistoryFor] = useState<PromptTemplate | null>(null)
  const [copied, setCopied] = useState<number | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['prompts', workspace.id] })

  const { data } = useQuery({
    queryKey: ['prompts', workspace.id, filter],
    queryFn: () => prompts.list(workspace.id, filter ?? undefined),
  })

  const history = useQuery({
    queryKey: ['prompt-history', historyFor?.id],
    queryFn: () => prompts.history(workspace.id, historyFor!.id),
    enabled: historyFor !== null,
  })

  const create = useMutation({
    mutationFn: () => prompts.create(workspace.id, { title, body, category }),
    onSuccess: () => {
      setCreating(false)
      setTitle('')
      setBody('')
      setCategory('custom')
      invalidate()
    },
  })

  const save = useMutation({
    mutationFn: () => prompts.edit(workspace.id, editing!.id, { title, body }),
    onSuccess: () => {
      setEditing(null)
      invalidate()
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => prompts.remove(workspace.id, id),
    onSuccess: invalidate,
  })

  function startEdit(prompt: PromptTemplate) {
    setEditing(prompt)
    setTitle(prompt.title)
    setBody(prompt.body)
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Prompt library</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Saved prompts you reuse. Editing one creates a new version — the old text is kept, so
            an old conversation can still be traced to the prompt that produced it.
          </p>
        </div>
        <Button onClick={() => setCreating(true)} className="shrink-0">
          <Plus className="size-4" aria-hidden />
          New
        </Button>
      </div>

      <div className="mt-5 flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => setFilter(null)}
          aria-pressed={filter === null}
          className={`rounded-md border px-2 py-1 text-xs transition-colors ${
            filter === null ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground'
          }`}
        >
          All
        </button>
        {CATEGORIES.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setFilter(option)}
            aria-pressed={filter === option}
            className={`rounded-md border px-2 py-1 text-xs transition-colors ${
              filter === option ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground'
            }`}
          >
            {option}
          </button>
        ))}
      </div>

      {(creating || editing) && (
        <div className="mt-5 space-y-3 rounded-lg border border-border p-4">
          <p className="text-sm font-medium">
            {editing ? `Editing "${editing.title}" — saves as version ${editing.version + 1}` : 'New prompt'}
          </p>
          <Input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Title"
            aria-label="Prompt title"
          />
          <Textarea
            rows={5}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder="The prompt text. Use {placeholders} for the parts you fill in each time."
            aria-label="Prompt body"
            className="font-mono text-xs"
          />
          {creating && (
            <div className="flex flex-wrap gap-1.5">
              {CATEGORIES.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setCategory(option)}
                  aria-pressed={category === option}
                  className={`rounded-md border px-2 py-1 text-xs ${
                    category === option ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <Button
              onClick={() => (editing ? save.mutate() : create.mutate())}
              disabled={!title.trim() || !body.trim() || create.isPending || save.isPending}
            >
              {(create.isPending || save.isPending) && (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              )}
              {editing ? 'Save as new version' : 'Create'}
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                setCreating(false)
                setEditing(null)
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div className="mt-6 space-y-2">
        {data?.length === 0 && !creating && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">No prompts yet</CardTitle>
              <CardDescription>
                Save a prompt you type often and it will be one click away.
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        {data?.map((prompt) => (
          <div key={prompt.id} className="rounded-lg border border-border px-4 py-3">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{prompt.title}</p>
                <p className="mt-1 line-clamp-3 font-mono text-xs leading-relaxed text-muted-foreground">
                  {prompt.body}
                </p>
              </div>
              <div className="flex shrink-0 gap-0.5">
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(prompt.body)
                    prompts.use(workspace.id, prompt.id).then(invalidate)
                    setCopied(prompt.id)
                    window.setTimeout(() => setCopied(null), 2000)
                  }}
                  aria-label={`Copy ${prompt.title}`}
                  className="rounded p-1 text-muted-foreground hover:text-foreground"
                >
                  {copied === prompt.id ? (
                    <Check className="size-3.5 text-primary" aria-hidden />
                  ) : (
                    <Copy className="size-3.5" aria-hidden />
                  )}
                </button>
                {prompt.version > 1 && (
                  <button
                    type="button"
                    onClick={() => setHistoryFor(historyFor?.id === prompt.id ? null : prompt)}
                    aria-label={`Version history for ${prompt.title}`}
                    className="rounded p-1 text-muted-foreground hover:text-foreground"
                  >
                    <History className="size-3.5" aria-hidden />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Delete "${prompt.title}" and all its versions?`)) {
                      remove.mutate(prompt.id)
                    }
                  }}
                  aria-label={`Delete ${prompt.title}`}
                  className="rounded p-1 text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="size-3.5" aria-hidden />
                </button>
              </div>
            </div>

            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
              <span className="rounded border border-border px-1.5 py-0.5">{prompt.category}</span>
              <span className="tabular">v{prompt.version}</span>
              {prompt.workspace_id === null && <span>All workspaces</span>}
              {prompt.use_count > 0 && <span className="tabular">used {prompt.use_count}x</span>}
              <button
                type="button"
                onClick={() => startEdit(prompt)}
                className="ml-auto hover:text-foreground hover:underline"
              >
                Edit
              </button>
            </div>

            {historyFor?.id === prompt.id && history.data && (
              <div className="mt-3 rounded-md bg-muted/40 p-3">
                <div className="flex items-center justify-between">
                  <p className="text-[11px] font-medium">Version history</p>
                  <button
                    type="button"
                    onClick={() => setHistoryFor(null)}
                    aria-label="Close history"
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="size-3.5" aria-hidden />
                  </button>
                </div>
                <ul className="mt-2 space-y-2">
                  {history.data.map((version) => (
                    <li key={version.id} className="text-xs">
                      <span className="tabular text-muted-foreground">v{version.version}</span>
                      <span className="ml-2 font-mono text-muted-foreground">{version.body}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
