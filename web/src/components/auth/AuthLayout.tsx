import { Brain, FileText, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'

import { ThemeToggle } from '@/components/ThemeToggle'

const PILLARS = [
  {
    icon: Brain,
    title: 'Memory that persists',
    body: 'Tell it once. It still knows next week, in a new session.',
  },
  {
    icon: FileText,
    title: 'Answers you can check',
    body: 'Every claim carries a citation back to the page it came from.',
  },
  {
    icon: Sparkles,
    title: 'Reusable skills',
    body: 'Summaries, SWOTs, meeting notes — one click, any workspace.',
  },
] as const

/**
 * Shell for the signed-out screens.
 *
 * The left panel is hidden below `lg`. On a phone the form is the entire job, and marketing copy
 * above it would just push the fields under the fold.
 */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle: string
  children: ReactNode
  footer: ReactNode
}) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <aside className="relative hidden flex-col justify-between bg-sidebar p-12 lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary">
            <Sparkles className="size-4 text-primary-foreground" aria-hidden />
          </div>
          <span className="font-semibold tracking-tight">AI Workspace</span>
        </div>

        <div className="max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight">
            One workspace for every conversation, document, and decision.
          </h2>
          <ul className="mt-10 space-y-6">
            {PILLARS.map(({ icon: Icon, title: pillarTitle, body }) => (
              <li key={pillarTitle} className="flex gap-3.5">
                <Icon className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden />
                <div>
                  <p className="text-sm font-medium">{pillarTitle}</p>
                  <p className="text-sm text-muted-foreground">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-xs text-muted-foreground">
          Visibility Bots Innovation Lab · AI Summer Fellowship 2026
        </p>
      </aside>

      <main className="relative flex items-center justify-center px-6 py-12">
        <div className="absolute right-6 top-6">
          <ThemeToggle />
        </div>

        <div className="w-full max-w-sm">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary">
              <Sparkles className="size-4 text-primary-foreground" aria-hidden />
            </div>
            <span className="font-semibold tracking-tight">AI Workspace</span>
          </div>

          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">{subtitle}</p>

          <div className="mt-8">{children}</div>

          <div className="mt-6 text-sm text-muted-foreground">{footer}</div>
        </div>
      </main>
    </div>
  )
}
