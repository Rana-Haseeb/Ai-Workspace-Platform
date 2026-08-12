import { Link, useOutletContext } from 'react-router-dom'
import { BrainCircuit, FileText, MessagesSquare, Settings, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { workspaceIcon } from '@/lib/icons'
import type { WorkspaceDetail } from '@/lib/api'

/**
 * Workspace overview.
 *
 * Placeholder for the chat screen that lands in Phase 3. It shows the configuration that is
 * already live, so the workspace is not an empty room while the rest is built.
 */
export default function WorkspaceHome() {
  const workspace = useOutletContext<WorkspaceDetail>()
  const Icon = workspaceIcon(workspace.icon)
  const { settings } = workspace

  const facts = [
    { label: 'Model', value: settings.model ?? 'Deployment default' },
    { label: 'Temperature', value: settings.temperature.toFixed(1) },
    { label: 'Max tokens', value: settings.max_tokens.toLocaleString() },
    { label: 'Personality', value: settings.personality },
    { label: 'Response style', value: settings.response_style },
    { label: 'Memory', value: settings.use_memory ? 'On' : 'Off' },
  ]

  const upcoming = [
    { icon: MessagesSquare, label: 'Chat with history and streaming', phase: 'Ready' },
    { icon: FileText, label: 'Documents with cited answers', phase: 'Ready' },
    { icon: BrainCircuit, label: 'Memory that persists across sessions', phase: 'Ready' },
    { icon: Sparkles, label: 'Prompt library and reusable skills', phase: 'Ready' },
  ]

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <div className="flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Icon className="size-5 text-muted-foreground" aria-hidden />
        </div>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight">{workspace.name}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {workspace.description ?? 'No description yet.'}
          </p>
        </div>
      </div>

      <Card className="mt-6">
        <CardHeader className="flex-row items-start justify-between gap-4">
          <div>
            <CardTitle className="text-base">{settings.assistant_name}</CardTitle>
            <CardDescription>{settings.role}</CardDescription>
          </div>
          {/* Renders as an <a>, not a <button>: this navigates, so it should be middle-clickable
              and open-in-new-tab-able like any link. `nativeButton={false}` tells Base UI the
              non-button element is deliberate rather than an accessibility mistake. */}
          <Button
            variant="outline"
            size="sm"
            nativeButton={false}
            render={<Link to={`/w/${workspace.id}/settings`} />}
          >
            <Settings className="size-4" aria-hidden />
            Configure
          </Button>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
            {facts.map(({ label, value }) => (
              <div key={label}>
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="tabular truncate text-sm font-medium">{value}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-5 rounded-md bg-muted/50 p-3">
            <p className="text-xs text-muted-foreground">System prompt</p>
            <p className="mt-1 font-mono text-xs leading-relaxed">{settings.system_prompt}</p>
          </div>
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-base">Coming next</CardTitle>
          <CardDescription>Built in order, each verified before the next starts.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="space-y-3">
            {upcoming.map(({ icon: ItemIcon, label, phase }) => (
              <li key={label} className="flex items-center gap-3 text-sm">
                <ItemIcon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="text-muted-foreground">{label}</span>
                <span className="ml-auto text-xs uppercase tracking-wide text-muted-foreground/70">
                  {phase}
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}
