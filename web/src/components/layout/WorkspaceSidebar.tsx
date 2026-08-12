import { NavLink } from 'react-router-dom'
import {
  BrainCircuit,
  FileText,
  LayoutDashboard,
  Library,
  Settings,
  Sparkles,
} from 'lucide-react'

import { ConversationList } from '@/components/layout/ConversationList'
import { workspaceIcon } from '@/lib/icons'
import type { WorkspaceDetail } from '@/lib/api'

/**
 * The workspace column: what this workspace is, where you can go inside it, and its
 * conversations.
 *
 * Sections that arrive in later phases are shown and disabled rather than hidden. Hiding them
 * would make the product look smaller than it is; disabling them states plainly what exists now.
 */
const SECTIONS = [
  { to: 'documents', label: 'Documents', icon: FileText, ready: true, phase: '' },
  { to: 'memory', label: 'Memory', icon: BrainCircuit, ready: true, phase: '' },
  { to: 'prompts', label: 'Prompts', icon: Library, ready: true, phase: '' },
  { to: 'skills', label: 'Skills', icon: Sparkles, ready: true, phase: '' },
  { to: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, ready: true, phase: '' },
  { to: 'settings', label: 'Settings', icon: Settings, ready: true, phase: '' },
] as const

export function WorkspaceSidebar({ workspace }: { workspace: WorkspaceDetail }) {
  const Icon = workspaceIcon(workspace.icon)

  return (
    <div className="flex h-full w-64 shrink-0 flex-col border-r border-border">
      <div className="flex items-start gap-2.5 border-b border-border px-4 py-3.5">
        <Icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{workspace.name}</p>
          <p className="truncate text-xs text-muted-foreground">
            {workspace.settings.assistant_name}
          </p>
        </div>
      </div>

      {/* Conversations take the space that is left, and scroll on their own. */}
      <div className="min-h-0 flex-1">
        <ConversationList workspaceId={workspace.id} />
      </div>

      <nav
        aria-label="Workspace sections"
        className="grid grid-cols-3 gap-0.5 border-t border-border p-2"
      >
        {SECTIONS.map(({ to, label, icon: SectionIcon, ready, phase }) =>
          ready ? (
            <NavLink
              key={label}
              to={`/w/${workspace.id}/${to}`}
              title={label}
              className={({ isActive }) =>
                [
                  'flex flex-col items-center gap-1 rounded-md px-1 py-2 text-[10px] transition-colors',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
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
              title={`Arrives in Phase ${phase.slice(1)}`}
              aria-disabled="true"
              className="flex cursor-not-allowed flex-col items-center gap-1 rounded-md px-1 py-2 text-[10px] text-muted-foreground/40"
            >
              <SectionIcon className="size-4" aria-hidden />
              {label}
            </span>
          ),
        )}
      </nav>
    </div>
  )
}
