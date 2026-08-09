import { useState } from 'react'
import { Navigate, Outlet, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Loader2, LogOut } from 'lucide-react'

import { ThemeToggle } from '@/components/ThemeToggle'
import { WorkspaceRail } from '@/components/layout/WorkspaceRail'
import { WorkspaceSidebar } from '@/components/layout/WorkspaceSidebar'
import { CreateWorkspaceDialog } from '@/components/workspaces/CreateWorkspaceDialog'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '@/hooks/useAuth'
import { workspaces } from '@/lib/api'

/** Shown while a workspace loads, so the layout does not jump when it arrives. */
function ShellSkeleton() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
    </div>
  )
}

export function AppShell() {
  const { workspaceId } = useParams()
  const { user, logout } = useAuth()
  const [creating, setCreating] = useState(false)

  const workspaceList = useQuery({ queryKey: ['workspaces'], queryFn: workspaces.list })
  const current = useQuery({
    queryKey: ['workspace', workspaceId],
    queryFn: () => workspaces.get(Number(workspaceId)),
    enabled: Boolean(workspaceId),
  })

  // A workspace that 404s or 403s — deleted, or someone else's id typed into the URL — sends the
  // user back to their own list rather than leaving them on a broken screen.
  if (current.isError) return <Navigate to="/" replace />

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      <WorkspaceRail
        workspaces={workspaceList.data ?? []}
        onCreate={() => setCreating(true)}
      />

      {/* Hidden on narrow screens; the workspace name still shows in the header below. */}
      <aside className="hidden md:block">
        {current.data && <WorkspaceSidebar workspace={current.data} />}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-5">
          <p className="truncate text-sm font-medium md:hidden">{current.data?.name}</p>
          <div className="hidden md:block" />
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button variant="ghost" size="sm" className="gap-2">
                    <span className="max-w-40 truncate text-sm text-muted-foreground">
                      {user?.email}
                    </span>
                  </Button>
                }
              />
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={logout}>
                  <LogOut className="size-4" aria-hidden />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          {current.isLoading ? <ShellSkeleton /> : <Outlet context={current.data} />}
        </main>
      </div>

      <CreateWorkspaceDialog open={creating} onOpenChange={setCreating} />
    </div>
  )
}
