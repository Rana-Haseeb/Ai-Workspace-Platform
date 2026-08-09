import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { workspaces } from '@/lib/api'
import { workspaceIcon } from '@/lib/icons'

export function CreateWorkspaceDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [icon, setIcon] = useState('folder')
  const [error, setError] = useState<string | null>(null)

  // The icon list comes from the server rather than a second copy here, so the picker can never
  // offer something the API would reject.
  const { data: meta } = useQuery({ queryKey: ['workspace-meta'], queryFn: workspaces.meta })

  const create = useMutation({
    mutationFn: () => workspaces.create(name.trim(), description.trim(), icon),
    onSuccess: (workspace) => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] })
      onOpenChange(false)
      setName('')
      setDescription('')
      setIcon('folder')
      setError(null)
      navigate(`/w/${workspace.id}`)
    },
    onError: (caught) =>
      setError(caught instanceof Error ? caught.message : 'Could not create the workspace.'),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New workspace</DialogTitle>
          <DialogDescription>
            Each workspace keeps its own conversations, documents, memory and assistant setup.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            if (name.trim()) create.mutate()
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="workspace-name">Name</Label>
            <Input
              id="workspace-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Research"
              autoFocus
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="workspace-description">
              Description <span className="text-muted-foreground">(optional)</span>
            </Label>
            <Textarea
              id="workspace-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Comparing vector databases for the platform"
              rows={2}
            />
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Icon</legend>
            <div className="flex flex-wrap gap-1.5">
              {(meta?.icons ?? ['folder']).map((name_) => {
                const Icon = workspaceIcon(name_)
                const selected = icon === name_
                return (
                  <button
                    key={name_}
                    type="button"
                    onClick={() => setIcon(name_)}
                    aria-label={name_}
                    aria-pressed={selected}
                    className={[
                      'flex size-9 items-center justify-center rounded-md border transition-colors',
                      selected
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border text-muted-foreground hover:border-border hover:text-foreground',
                    ].join(' ')}
                  >
                    <Icon className="size-4" aria-hidden />
                  </button>
                )
              })}
            </div>
          </fieldset>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
              Create workspace
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
