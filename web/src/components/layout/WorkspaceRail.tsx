import { NavLink } from 'react-router-dom'
import { Plus, Sparkles } from 'lucide-react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { workspaceIcon } from '@/lib/icons'
import type { Workspace } from '@/lib/api'

/**
 * The narrow column of workspace icons.
 *
 * Icons alone would be undiscoverable, so every one carries a tooltip and an `aria-label`. The
 * active workspace is marked by a bar on the left edge as well as a colour change — colour on
 * its own fails for anyone who cannot distinguish it.
 */
export function WorkspaceRail({
  workspaces,
  onCreate,
}: {
  workspaces: Workspace[]
  onCreate: () => void
}) {
  return (
    <nav
      aria-label="Workspaces"
      className="flex w-14 shrink-0 flex-col items-center gap-1 border-r border-border bg-sidebar py-3"
    >
      <div className="mb-2 flex size-9 items-center justify-center rounded-lg bg-primary">
        <Sparkles className="size-4 text-primary-foreground" aria-hidden />
      </div>

      {workspaces.map((workspace) => {
        const Icon = workspaceIcon(workspace.icon)
        return (
          <Tooltip key={workspace.id}>
            <TooltipTrigger
              render={
                <NavLink
                  to={`/w/${workspace.id}`}
                  aria-label={workspace.name}
                  className={({ isActive }) =>
                    [
                      'relative flex size-9 items-center justify-center rounded-lg transition-colors',
                      isActive
                        ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                        : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground',
                      // The active marker: a bar, not only a colour.
                      isActive
                        ? 'before:absolute before:-left-3 before:h-5 before:w-0.5 before:rounded-full before:bg-primary'
                        : '',
                    ].join(' ')
                  }
                >
                  <Icon className="size-4.5" aria-hidden />
                </NavLink>
              }
            />
            <TooltipContent side="right">{workspace.name}</TooltipContent>
          </Tooltip>
        )
      })}

      <Tooltip>
        <TooltipTrigger
          render={
            <button
              type="button"
              onClick={onCreate}
              aria-label="New workspace"
              className="flex size-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-foreground"
            >
              <Plus className="size-4.5" aria-hidden />
            </button>
          }
        />
        <TooltipContent side="right">New workspace</TooltipContent>
      </Tooltip>
    </nav>
  )
}
