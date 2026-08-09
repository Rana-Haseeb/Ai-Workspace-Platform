import { NavLink } from 'react-router-dom'
import {
  BrainCircuit,
  FileText,
  LayoutDashboard,
  Library,
  MessagesSquare,
  Settings,
  Sparkles,
} from 'lucide-react'

import { workspaceIcon } from '@/lib/icons'
import type { WorkspaceDetail } from '@/lib/api'

/**
 * Navigation within one workspace.
 *
 * Sections that arrive in later phases are shown and disabled rather than hidden. Hiding them
 * would make the product look smaller than it is during a demo; disabling them states plainly
 * what exists now. Each carries the phase it lands in as its title attribute.
 */
const SECTIONS = [
  { to: '', label: 'Chat', icon: MessagesSquare, ready: false, phase: 'Phase 3' },
  { to: 'documents', label: 'Documents', icon: FileText, ready: false, phase: 'Phase 4' },
  { to: 'memory', label: 'Memory', icon: BrainCircuit, ready: false, phase: 'Phase 5' },
  { to: 'prompts', label: 'Prompts', icon: Library, ready: false, phase: 'Phase 6' },
  { to: 'skills', label: 'Skills', icon: Sparkles, ready: false, phase: 'Phase 6' },
  { to: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, ready: false, phase: 'Phase 7' },
  { to: 'settings', label: 'Settings', icon: Settings, ready: true, phase: '' },
] as const

export function WorkspaceSidebar({ workspace }: { workspace: WorkspaceDetail }) {
  const Icon = workspaceIcon(workspace.icon)

  return (
    <div className="flex h-full w-60 shrink-0 flex-col border-r border-border">
      <div className="flex items-start gap-2.5 border-b border-border px-4 py-3.5">
        <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{workspace.name}</p>
          <p className="truncate text-xs text-muted-foreground">
            {workspace.settings.assistant_name}
          </p>
        </div>
      </div>

      <nav aria-label="Workspace sections" className="flex-1 space-y-0.5 p-2">
        {SECTIONS.map(({ to, label, icon: SectionIcon, ready, phase }) =>
          ready ? (
            <NavLink
              key={label}
              to={to ? `/w/${workspace.id}/${to}` : `/w/${workspace.id}`}
              end
              className={({ isActive }) =>
                [
                  'flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-sidebar-accent font-medium text-sidebar-accent-foreground'
                    : 'text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground',
                ].join(' ')
              }
            >
              <SectionIcon className="size-4" aria-hidden />
              {label}
            </NavLink>
          ) : (
            <span
              key={label}
              title={`Arrives in ${phase}`}
              aria-disabled="true"
              className="flex cursor-not-allowed items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-muted-foreground/50"
            >
              <SectionIcon className="size-4" aria-hidden />
              {label}
              <span className="ml-auto text-[10px] uppercase tracking-wide">{phase}</span>
            </span>
          ),
        )}
      </nav>
    </div>
  )
}
