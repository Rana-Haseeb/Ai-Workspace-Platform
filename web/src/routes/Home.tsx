import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderPlus, Loader2, LogOut, Sparkles } from 'lucide-react'

import { ThemeToggle } from '@/components/ThemeToggle'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/hooks/useAuth'
import { workspaces } from '@/lib/api'

/**
 * Phase 1 signed-in screen.
 *
 * It exists to prove the loop end to end: authenticated identity, a workspace created against
 * that identity, and a list that only ever contains your own. Phase 2 replaces it with the real
 * four-column app shell.
 */
export default function Home() {
  const { user, logout } = useAuth()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['workspaces'],
    queryFn: workspaces.list,
  })

  const createWorkspace = useMutation({
    mutationFn: (workspaceName: string) => workspaces.create(workspaceName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspaces'] })
      setName('')
    },
  })

  return (
    <div className="min-h-dvh bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary">
              <Sparkles className="size-4 text-primary-foreground" aria-hidden />
            </div>
            <span className="font-semibold tracking-tight">AI Workspace</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="mr-2 text-sm text-muted-foreground">{user?.email}</span>
            <ThemeToggle />
            <Button variant="ghost" size="icon" onClick={logout} aria-label="Sign out">
              <LogOut className="size-4" />
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Your workspaces</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Only you can see these. Another account asking for one of them gets a 403.
        </p>

        <form
          className="mt-6 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (name.trim()) createWorkspace.mutate(name.trim())
          }}
        >
          <Input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Research"
            aria-label="Workspace name"
          />
          <Button type="submit" disabled={!name.trim() || createWorkspace.isPending}>
            {createWorkspace.isPending ? (
              <Loader2 className="size-4 animate-spin" aria-hidden />
            ) : (
              <FolderPlus className="size-4" aria-hidden />
            )}
            Create
          </Button>
        </form>

        <div className="mt-8 space-y-3">
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

          {data?.length === 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Start your first workspace</CardTitle>
                <CardDescription>
                  A workspace holds its own conversations, documents, memory and assistant setup.
                </CardDescription>
              </CardHeader>
            </Card>
          )}

          {data?.map((workspace) => (
            <Card key={workspace.id}>
              <CardHeader>
                <CardTitle className="text-base">{workspace.name}</CardTitle>
                <CardDescription>
                  Created {new Date(workspace.created_at).toLocaleDateString()}
                </CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </main>
    </div>
  )
}
