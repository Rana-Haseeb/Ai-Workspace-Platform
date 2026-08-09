import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FolderPlus, Loader2, LogOut } from 'lucide-react'

import { ThemeToggle } from '@/components/ThemeToggle'
import { CreateWorkspaceDialog } from '@/components/workspaces/CreateWorkspaceDialog'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/hooks/useAuth'
import { workspaces } from '@/lib/api'

/**
 * The `/` route.
 *
 * With workspaces, it forwards to the most recent one so signing in lands somewhere useful.
 * Without any, it is the onboarding screen — an invitation with one action, not an apology for
 * being empty.
 */
export default function WorkspaceIndex() {
  const { user, logout } = useAuth()
  const [creating, setCreating] = useState(false)
  const { data, isLoading } = useQuery({ queryKey: ['workspaces'], queryFn: workspaces.list })

  if (isLoading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-background">
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
      </div>
    )
  }

  if (data && data.length > 0) return <Navigate to={`/w/${data[0].id}`} replace />

  return (
    <div className="min-h-dvh bg-background">
      <header className="flex h-14 items-center justify-end gap-1 px-5">
        <span className="mr-2 text-sm text-muted-foreground">{user?.email}</span>
        <ThemeToggle />
        <Button variant="ghost" size="icon" onClick={logout} aria-label="Sign out">
          <LogOut className="size-4" />
        </Button>
      </header>

      <main className="mx-auto flex max-w-md flex-col items-center px-6 py-24 text-center">
        <div className="flex size-12 items-center justify-center rounded-xl bg-primary">
          <FolderPlus className="size-6 text-primary-foreground" aria-hidden />
        </div>
        <h1 className="mt-6 text-2xl font-semibold tracking-tight">
          Create your first workspace
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          A workspace keeps its own conversations, documents, memory and assistant setup —
          research separate from marketing, university separate from work.
        </p>
        <Button className="mt-8" onClick={() => setCreating(true)}>
          <FolderPlus className="size-4" aria-hidden />
          New workspace
        </Button>
      </main>

      <CreateWorkspaceDialog open={creating} onOpenChange={setCreating} />
    </div>
  )
}
